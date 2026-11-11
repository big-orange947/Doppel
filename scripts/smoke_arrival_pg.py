"""Synthetic late-arrival integration; explicit PG, offline embedding, retained state."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import os
from pathlib import Path
from typing import Literal

from doppel_memory import (
    ChatMessage,
    DeterministicMemoryConsolidator,
    DoppelClient,
    MemoryFilter,
    MemoryScope,
    PersonalMemoryAnalysis,
    PersonalMemoryDraft,
    PersonalMemoryMiner,
    PersonalMemoryMinerConfig,
    PersonalMemoryQueryDraftV2,
    PostgreSQLStore,
    PostgreSQLVectorIndex,
    VectorIndexConfig,
    memory_index_fingerprint,
)
from examples.arrival_inbox import ArrivalInbox, drain_once
from examples.personal_memory import StructuredQueryPlanner
from examples.personal_memory_runtime import PersonalMemoryWorkflow, WorkflowState
from scripts.smoke_personal_workflow import OfflineSentenceEmbedding, storage_identity
from scripts.smoke_workflow_lifecycle import InterruptIndex, at

PRIMARY = MemoryScope(user_id="synthetic-owner", agent_id="arrival-pg")
FOREIGN = MemoryScope(user_id="synthetic-other", agent_id="arrival-pg")
STAGES = ("seed", "interrupt", "resume", "replay")


class Analyzer:
    name, version = "smoke.synthetic-arrival", "1"

    def __init__(self):
        self.calls = 0

    async def analyze(self, request):
        self.calls += 1
        return PersonalMemoryAnalysis(
            memories=[
                PersonalMemoryDraft(
                    content=message.text,
                    memory_type="state",
                    topic_key="opaque.interval"
                    if message.identity_key == "interval"
                    else "opaque.slot",
                    temporal_status="current",
                    revision_kind="correction"
                    if message.identity_key == "new"
                    else "assertion",
                    valid_from=message.at,
                    valid_to=at(2) if message.identity_key == "interval" else None,
                    evidence_ids=[message.identity_key],
                )
                for message in request.messages
            ]
        )


def fingerprint(rows):
    return hashlib.sha256(
        json.dumps(
            [
                r.model_dump(mode="json")
                for r in sorted(rows, key=lambda r: r.memory_id)
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


async def exercise(
    stage, directory, store, index, storage_key, *, require_vector=False
):
    marker = directory / "stage.json"
    previous = json.loads(marker.read_text()) if marker.exists() else None
    expected = {"interrupt": "seed", "resume": "interrupt", "replay": "resume"}
    if (stage == "seed" and directory.exists()) or (
        stage != "seed" and (previous is None or previous["stage"] != expected[stage])
    ):
        raise ValueError(
            "unexpected arrival stage; inspect retained state, do not reset"
        )
    if previous and previous["binding"] != [storage_key, index.identity]:
        raise ValueError("arrival storage/index binding changed")
    inbox = ArrivalInbox(directory / "inbox.sqlite3")
    analyzer = Analyzer()
    writer = InterruptIndex(index) if stage == "interrupt" else index

    def factory(batch):
        return PersonalMemoryWorkflow(
            directory / "jobs",
            workflow_key=batch.identity,
            storage_identity=storage_key,
            store=store,
            scope=batch.scope,
            miner=PersonalMemoryMiner(
                analyzer, PersonalMemoryMinerConfig(owner_target_scope="conversation")
            ),
            consolidator=DeterministicMemoryConsolidator(),
            index=writer,
            index_page_size=2,
            history=batch.history(),
            history_identity=batch.identity,
        )

    if stage == "seed":
        for scope, identity, text in [
            (PRIMARY, "new", "opaque latest"),
            (FOREIGN, "foreign", "opaque foreign"),
        ]:
            await inbox.append(
                scope, ChatMessage.of("owner", text, at(3), message_id=identity)
            )
            result = await drain_once(inbox, scope, store, factory)
            if not result.get("ok") or not result["complete"]:
                raise RuntimeError("arrival seed did not complete")
    elif stage == "interrupt":
        if await inbox.reserve(PRIMARY) is not None:
            raise ValueError("unexpected pending seed batch")
        for identity, text in [("old", "opaque older"), ("interval", "opaque bounded")]:
            await inbox.append(
                PRIMARY, ChatMessage.of("owner", text, at(1), message_id=identity)
            )
        result = await drain_once(inbox, PRIMARY, store, factory)
        if (
            result.get("ok") is not False
            or result.get("stage") != "index"
            or not writer.failed_operations
        ):
            raise RuntimeError("expected index boundary interruption was not exercised")
    else:
        pending = await inbox.reserve(PRIMARY)
        if stage == "resume":
            assert previous is not None
            if pending is None or pending.identity != previous["pending_batch"]:
                raise ValueError("original frozen batch missing")
            saved = WorkflowState.model_validate_json(factory(pending).path.read_text())
            if saved.stage != "index":
                raise ValueError("resume must continue saved index stage")
        elif pending is not None:
            raise ValueError("replay requires acknowledged queue")
        result = await drain_once(inbox, PRIMARY, store, factory)
        if not result["complete"]:
            raise RuntimeError("arrival recovery did not complete")
        if analyzer.calls:
            raise RuntimeError("recovery repeated analysis")

    rows = []
    manifest_checks, stale, missing = 0, 0, 0
    for scope in (PRIMARY, FOREIGN):
        records = (
            await store.scan(
                scope, filters=MemoryFilter(include_inactive=True), limit=100
            )
        ).records
        if len(records) >= 100:
            raise RuntimeError("audit bound reached")
        rows.extend(records)
        for record in records:
            entry = await index.inspect(scope, record.memory_id)
            active = record.state.value in {"candidate", "confirmed"}
            stale += int(entry is not None and not active)
            missing += int(
                active
                and (
                    entry is None
                    or entry.fingerprint != memory_index_fingerprint(record)
                )
            )
            manifest_checks += 1
        for record in records:
            if record.extractor == "ingestor":
                expected_at = (
                    at(1) if record.source_message_id in {"old", "interval"} else at(3)
                )
                if record.created_at != expected_at:
                    raise RuntimeError("source timestamp was rewritten")
    if stage == "interrupt":
        if not (stale or missing):
            raise RuntimeError("interruption left no observable index divergence")
    elif stale or missing:
        raise RuntimeError("completed batch has inconsistent manifest")

    client = DoppelClient(store)

    async def query(
        scope, view: Literal["current", "as_of"] = "current", as_of=None, topics=None
    ):
        result = await client.query_personal_memory(
            "opaque",
            [scope],
            now=at(5),
            semantic_index=index,
            planner=StructuredQueryPlanner(
                PersonalMemoryQueryDraftV2(
                    search_text="opaque",
                    temporal_view=view,
                    as_of=as_of,
                    topic_keys=topics or [],
                )
            ),
        )
        if any(hit.record.scope != scope for hit in result.hits):
            raise RuntimeError("scope leakage")
        return result.hits

    current = await query(PRIMARY)
    foreign = await query(FOREIGN)
    empty = await query(MemoryScope(user_id="synthetic-empty", agent_id="arrival-pg"))
    inside = await query(PRIMARY, "as_of", at(1, 12), ["opaque.interval"])
    outside = await query(PRIMARY, "as_of", at(3), ["opaque.interval"])
    if (
        [h.record.content for h in current] != ["opaque latest"]
        or [h.record.content for h in foreign] != ["opaque foreign"]
        or empty
        or outside
    ):
        raise RuntimeError("current/scope/outside-time expectation failed")
    if [h.record.content for h in inside] != (
        [] if stage == "seed" else ["opaque bounded"]
    ):
        raise RuntimeError("late interval missing from historical query")
    if any(h.candidate_evidence.as_of_match != "validity_match" for h in inside):
        raise RuntimeError("as-of hit lacks explicit validity match")
    evidence = {ref["evidence_id"] for ref in current[0].record.metadata["evidence"]}
    if evidence != ({"new"} if stage == "seed" else {"new", "old"}):
        raise RuntimeError("current evidence provenance differs")
    semantic_hits = sum(
        "semantic" in h.candidate_evidence.sources for h in [*current, *inside]
    )
    if (
        require_vector
        and stage != "interrupt"
        and semantic_hits != len(current) + len(inside)
    ):
        raise RuntimeError(
            "final hits were not actually supported by vector candidates"
        )
    digest = fingerprint(rows)
    if stage in {"resume", "replay"}:
        assert previous is not None
        if digest != previous["store_digest"]:
            raise RuntimeError("index recovery/replay mutated authoritative records")
    pending = await inbox.reserve(PRIMARY)
    if (pending is not None) != (stage == "interrupt"):
        raise RuntimeError("queue acknowledgment differs from workflow completion")
    report = {
        "stage": stage,
        "passed": True,
        "complete": pending is None,
        "analyzer_calls": analyzer.calls,
        "manifest_checks": manifest_checks,
        "stale_inactive_entries": stale,
        "missing_or_changed_active_entries": missing,
        "current_evidence_ids": sorted(evidence),
        "historical_hits": len(inside),
        "vector_supported_final_hits": semantic_hits,
        "store_digest": digest,
        "pending_batch": pending.identity if pending else "",
        "binding": [storage_key, index.identity],
        "paid_calls": 0,
        "quality_score_available": False,
        "fixtures_retained": True,
    }
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, sort_keys=True, indent=2), encoding="utf-8")
    temporary.replace(marker)
    return report


async def run(args):
    dsn = os.environ.get("DOPPEL_WORKFLOW_PG_DSN", "")
    key = storage_identity(dsn, args.schema)
    if not args.schema.startswith("doppel_arrival_"):
        raise ValueError("dedicated doppel_arrival_ schema required")
    driver = importlib.import_module("asyncpg")
    connection = await driver.connect(dsn)
    try:
        exists = bool(
            await connection.fetchval(
                "SELECT 1 FROM pg_namespace WHERE nspname=$1", args.schema
            )
        )
        if args.stage == "seed" and (exists or args.directory.exists()):
            raise ValueError("seed requires absent schema and directory")
        if args.stage != "seed" and (not exists or not args.directory.is_dir()):
            raise ValueError("resume requires existing schema and journals")
    finally:
        await connection.close()
    store = PostgreSQLStore(dsn, schema=args.schema, create_schema=True)
    try:
        provider = await asyncio.to_thread(
            OfflineSentenceEmbedding, args.embedding_model_path
        )
        index = PostgreSQLVectorIndex(
            store, provider, VectorIndexConfig(create_extension=True)
        )
        await index.initialize()
        report = await exercise(
            args.stage, args.directory, store, index, key, require_vector=True
        )
        report.update(
            runner="doppel.arrival-pg.v1",
            embedding_calls=provider.calls,
            embedding_dimensions=provider.dimensions,
            schema=args.schema,
        )
        return report
    finally:
        await store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-pg", action="store_true")
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--embedding-model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.live_pg or args.output.exists():
        parser.error("--live-pg and a new receipt path required")
    try:
        report = asyncio.run(run(args))
    except Exception as exc:  # noqa: BLE001 - retain state, redact credentials/provider bodies
        report = {
            "passed": False,
            "stage": args.stage,
            "error_type": type(exc).__name__,
            "paid_calls": 0,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
