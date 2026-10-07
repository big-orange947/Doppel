"""Opened-history retrieval diagnostic, not full Doppel/QA or AML scores.

Read the completed ingestion namespace; do not ingest, repair or reindex it.
Raw and derived records share one existing embedding profile. Channel selection
precedes a fixed candidate cap; the combined channel gets that same cap, not two
caps. A small-corpus exhaustive vector ordering avoids channel starvation from
post-filtering an ANN top-k. This is not a scalable search/latency benchmark.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_context_baseline import (
    execution_metadata,
    score_evidence,
    select_diagnostic_cases,
)
from benchmarks.public_context_rerank import (
    LocalContextCrossEncoder,
    StrictContextReranker,
)
from benchmarks.public_longmemeval import RuntimeCase, ScoringCase
from benchmarks.public_memory_pilot import _hash
from doppel_memory.indexing import memory_index_fingerprint
from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryFilter,
    MemoryIsolationError,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    RecallResult,
)
from doppel_memory.postgres_store import PostgreSQLStore
from doppel_memory.store import MemoryStore
from doppel_memory.vector import PostgreSQLVectorIndex, VectorIndexConfig
from integrations.aml.contract import event_ids, memory_scope, write_key

Channel = Literal["raw", "memory", "combined"]
CANDIDATE_LIMIT = 80
ITEM_LIMIT = 20
CONTEXT_BYTE_LIMIT = 24_000


def encoded(items: Sequence[Mapping[str, Any]]) -> bytes:
    return json.dumps(list(items), ensure_ascii=False, separators=(",", ":")).encode()


@dataclass(frozen=True)
class SourceBinding:
    memory_id: str
    position: tuple[int, int]
    role: str
    text: str
    timestamp_ms: int
    session_id: str
    transport_turn_index: int


def load_bindings(
    cases: Sequence[RuntimeCase],
    manifest: Mapping[str, Any],
    ingestion_report: Mapping[str, Any],
    run_dir: Path,
) -> dict[tuple[str, str], SourceBinding]:
    """Read-only journal and complete-plan check; no answers or evidence labels."""
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    payload = dict(plan)
    fingerprint = payload.pop("plan_fingerprint")
    if (
        fingerprint != _hash(payload)
        or ingestion_report.get("plan") != plan
        or plan["manifest_fingerprint"] != manifest["manifest_fingerprint"]
        or plan["source_sha256"] != manifest["source_sha256"]
        or plan["run_namespace"] != manifest["run_namespace"]
        or ingestion_report.get("status") != "complete"
        or ingestion_report.get("all_histories_ingested") is not True
        or ingestion_report.get("postgres_schema")
        != "public_memory_" + fingerprint[:12]
        or ingestion_report["store_record_audit"]["provenance_failures"] != 0
    ):
        raise ValueError("complete ingestion binding required")
    chunks = []
    expected: dict[tuple[str, str], tuple[Any, ...]] = {}
    for case in cases:
        scope = memory_scope(manifest["run_namespace"], case.user_id)
        for chunk in case.ingestion_chunks(max_messages=manifest["max_messages"]):
            ids = event_ids(scope, chunk.request)
            chunks.append(
                {
                    "user_id": case.user_id,
                    "request_id": chunk.request.request_id,
                    "write_key": write_key(scope, chunk.request),
                    "scope_key": scope.scope_key,
                    "source_session_index": chunk.source_session_index,
                    "source_turn_indices": list(chunk.source_turn_indices),
                    "event_ids": list(ids),
                    "roles": [m.role for m in chunk.request.messages],
                    "payload_sha256": _hash(chunk.request.model_dump(mode="json")),
                    "message_count": len(chunk.request.messages),
                }
            )
            for index, (message, event, turn) in enumerate(
                zip(chunk.request.messages, ids, chunk.source_turn_indices, strict=True)
            ):
                key = (scope.scope_key, event)
                if key in expected or message.timestamp is None:
                    raise ValueError("source identity/timestamp invalid")
                expected[key] = (
                    (chunk.source_session_index, turn),
                    message.role,
                    message.content,
                    message.timestamp,
                    chunk.request.session_id,
                    index,
                )
    if chunks != plan["chunks"] or len(expected) != plan["total_messages"]:
        raise ValueError("runtime history differs from completed ingestion")
    uri = (run_dir / "ingestion.sqlite3").resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as journal:
        writes = journal.execute("SELECT key, completion FROM writes").fetchall()
        if {k for k, _ in writes} != {c["write_key"] for c in chunks} or any(
            not completion for _, completion in writes
        ):
            raise ValueError("journal histories incomplete")
        sources = journal.execute("SELECT scope, event, memory FROM sources").fetchall()
    if {(scope, event) for scope, event, _ in sources} != set(expected):
        raise ValueError("journal source set differs from runtime")
    return {
        (scope, event): SourceBinding(memory, *expected[(scope, event)])
        for scope, event, memory in sources
    }


async def inventory(
    store: MemoryStore, scopes: Sequence[MemoryScope]
) -> dict[str, MemoryRecord]:
    result: dict[str, MemoryRecord] = {}
    for scope in scopes:
        cursor = ""
        for _ in range(1000):
            page = await store.scan(
                scope,
                filters=MemoryFilter(include_inactive=True),
                cursor=cursor,
                limit=200,
            )
            for record in page.records:
                if (
                    record.scope.scope_key != scope.scope_key
                    or record.memory_id in result
                ):
                    raise MemoryIsolationError("inventory escaped exact scope/identity")
                result[record.memory_id] = record.model_copy(deep=True)
            if not page.has_more:
                break
            if not page.next_cursor or page.next_cursor == cursor:
                raise ValueError("inventory cursor did not advance")
            cursor = page.next_cursor
        else:
            raise ValueError("inventory page bound exceeded")
    return result


def check_raw(record: MemoryRecord, source: SourceBinding, event: str) -> None:
    actor = Actor.OWNER if source.role == "user" else Actor.AGENT
    raw = record.metadata.get("raw", {})
    if (
        record.memory_id != source.memory_id
        or record.source_event_id != event
        or record.extractor != "ingestor"
        or record.kind != "event"
        or record.state != MemoryState.CONFIRMED
        or record.actor != actor
        or record.authority != FactAuthority.of(actor)
        or record.content != source.text.strip()
        or record.created_at.timestamp() * 1000 != source.timestamp_ms
        or raw.get("source_text") != source.text
        or raw.get("transport_role") != source.role
        or raw.get("session_id") != source.session_id
        or raw.get("turn_index") != source.transport_turn_index
    ):
        raise ValueError("raw Store/source binding invalid")


def context_item(
    record: MemoryRecord,
    records: Mapping[str, MemoryRecord],
    sources: Mapping[tuple[str, str], SourceBinding],
) -> dict[str, Any] | None:
    """Return source-bound text, never substitute an index candidate's text."""
    if record.state != MemoryState.CONFIRMED:
        return None
    scope = record.scope.scope_key
    if record.extractor == "ingestor":
        event = record.source_event_id
        source = sources.get((scope, event))
        if source is None:
            raise ValueError("raw source missing")
        check_raw(record, source, event)
        channel, text, role, events = "raw", source.text, source.role, [event]
    elif "personal-memory" in record.tags:
        evidence = record.metadata.get("evidence")
        if (
            record.actor != Actor.OWNER
            or record.authority != FactAuthority.HUMAN_SELF
            or record.metadata.get("subject") != "owner"
            or record.metadata.get("subject_id") != record.scope.user_id
            or record.metadata.get("source_scope_key") != scope
            or not isinstance(evidence, list)
            or not evidence
        ):
            raise ValueError("derived identity/provenance invalid")
        events = []
        for reference in evidence:
            event = (
                reference.get("evidence_id") if isinstance(reference, dict) else None
            )
            source = sources.get((scope, event)) if isinstance(event, str) else None
            raw = records.get(source.memory_id) if source else None
            if (
                not isinstance(event, str)
                or source is None
                or raw is None
                or raw.scope.scope_key != scope
            ):
                raise ValueError("derived source missing or cross scope")
            check_raw(raw, source, event)
            if raw.actor != record.actor or raw.authority != record.authority:
                raise ValueError("derived evidence authority invalid")
            events.append(event)
        channel, text, role = "memory", record.content, "derived-owner-memory"
    else:
        # Governance markers are not claims or raw dialogue.
        if record.kind != "memory_conflict" or "memory-conflict" not in record.tags:
            raise ValueError("unclassified Store record")
        return None
    return {
        "channel": channel,
        "memory_id": record.memory_id,
        "scope_key": scope,
        "role": role,
        "actor": record.actor,
        "authority": record.authority.value,
        "text": text,
        "observed_at": record.created_at.isoformat(),
        "temporal_status": record.metadata.get("temporal_status"),
        "valid_from": record.metadata.get("valid_from"),
        "valid_to": record.metadata.get("valid_to"),
        "source_events": list(dict.fromkeys(events)),
    }


def select_candidates(
    candidates: Sequence[RecallResult],
    items: Mapping[str, Mapping[str, Any]],
    scope: MemoryScope,
    channel: Channel,
) -> list[RecallResult]:
    selected = []
    seen = set()
    for candidate in candidates:
        if candidate.scope is None or candidate.scope.scope_key != scope.scope_key:
            raise MemoryIsolationError("vector candidate escaped exact scope")
        if not math.isfinite(candidate.similarity):
            raise ValueError("nonfinite vector score")
        item = items.get(candidate.memory_id)
        if item is None or candidate.memory_id in seen:
            continue
        if item["scope_key"] != scope.scope_key:
            raise MemoryIsolationError("context item escaped exact scope")
        if channel != "combined" and item["channel"] != channel:
            continue
        seen.add(candidate.memory_id)
        selected.append(
            candidate.model_copy(
                update={"fact": item["text"], "raw_text": item["text"]}
            )
        )
        if len(selected) == CANDIDATE_LIMIT:
            break
    return selected


def pack_context(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Fixed rank prefix; no gold-conditioned drop/expansion or partial snippets."""
    packed: list[dict[str, Any]] = []
    for item in items[:ITEM_LIMIT]:
        next_items = [*packed, dict(item)]
        if len(encoded(next_items)) > CONTEXT_BYTE_LIMIT:
            break
        packed = next_items
    return packed


def positions(
    items: Sequence[Mapping[str, Any]], sources: Mapping[tuple[str, str], SourceBinding]
) -> list[tuple[int, int]]:
    return sorted(
        {
            sources[(item["scope_key"], event)].position
            for item in items
            for event in item["source_events"]
        }
    )


async def run_comparison(
    cases: Sequence[tuple[RuntimeCase, ScoringCase]],
    manifest: Mapping[str, Any],
    ingestion_report: Mapping[str, Any],
    *,
    run_dir: Path,
    dsn: str,
    embedding_cache_dir: Path | None,
    reranker: StrictContextReranker | None = None,
) -> dict[str, Any]:
    sources = load_bindings([r for r, _ in cases], manifest, ingestion_report, run_dir)
    store = PostgreSQLStore(dsn, schema=ingestion_report["postgres_schema"])
    provider = _LocalEmbeddingProvider(cache_dir=embedding_cache_dir)
    identity = {
        "name": provider.name,
        "version": provider.version,
        "dimensions": provider.dimensions,
    }
    if identity != ingestion_report["embedding"]:
        raise ValueError("embedding differs from ingestion")
    index = PostgreSQLVectorIndex(
        store, provider, VectorIndexConfig(create_extension=False)
    )
    scopes = [memory_scope(manifest["run_namespace"], r.user_id) for r, _ in cases]
    try:
        records = await inventory(store, scopes)
        before = _hash(
            {key: value.model_dump(mode="json") for key, value in records.items()}
        )
        items = {
            key: item
            for key, record in records.items()
            if (item := context_item(record, records, sources)) is not None
        }
        counts = {
            "raw": sum(i["channel"] == "raw" for i in items.values()),
            "memory": sum(i["channel"] == "memory" for i in items.values()),
            "governance": len(records) - len(items),
        }
        audit = ingestion_report["store_record_audit"]
        if counts != {
            "raw": audit["raw_records"],
            "memory": audit["derived_records_including_inactive"],
            "governance": audit["governance_records"],
        }:
            raise ValueError("corpus counts differ from completed ingestion")
        # Verify existing entries only; never repair/index to make a profile pass.
        for record in records.values():
            entry = await index.inspect(record.scope, record.memory_id)
            if (
                entry is None
                or entry.fingerprint != memory_index_fingerprint(record)
                or entry.source_version != record.version
            ):
                raise ValueError("existing vector entry missing or stale")
        rows = []
        for runtime, scoring in cases:
            scope = memory_scope(manifest["run_namespace"], runtime.user_id)
            size = sum(r.scope.scope_key == scope.scope_key for r in records.values())
            ordered = await index.search(
                runtime.query.query,
                [scope],
                filters=MemoryFilter(states={MemoryState.CONFIRMED}),
                limit=size,
            )
            if {c.memory_id for c in ordered} != {
                r.memory_id
                for r in records.values()
                if r.scope.scope_key == scope.scope_key
            }:
                raise ValueError("exhaustive small-corpus vector ordering incomplete")
            for channel in ("raw", "memory", "combined"):
                candidates = select_candidates(ordered, items, scope, channel)
                profiles: list[
                    tuple[str, list[RecallResult], dict[str, Any] | None]
                ] = [(channel + "_vector", candidates, None)]
                if reranker is not None:
                    reranked = list(
                        await reranker.rerank(
                            runtime.query.query, candidates, limit=ITEM_LIMIT
                        )
                    )
                    allowed = {c.memory_id for c in candidates}
                    if any(
                        c.memory_id not in allowed or c.scope != scope for c in reranked
                    ) or len({c.memory_id for c in reranked}) != len(reranked):
                        raise ValueError("reranker introduced a noncandidate")
                    profiles.append(
                        (
                            channel + "_vector_reranked",
                            reranked,
                            reranker.last_summary.model_dump(mode="json")
                            if reranker.last_summary
                            else None,
                        )
                    )
                for name, ranking, summary in profiles:
                    packed = pack_context([items[c.memory_id] for c in ranking])
                    # Revalidate snapshots and every referenced raw source after ordering.
                    rechecks = set()
                    for item in packed:
                        rechecks.add(item["memory_id"])
                        rechecks.update(
                            sources[(scope.scope_key, e)].memory_id
                            for e in item["source_events"]
                        )
                    for key in rechecks:
                        if await store.get(scope, key) != records[key]:
                            raise ValueError("Store changed after ordering")
                    rows.append(
                        {
                            "case_id": scoring.case_id,
                            "profile": name,
                            "candidate_count": len(candidates),
                            "candidate_provenance_coverage": score_evidence(
                                scoring,
                                positions(
                                    [items[c.memory_id] for c in candidates], sources
                                ),
                            ),
                            "rank_at_5_provenance_coverage": score_evidence(
                                scoring,
                                positions(
                                    [items[c.memory_id] for c in ranking[:5]], sources
                                ),
                            ),
                            "packed_provenance_coverage": score_evidence(
                                scoring, positions(packed, sources)
                            ),
                            "packed_item_count": len(packed),
                            "packed_context_bytes": len(encoded(packed)),
                            "packed_channel_counts": {
                                ch: sum(i["channel"] == ch for i in packed)
                                for ch in ("raw", "memory")
                            },
                            "store_revalidation_checks": len(rechecks),
                            "rerank_summary": summary,
                            "context": packed,
                        }
                    )
        after = _hash(
            {
                key: value.model_dump(mode="json")
                for key, value in (await inventory(store, scopes)).items()
            }
        )
        if after != before:
            raise ValueError("corpus changed during comparison")
        return {
            "runner": "doppel.public-memory-comparison.v1",
            "status": "complete",
            "execution_metadata": {
                **execution_metadata(),
                "comparison_source_sha256": hashlib.sha256(
                    Path(__file__).read_bytes()
                ).hexdigest(),
            },
            "manifest_fingerprint": manifest["manifest_fingerprint"],
            "ingestion_plan_fingerprint": ingestion_report["plan"]["plan_fingerprint"],
            "postgres_schema": store.schema,
            "embedding": identity,
            "index_identity": index.identity,
            "corpus_counts": counts,
            "corpus_sha256_before": before,
            "corpus_sha256_after": after,
            "budget": {
                "candidate_items": CANDIDATE_LIMIT,
                "final_items": ITEM_LIMIT,
                "serialized_context_utf8_bytes": CONTEXT_BYTE_LIMIT,
                "reader_tokens_matched": False,
            },
            "ordering": "complete-existing-pgvector-cosine-order/channel-filter-before-80-cap",
            "combined_policy": "single-shared-vector-order-and-shared-80-candidate-cap-no-channel-quota",
            "coverage_warning": "Derived provenance coverage is citation coverage, not retained answer information or semantic entailment. Raw and memory ranks use different item units. Unannotated valid evidence may exist.",
            "source_expansion_executed": False,
            "production_query_engine_executed": False,
            "planner_executed": False,
            "graph_executed": False,
            "reader_executed": False,
            "qa_metrics_available": False,
            "reserved_histories_executed": False,
            "publication_ready": False,
            "aml_academic_model_compliant": False,
            "llm_calls_this_invocation": 0,
            "provider_tokens_this_invocation": 0,
            "record_or_index_writes": 0,
            "schema_initialization_may_run_idempotent_ddl": True,
            "reranker": reranker.provider.report() if reranker else None,
            "rows": rows,
        }
    finally:
        await store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--ingestion-report", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dsn-env", default="DOPPEL_PUBLIC_PILOT_PG_DSN")
    parser.add_argument("--embedding-cache-dir", type=Path)
    parser.add_argument("--reranker-model-path", type=Path)
    parser.add_argument("--reranker-device", default="cuda")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; preserve the prior report")
    dsn = os.environ.get(args.dsn_env, "").strip()
    if not dsn:
        parser.error("database environment variable is absent")
    source = args.dataset.read_bytes()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    cases = select_diagnostic_cases(
        json.loads(source), manifest, source_sha256=hashlib.sha256(source).hexdigest()
    )
    ingestion = json.loads(args.ingestion_report.read_text(encoding="utf-8"))
    ordering = (
        StrictContextReranker(
            LocalContextCrossEncoder(
                args.reranker_model_path, device=args.reranker_device
            )
        )
        if args.reranker_model_path
        else None
    )
    # Never include exception/DSN/provider text in failure artifacts.
    try:
        report = asyncio.run(
            run_comparison(
                cases,
                manifest,
                ingestion,
                run_dir=args.run_dir,
                dsn=dsn,
                embedding_cache_dir=args.embedding_cache_dir,
                reranker=ordering,
            )
        )
    except Exception as error:  # noqa: BLE001 - sanitized diagnostic boundary
        report = {
            "runner": "doppel.public-memory-comparison.v1",
            "status": "failed",
            "failure_type": type(error).__name__,
            "qa_metrics_available": False,
            "publication_ready": False,
        }
    report["input_sha256"] = {
        label: hashlib.sha256(path.read_bytes()).hexdigest()
        for label, path in (
            ("manifest", args.manifest),
            ("ingestion_report", args.ingestion_report),
        )
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(f"output: {args.output.resolve()}")
    print(f"sha256: {hashlib.sha256(args.output.read_bytes()).hexdigest()}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "profile_rows": len(report.get("rows", [])),
                "qa_metrics_available": False,
            }
        )
    )
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
