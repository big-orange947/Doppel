"""Freeze and project the next two complete ingestion scopes, without questions.

Reuse the production Graphiti writer and durable accounting. Larger explicitly
preregistered byte ceilings avoid the first history's artificial 8 MB stop.
No record selection by answer, no re-ingestion, no synthetic graph fixtures.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from benchmarks.evidence_rich_blind_diagnostic import local_credentials
from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_memory_comparison import inventory
from benchmarks.public_memory_expansion import local_diagnostic_dsn, save
from benchmarks.public_memory_graph_backfill import build_plan, execute, writer_lock
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

RUNNER = "doppel.public-memory-consecutive-graph-batch.v1"


def build_batch(records, scopes, ingestion, binding, vectors):
    if len(scopes) < 3:
        raise ValueError("three fixed ingestion scopes required")
    plans = []
    for ordinal, scope in enumerate(scopes[1:3], 2):
        graph = build_plan(
            records, [scope], ingestion, max_records=10_000, max_calls=1500
        )
        if graph["selected_records"] != graph["eligible_records"]:
            raise ValueError("complete scope selection required")
        graph["max_total_request_bytes"] = 32_000_000
        graph["scope_ordinal"] = ordinal
        graph["coverage_domain"] = "one-selected-scope-not-full-corpus"
        graph["plan_fingerprint"] = _hash(
            {k: v for k, v in graph.items() if k != "plan_fingerprint"}
        )
        plans.append(graph)
    batch = {
        "runner": RUNNER,
        "binding": binding,
        "scope_plans": plans,
        "corpus_sha256": plans[0]["corpus_sha256"],
        "vectors": vectors,
        "selection": "fixed-ingestion-scope-ordinals-2-and-3-no-question-or-gold",
        "max_calls": 3000,
        "max_total_request_bytes": 64_000_000,
        "qa_rule": "natural-V7/evidence-rich-V8/local-BGE-CUDA/raw-and-backing/20-whole-items-24000-bytes/Reader-v2/reference-only-task-judge",
        "qa_calls_per_scope": 5,
        "schema_batch_size": 24,
        "schema_output_cap": 4096,
        "schema_inputs": "distinct-source-relation-names-only",
        "comparison": "existing-fixed-vector-baselines-report-separately-no-merged-protocol-score",
        "reporting_contract": "doppel.high-config-execution-contract.v2",
        "publication_ready": False,
        "reserved_histories_executed": False,
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    return {**batch, "plan_fingerprint": _hash(batch)}


async def outside_snapshot(scopes, selected_scope):
    """Hash all other diagnostic scopes, including their nodes/episodes/edges."""
    from neo4j import AsyncGraphDatabase

    _, password, _ = local_credentials()
    driver = AsyncGraphDatabase.driver(
        "bolt://127.0.0.1:7687", auth=("neo4j", password)
    )
    keys = [s.scope_key for s in scopes if s.scope_key != selected_scope]
    try:
        nodes, _, _ = await driver.execute_query(
            "MATCH (n) WHERE n.group_id IN $scopes RETURN elementId(n) AS id, "
            "labels(n) AS labels, properties(n) AS properties ORDER BY id",
            scopes=keys,
        )
        edges, _, _ = await driver.execute_query(
            "MATCH (s)-[r]->(t) WHERE r.group_id IN $scopes RETURN elementId(r) AS id, "
            "elementId(s) AS source,elementId(t) AS target,type(r) AS type, "
            "properties(r) AS properties ORDER BY id",
            scopes=keys,
        )
        # Neo4j temporal values need deterministic textual conversion for hashes.
        normalized = json.loads(
            json.dumps(
                {"nodes": [dict(n) for n in nodes], "edges": [dict(e) for e in edges]},
                default=str,
                sort_keys=True,
            )
        )
        return {"sha256": _hash(normalized), "nodes": len(nodes), "edges": len(edges)}
    finally:
        await driver.close()


async def run(args):
    paths = {
        "manifest": args.manifest,
        "ingestion": args.ingestion,
        "first_graph_receipt": args.first_graph_receipt,
    }
    contents = {k: p.read_bytes() for k, p in paths.items()}
    binding = {k: hashlib.sha256(v).hexdigest() for k, v in contents.items()}
    manifest, ingestion, first = (
        json.loads(contents[k])
        for k in ["manifest", "ingestion", "first_graph_receipt"]
    )
    scopes = bound_scopes(manifest, ingestion)
    if (
        first["status"] != "complete"
        or not first["corpus_unchanged"]
        or first["plan"]["ingestion_plan_fingerprint"]
        != ingestion["plan"]["plan_fingerprint"]
        or {r["scope_key"] for r in first["plan"]["records"]} != {scopes[0].scope_key}
    ):
        raise ValueError("complete matching first-scope receipt required")
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"),
        schema=ingestion["postgres_schema"],
    )
    try:
        records = await inventory(store, scopes)
        vector = ReadOnlyVectorIndex(
            store, _IdentityOnlyEmbedding(ingestion["embedding"])
        )
        vectors = await vector_snapshot(store, vector, records, scopes)
        batch = build_batch(records, scopes, ingestion, binding, vectors)
        if batch["corpus_sha256"] != first["plan"]["corpus_sha256"]:
            raise ValueError("corpus differs from settled first-history graph")
        report = {
            "runner": RUNNER,
            "plan": batch,
            "status": "ready",
            "qa_metrics_available": False,
            "publication_ready": False,
            "store_or_vector_writes": 0,
            "reserved_histories_executed": False,
        }
        if args.live:
            if (
                not args.frozen_preflight
                or json.loads(args.frozen_preflight.read_text(encoding="utf-8"))["plan"]
                != batch
            ):
                raise ValueError("unchanged frozen source-only batch required")
            key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
            if not key:
                raise ValueError("API key environment absent")
            target = batch["scope_plans"][args.scope_ordinal - 2]
            run_dir = args.run_dir / f"scope-{args.scope_ordinal:02d}"
            protected_before = await outside_snapshot(
                scopes, target["records"][0]["scope_key"]
            )
            with writer_lock(run_dir / "writer.lock"):
                _bind_json(run_dir / "plan.json", target)
                report.update(
                    await execute(
                        store,
                        records,
                        target,
                        run_dir=run_dir,
                        api_key=key,
                        cache_dir=args.embedding_cache,
                    )
                )
            # The existing writer's scoped coverage boolean must not become a
            # fifty-history coverage claim merely because the target is complete.
            report["selected_scope_projection_complete"] = report.pop(
                "full_corpus_graph_coverage_certified"
            )
            report["full_corpus_graph_coverage_certified"] = False
            report["graph_plan"] = target
            report["scope_ordinal"] = args.scope_ordinal
            report["other_scopes_unchanged"] = (
                await outside_snapshot(scopes, target["records"][0]["scope_key"])
                == protected_before
            )
            report["protected_snapshot_before"] = protected_before
        after = await inventory(store, scopes)
        report["corpus_unchanged"] = (
            _hash({k: r.model_dump(mode="json") for k, r in after.items()})
            == batch["corpus_sha256"]
        )
        report["vectors_unchanged"] = (
            await vector_snapshot(store, vector, after, scopes) == vectors
        )
        if any(
            report.get(k) is False
            for k in ["other_scopes_unchanged", "corpus_unchanged", "vectors_unchanged"]
        ):
            report["status"] = "failed"
        report["execution_metadata"] = execution_metadata()
        return report
    finally:
        await store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["manifest", "ingestion", "first-graph-receipt", "run-dir", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--embedding-cache", type=Path)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--scope-ordinal", type=int, choices=[2, 3], default=2)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve previous receipts")
    report = asyncio.run(run(args))
    save(args.output, report)
    print(
        json.dumps(
            {
                k: report.get(k)
                for k in [
                    "status",
                    "scope_ordinal",
                    "completed_records",
                    "failure_type",
                    "budget_stop_reason",
                ]
            }
        )
    )
    return 0 if report["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
