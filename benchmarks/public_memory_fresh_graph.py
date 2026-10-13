"""Project one closed source scope while the frozen cohort is still partial.

No question, gold or turn label enters selection. Completeness is scope-local;
the original fifty-history ingestion receipt is never relabelled or rewritten.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
from pathlib import Path

from benchmarks.public_memory_comparison import SourceBinding, context_item, inventory
from benchmarks.public_memory_expansion import config, local_diagnostic_dsn, save
from benchmarks.public_memory_fresh_continue import completed_prefix
from benchmarks.public_memory_fresh_ingest import prepare_stage
from benchmarks.public_memory_graph_backfill import execute, writer_lock
from benchmarks.public_memory_graph_consecutive_batch import outside_snapshot
from benchmarks.public_memory_high_config_first import (
    ReadOnlyStore,
    ReadOnlyVectorIndex,
    vector_snapshot,
)
from benchmarks.public_memory_high_config_preflight import (
    _IdentityOnlyEmbedding,
    bound_scopes,
)
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_pilot import _hash
from doppel_memory.graphiti_store import (
    GRAPHITI_PROJECTION_VERSION,
    _graphiti_episode_id,
)
from doppel_memory.indexing import memory_index_fingerprint
from doppel_memory.models import Actor, FactAuthority, MemoryState
from integrations.aml.contract import (
    event_ids,
    memory_scope,
    payload_fingerprint,
    write_key,
)

RUNNER = "doppel.public-memory-fresh-scope-graph.v1"


def scoped_bindings(runtime, manifest, ingestion, ingestion_dir):
    """Verify every original turn and durable stage of this closed scope only."""
    scope = memory_scope(manifest["run_namespace"], runtime.user_id)
    chunks, expected, payloads, events = [], {}, {}, {}
    for chunk in runtime.ingestion_chunks(max_messages=manifest["max_messages"]):
        chunks.append(write_key(scope, chunk.request))
        payloads[chunks[-1]] = payload_fingerprint(chunk.request)
        events[chunks[-1]] = list(event_ids(scope, chunk.request))
        for index, (message, event, turn) in enumerate(
            zip(
                chunk.request.messages,
                event_ids(scope, chunk.request),
                chunk.source_turn_indices,
                strict=True,
            )
        ):
            key = (scope.scope_key, event)
            if key in expected or message.timestamp is None:
                raise ValueError("duplicate or untimed source")
            expected[key] = (
                (chunk.source_session_index, turn),
                message.role,
                message.content,
                message.timestamp,
                chunk.request.session_id,
                index,
            )
    planned = [
        r["write_key"]
        for r in ingestion["plan"]["chunks"]
        if r["scope_key"] == scope.scope_key
    ]
    if chunks != planned:
        raise ValueError("source runtime differs from fixed scope plan")
    uri = (ingestion_dir / "ingestion.sqlite3").resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        writes = db.execute(
            "SELECT * FROM writes WHERE scope=? ORDER BY rowid", (scope.scope_key,)
        ).fetchall()
        observations = db.execute(
            "SELECT a.key,a.diagnostics FROM analysis_observations a JOIN writes w ON a.key=w.key WHERE w.scope=? ORDER BY a.key",
            (scope.scope_key,),
        ).fetchall()
        sources = db.execute(
            "SELECT scope,event,memory FROM sources WHERE scope=? ORDER BY event",
            (scope.scope_key,),
        ).fetchall()
        profile = db.execute(
            "SELECT fingerprint FROM host_profile WHERE id=1"
        ).fetchone()
    if (
        [r[0] for r in writes] != chunks
        or any(r[1] != payloads[r[0]] for r in writes)
        or any(
            r[-1] is None or not r[-2] or any(v is None for v in r[3:6]) for r in writes
        )
        or {r[0] for r in observations} != set(chunks)
        or {(s, e) for s, e, _ in sources} != set(expected)
        or len({m for _, _, m in sources}) != len(expected)
        or profile != (ingestion["audit"]["profile_fingerprint"],)
    ):
        raise ValueError("scope has incomplete or changed source journal")
    source_memories = {event: memory for _, event, memory in sources}
    for row in writes:
        if json.loads(row[3]) != [source_memories[e] for e in events[row[0]]]:
            raise ValueError("raw stage differs from source-to-memory mapping")
        completion = json.loads(row[-1])
        if any(
            completion.get(k) != v
            for k, v in {
                "completed": True,
                "write_key": row[0],
                "scope_key": scope.scope_key,
                "payload_fingerprint": payloads[row[0]],
                "raw_event_count": len(events[row[0]]),
            }.items()
        ):
            raise ValueError("scope completion receipt differs from original source")
    bindings = {(s, e): SourceBinding(m, *expected[(s, e)]) for s, e, m in sources}
    return bindings, {
        "scope_key": scope.scope_key,
        "completed_chunks": len(chunks),
        "source_turns": len(expected),
        "journal_sha256": _hash([writes, observations, sources, profile]),
        "completion_domain": "one-fixed-scope-not-whole-cohort",
        "source_closed": True,
        "all_fifty_histories_ingested_claimed": False,
    }


def closed_source(raw, manifest, cohort, parent, *, source_sha, ordinal, ingestion_dir):
    cases, _ = prepare_stage(raw, manifest, cohort, source_sha=source_sha)
    if type(ordinal) is not int or not 1 <= ordinal <= len(cases):
        raise ValueError("invalid fixed scope ordinal")
    ingestion = parent["ingestion"]
    done = completed_prefix(ingestion, cohort["ingestion_plan"])
    scope = bound_scopes(manifest, ingestion)[ordinal - 1]
    end = max(
        i + 1
        for i, c in enumerate(ingestion["plan"]["chunks"])
        if c["scope_key"] == scope.scope_key
    )
    if done < end:
        raise ValueError("target history is not closed in parent receipt")
    sources, certificate = scoped_bindings(
        cases[ordinal - 1], manifest, ingestion, ingestion_dir
    )
    certificate.update(
        scope_ordinal=ordinal,
        cohort_plan_fingerprint=cohort["plan_fingerprint"],
        ingestion_plan_fingerprint=ingestion["plan"]["plan_fingerprint"],
    )
    return scope, cases[ordinal - 1], sources, certificate


def graph_plan(records, scope, ingestion, certificate, *, max_calls):
    if (
        not 1 <= max_calls <= 1500
        or certificate["scope_key"] != scope.scope_key
        or certificate.get("source_closed") is not True
        or certificate.get("completed_chunks", 0) < 1
        or certificate.get("source_turns", 0) < 1
    ):
        raise ValueError("invalid scope or graph budget")
    if any(r.scope != scope for r in records.values()):
        raise ValueError("inventory escaped closed scope")
    eligible = []
    for record in sorted(records.values(), key=lambda r: (r.created_at, r.memory_id)):
        if (
            "personal-memory" not in record.tags
            or record.state != MemoryState.CONFIRMED
        ):
            continue
        subject = record.metadata.get("subject")
        subject_id = scope.user_id if subject == Actor.OWNER else scope.agent_id
        if (
            subject not in {Actor.OWNER, Actor.AGENT}
            or record.actor != subject
            or record.authority != FactAuthority.of(subject)
            or record.metadata.get("subject_id") != subject_id
            or not record.metadata.get("evidence")
        ):
            raise ValueError("eligible source identity/provenance invalid")
        eligible.append(record)
    if not eligible:
        raise ValueError("no eligible personal graph memories")
    value = {
        "runner": RUNNER,
        "ingestion_plan_fingerprint": ingestion["plan"]["plan_fingerprint"],
        "source_completion_certificate": certificate,
        "corpus_sha256": _hash(
            {k: r.model_dump(mode="json") for k, r in records.items()}
        ),
        "postgres_schema": ingestion["postgres_schema"],
        "selection": "all-confirmed-personal-memories-in-closed-fixed-source-scope/created_at/memory_id",
        "eligible_records": len(eligible),
        "selected_records": len(eligible),
        "max_records": len(eligible),
        "max_calls": max_calls,
        "provider": config(8192).model_dump(mode="json"),
        "embedding": ingestion["embedding"],
        "projection_version": GRAPHITI_PROJECTION_VERSION,
        "max_request_bytes": 500_000,
        "max_total_request_bytes": 32_000_000,
        "records": [
            {
                "memory_id": r.memory_id,
                "scope_key": scope.scope_key,
                "fingerprint": memory_index_fingerprint(r),
                "source_version": r.version,
                "episode_id": _graphiti_episode_id(scope, r.memory_id),
            }
            for r in eligible
        ],
        "implementation_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                Path(__file__),
                Path(__file__).with_name("public_memory_graph_backfill.py"),
                Path(__file__).with_name("graphiti_runtime.py"),
            ]
        },
        "completion_domain": "one-fixed-scope-not-whole-cohort",
        "qa_calls": 0,
    }
    return {**value, "plan_fingerprint": _hash(value)}


async def run(args):
    contents = {
        k: getattr(args, k).read_bytes()
        for k in ["dataset", "manifest", "cohort_plan", "parent_report"]
    }
    raw, manifest, cohort, parent = (
        json.loads(contents[k])
        for k in ["dataset", "manifest", "cohort_plan", "parent_report"]
    )
    scope, runtime, sources, certificate = closed_source(
        raw,
        manifest,
        cohort,
        parent,
        source_sha=hashlib.sha256(contents["dataset"]).hexdigest(),
        ordinal=args.scope_ordinal,
        ingestion_dir=args.ingestion_dir,
    )
    ingestion = parent["ingestion"]
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"),
        schema=ingestion["postgres_schema"],
    )
    try:
        records = await inventory(store, [scope])
        for record in records.values():
            context_item(record, records, sources)
        if (
            sum(r.extractor == "ingestor" for r in records.values())
            != certificate["source_turns"]
        ):
            raise ValueError("scope raw corpus is not complete")
        vector = ReadOnlyVectorIndex(
            store, _IdentityOnlyEmbedding(ingestion["embedding"])
        )
        vectors = await vector_snapshot(store, vector, records, [scope])
        certificate["vectors"] = vectors
        certificate["parent_report_sha256"] = hashlib.sha256(
            contents["parent_report"]
        ).hexdigest()
        plan = graph_plan(
            records, scope, ingestion, certificate, max_calls=args.max_calls
        )
        report = {
            "runner": RUNNER,
            "plan": plan,
            "status": "ready",
            "quality_metrics_available": False,
            "full_corpus_graph_coverage_certified": False,
            "publication_ready": False,
            "scope_ordinal": args.scope_ordinal,
            "store_or_vector_writes": 0,
        }
        scopes = bound_scopes(manifest, ingestion)
        protected = await outside_snapshot(scopes, scope.scope_key)
        if args.live:
            if (
                not args.frozen_preflight
                or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
            ):
                raise ValueError("unchanged frozen scope graph preflight required")
            key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
            if not key:
                raise ValueError("provider key absent")
            with writer_lock(args.run_dir / "writer.lock"):
                _bind_json(args.run_dir / "plan.json", plan)
                result = await execute(
                    store,
                    records,
                    plan,
                    run_dir=args.run_dir,
                    api_key=key,
                    cache_dir=None,
                )
            result["selected_scope_projection_complete"] = result.pop(
                "full_corpus_graph_coverage_certified"
            )
            report.update(result)
        after = await inventory(store, [scope])
        report["corpus_unchanged"] = (
            _hash({k: r.model_dump(mode="json") for k, r in after.items()})
            == plan["corpus_sha256"]
        )
        report["vectors_unchanged"] = (
            await vector_snapshot(store, vector, after, [scope]) == vectors
        )
        report["source_journal_unchanged"] = (
            scoped_bindings(runtime, manifest, ingestion, args.ingestion_dir)[1][
                "journal_sha256"
            ]
            == certificate["journal_sha256"]
        )
        report["other_cohort_graph_scopes_unchanged"] = (
            await outside_snapshot(scopes, scope.scope_key) == protected
        )
        if not all(
            report[k]
            for k in [
                "corpus_unchanged",
                "vectors_unchanged",
                "source_journal_unchanged",
                "other_cohort_graph_scopes_unchanged",
            ]
        ):
            report["status"] = "integrity_failed"
        return report
    finally:
        await store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in [
        "dataset",
        "manifest",
        "cohort-plan",
        "parent-report",
        "ingestion-dir",
        "run-dir",
        "output",
    ]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--scope-ordinal", type=int, default=1)
    parser.add_argument("--max-calls", type=int, default=1500)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve existing receipts")
    result = asyncio.run(run(args))
    save(args.output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "eligible_records": result["plan"]["eligible_records"],
                "completed_records": result.get("completed_records", 0),
                "scope_ordinal": args.scope_ordinal,
                "full_corpus_graph_coverage_certified": False,
            }
        )
    )
    return 0 if result["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
