"""Synthetic comparison boundaries; no model/API or benchmark-score claims."""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from benchmarks.public_context_baseline import RawHistoryHost
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_comparison import (
    CANDIDATE_LIMIT,
    CONTEXT_BYTE_LIMIT,
    context_item,
    encoded,
    inventory,
    load_bindings,
    pack_context,
    positions,
    run_comparison,
    select_candidates,
)
from benchmarks.public_memory_ingestion import build_ingestion_plan
from doppel_memory.indexing import IndexEntry, memory_index_fingerprint
from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryIsolationError,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    RecallResult,
)
from doppel_memory.sqlite_store import SQLiteStore
from integrations.aml.contract import memory_scope
from tests.test_public_context_baseline import sample
from tests.test_public_memory_ingestion import config


async def fixture(tmp_path: Path):
    runtime = prepare_case(sample(), dataset_namespace="synthetic").runtime
    manifest = {
        "run_namespace": "run",
        "max_messages": 1,
        "manifest_fingerprint": "a" * 64,
        "source_sha256": "b" * 64,
        "temporal_policy": "full",
    }
    plan = build_ingestion_plan([runtime], manifest, config(), max_calls=4)
    scope = memory_scope("run", runtime.user_id)
    store = SQLiteStore(tmp_path / "store.sqlite3")
    host = RawHistoryHost(store)
    raw = await host.ingest(runtime, scope, max_messages=1)
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    with sqlite3.connect(tmp_path / "ingestion.sqlite3") as journal:
        journal.executescript(
            "CREATE TABLE writes (key TEXT, completion TEXT); CREATE TABLE sources (scope TEXT, event TEXT, memory TEXT);"
        )
        journal.executemany(
            "INSERT INTO writes VALUES (?,?)",
            [(c["write_key"], "{}") for c in plan["chunks"]],
        )
        journal.executemany(
            "INSERT INTO sources VALUES (?,?,?)",
            [(r.scope.scope_key, r.source_event_id, r.memory_id) for r in raw],
        )
    report = {
        "plan": plan,
        "status": "complete",
        "all_histories_ingested": True,
        "postgres_schema": "public_memory_" + plan["plan_fingerprint"][:12],
        "store_record_audit": {"provenance_failures": 0},
    }
    bindings = load_bindings([runtime], manifest, report, tmp_path)
    records = await inventory(store, [scope])
    return store, runtime, manifest, report, scope, bindings, records


@pytest.mark.asyncio
async def test_complete_source_projection_read_only_and_question_independent(
    tmp_path: Path,
):
    store, runtime, manifest, report, _, bindings, records = await fixture(tmp_path)
    try:
        path = tmp_path / "ingestion.sqlite3"
        before = path.read_bytes()
        changed = replace(
            runtime, query=replace(runtime.query, query="DIFFERENT_QUESTION")
        )
        assert load_bindings([changed], manifest, report, tmp_path) == bindings
        assert path.read_bytes() == before
        assert sorted(b.position for b in bindings.values()) == [(0, 0), (0, 1), (1, 1)]
        items = [context_item(r, records, bindings) for r in records.values()]
        assert "GOLD_SECRET" not in json.dumps(items)
        assert {i["role"] for i in items} == {"user", "assistant"}
        assert (
            next(i for i in items if i["role"] == "assistant")["authority"]
            == "agent_output"
        )
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation", ["partial", "plan", "source", "journal", "embedding_namespace"]
)
async def test_incomplete_mismatched_binding_fails(tmp_path: Path, mutation: str):
    store, runtime, manifest, report, _, _, _ = await fixture(tmp_path)
    try:
        altered = deepcopy(report)
        if mutation == "partial":
            altered["all_histories_ingested"] = False
        elif mutation == "plan":
            altered["plan"]["chunks"][0]["roles"] = ["assistant"]
        elif mutation == "source":
            with sqlite3.connect(tmp_path / "ingestion.sqlite3") as journal:
                journal.execute("DELETE FROM sources WHERE rowid=1")
        elif mutation == "journal":
            with sqlite3.connect(tmp_path / "ingestion.sqlite3") as journal:
                journal.execute("UPDATE writes SET completion=NULL WHERE rowid=1")
        else:
            altered["postgres_schema"] = "another_schema"
        with pytest.raises(ValueError):
            load_bindings([runtime], manifest, altered, tmp_path)
    finally:
        await store.close()


def derived(scope: MemoryScope, event: str) -> MemoryRecord:
    return MemoryRecord(
        memory_id="derived",
        scope=scope,
        kind="fact",
        actor=Actor.OWNER,
        authority=FactAuthority.HUMAN_SELF,
        content="summary without an annotated detail",
        tags=["personal-memory"],
        metadata={
            "subject": "owner",
            "subject_id": scope.user_id,
            "source_scope_key": scope.scope_key,
            "evidence": [{"evidence_id": event}],
        },
    )


@pytest.mark.asyncio
async def test_derived_citation_is_not_semantic_information_score(tmp_path: Path):
    store, _, _, _, scope, bindings, records = await fixture(tmp_path)
    try:
        raw = next(r for r in records.values() if r.actor == "owner")
        memory = derived(scope, raw.source_event_id)
        item = context_item(memory, records, bindings)
        assert item["text"] == memory.content
        assert item["channel"] == "memory" and item["role"] == "derived-owner-memory"
        assert positions([item, item], bindings) == [
            bindings[(scope.scope_key, raw.source_event_id)].position
        ]
        assert raw.content not in item["text"]  # No implicit free source expansion.
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation", ["agent", "unknown", "cross_scope", "inactive_source", "subject"]
)
async def test_derived_identity_and_source_gates(tmp_path: Path, mutation: str):
    store, _, _, _, scope, bindings, records = await fixture(tmp_path)
    try:
        raw = next(r for r in records.values() if r.actor == "owner")
        memory = derived(scope, raw.source_event_id)
        if mutation == "agent":
            memory.actor = Actor.AGENT
            memory.authority = FactAuthority.AGENT_OUTPUT
        elif mutation == "unknown":
            memory.metadata["evidence"] = [{"evidence_id": "unknown"}]
        elif mutation == "cross_scope":
            records[raw.memory_id] = raw.model_copy(
                update={"scope": MemoryScope(user_id="other", agent_id="host")}
            )
        elif mutation == "inactive_source":
            records[raw.memory_id] = raw.model_copy(
                update={"state": MemoryState.EXPIRED}
            )
        else:
            memory.metadata["subject_id"] = "other"
        with pytest.raises(ValueError):
            context_item(memory, records, bindings)
    finally:
        await store.close()


def candidate_fixture():
    scope = MemoryScope(user_id="u", agent_id="a")
    candidates = [
        RecallResult(
            scope=scope, memory_id=str(i), fact="POISON", similarity=1 - i / 1000
        )
        for i in range(200)
    ]
    items = {
        str(i): {
            "scope_key": scope.scope_key,
            "channel": "raw" if i % 2 == 0 else "memory",
            "text": f"bound {i}",
        }
        for i in range(200)
    }
    return scope, candidates, items


def test_channel_filter_before_candidate_cap_and_combined_not_doubled():
    scope, candidates, items = candidate_fixture()
    for channel in ("raw", "memory", "combined"):
        result = select_candidates(candidates, items, scope, channel)
        assert len(result) == CANDIDATE_LIMIT
        assert all(c.fact.startswith("bound ") and c.raw_text == c.fact for c in result)
    assert select_candidates(candidates, items, scope, "memory")[-1].memory_id == "159"
    assert select_candidates(candidates, items, scope, "combined")[-1].memory_id == "79"


@pytest.mark.parametrize("mutation", ["scope", "item_scope", "nan"])
def test_vector_candidates_cannot_escape_or_poison(mutation: str):
    scope, candidates, items = candidate_fixture()
    if mutation == "scope":
        candidates[0].scope = MemoryScope(user_id="other", agent_id="a")
    elif mutation == "item_scope":
        items["0"]["scope_key"] = "other"
    else:
        candidates[0].similarity = float("nan")
    with pytest.raises((ValueError, MemoryIsolationError)):
        select_candidates(candidates, items, scope, "raw")


def test_fixed_context_prefix_counts_json_and_multibyte_overhead():
    items = [{"text": "中文" * 1000, "channel": "raw"} for _ in range(30)]
    packed = pack_context(items)
    assert len(encoded(packed)) <= CONTEXT_BYTE_LIMIT
    assert len(packed) < 20 and packed == items[: len(packed)]
    assert len(encoded([*packed, items[len(packed)]])) > CONTEXT_BYTE_LIMIT
    assert pack_context([{"text": "x" * CONTEXT_BYTE_LIMIT}, {"text": "tiny"}]) == []
    assert len(pack_context([{"text": "tiny"}] * 25)) == 20


@pytest.mark.asyncio
async def test_inactive_memory_and_governance_not_claims(tmp_path: Path):
    store, _, _, _, scope, bindings, records = await fixture(tmp_path)
    try:
        governance = MemoryRecord(
            scope=scope,
            kind="memory_conflict",
            tags=["memory-conflict"],
            content="not a claim",
        )
        assert context_item(governance, records, bindings) is None
        assert (
            context_item(
                governance.model_copy(update={"state": MemoryState.EXPIRED}),
                records,
                bindings,
            )
            is None
        )
        with pytest.raises(ValueError, match="unclassified"):
            context_item(
                governance.model_copy(update={"kind": "fact"}), records, bindings
            )
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "none",
        "stale_index",
        "revoke",
        "invent",
        "duplicate",
        "inactive",
        "inactive_stale",
    ],
)
async def test_composition_read_only_no_gold_and_post_ranking_revalidation(
    tmp_path: Path, monkeypatch, failure: str
):
    import benchmarks.public_memory_comparison as module

    store, runtime, manifest, report, scope, _, records = await fixture(tmp_path)
    raw = next(r for r in records.values() if r.actor == "owner")
    written = await store.put(derived(scope, raw.source_event_id))
    memory_id = written.memory_id
    if failure in {"inactive", "inactive_stale"}:
        await store.transition(scope, memory_id, MemoryState.EXPIRED)
    records = await inventory(store, [scope])
    prepared = prepare_case(sample(), dataset_namespace="synthetic")
    report["store_record_audit"].update(
        raw_records=3, derived_records_including_inactive=1, governance_records=0
    )
    report["embedding"] = {"name": "synthetic", "version": "1", "dimensions": 2}
    monkeypatch.setattr(store, "schema", report["postgres_schema"], raising=False)

    class Provider:
        name = "synthetic"
        version = "1"
        dimensions = 2

    class Index:
        identity = "synthetic-index"

        async def inspect(self, scope, memory_id):
            record = records[memory_id]
            if record.state == MemoryState.EXPIRED and failure == "inactive":
                return None
            return IndexEntry(
                memory_id=memory_id,
                scope_key=scope.scope_key,
                fingerprint="wrong"
                if failure == "stale_index"
                else memory_index_fingerprint(record),
                source_version=record.version,
            )

        async def search(self, question, scopes, *, filters, limit):
            assert question == runtime.query.query and "GOLD_SECRET" not in question
            assert scopes == [scope] and limit == 4
            return [
                RecallResult(
                    scope=scope, memory_id=r.memory_id, fact="POISON", similarity=0.9
                )
                for r in records.values()
                if r.state == MemoryState.CONFIRMED
            ]

    class Ranking:
        last_summary = None
        provider = None

        async def rerank(self, question, candidates, *, limit):
            assert "GOLD_SECRET" not in json.dumps(
                [c.model_dump(mode="json") for c in candidates]
            )
            if failure == "revoke":
                await store.transition(scope, raw.memory_id, MemoryState.EXPIRED)
            elif failure == "invent":
                return [candidates[0].model_copy(update={"memory_id": "invented"})]
            elif failure == "duplicate":
                return [candidates[0], candidates[0]]
            return candidates[:limit]

        def report(self):
            return {"synthetic": True}

    ranking = Ranking()
    ranking.provider = ranking
    monkeypatch.setattr(module, "PostgreSQLStore", lambda *a, **kw: store)
    monkeypatch.setattr(module, "PostgreSQLVectorIndex", lambda *a, **kw: Index())
    monkeypatch.setattr(module, "_LocalEmbeddingProvider", lambda **kw: Provider())
    monkeypatch.setattr(module, "execution_metadata", lambda: {"synthetic": True})
    if failure not in {"none", "inactive"}:
        with pytest.raises(ValueError):
            await run_comparison(
                [(runtime, prepared.scoring)],
                manifest,
                report,
                run_dir=tmp_path,
                dsn="synthetic",
                embedding_cache_dir=None,
                reranker=ranking,
            )
    else:
        result = await run_comparison(
            [(runtime, prepared.scoring)],
            manifest,
            report,
            run_dir=tmp_path,
            dsn="synthetic",
            embedding_cache_dir=None,
            reranker=ranking,
        )
        assert len(result["rows"]) == 6 and result["record_or_index_writes"] == 0
        assert result["corpus_sha256_before"] == result["corpus_sha256_after"]
        assert (
            result["reader_executed"] is False
            and result["qa_metrics_available"] is False
        )
        context = [i for row in result["rows"] for i in row["context"]]
        assert any(i["memory_id"] == memory_id for i in context) == (failure == "none")
        if failure == "inactive":
            assert result["corpus_counts"]["memory"] == 0
            assert result["inventory_counts_including_inactive"]["memory"] == 1
        assert "POISON" not in json.dumps(context) and "GOLD_SECRET" not in json.dumps(
            context
        )
