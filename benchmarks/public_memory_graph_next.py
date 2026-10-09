"""Project exactly the next full source-order history after a settled receipt.

No questions, answers or scoring labels are loaded. The original two-scope batch
remains immutable; this additive runner binds a single new source-only plan.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from benchmarks.evidence_rich_blind_diagnostic import local_credentials
from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_memory_comparison import inventory
from benchmarks.public_memory_expansion import local_diagnostic_dsn, save
from benchmarks.public_memory_graph_backfill import (
    build_plan,
    execute,
    inspect_projection,
    writer_lock,
)
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
from doppel_memory.graphiti_store import GraphitiSemanticIndex

RUNNER = "doppel.public-memory-next-source-history-graph.v1"


def validate_predecessor(receipt, scopes):
    ordinal = receipt.get("scope_ordinal")
    if type(ordinal) is not int or not 1 <= ordinal < len(scopes):
        raise ValueError("predecessor must identify a diagnostic source ordinal")
    if (
        not all(
            receipt.get(k) is True
            for k in (
                "selected_scope_projection_complete",
                "corpus_unchanged",
                "vectors_unchanged",
                "other_scopes_unchanged",
            )
        )
        or receipt.get("status") != "complete"
    ):
        raise ValueError("settled complete predecessor required")
    graph = receipt["graph_plan"]
    envelope = receipt["plan"]
    for plan in [graph, envelope]:
        if (
            _hash({k: v for k, v in plan.items() if k != "plan_fingerprint"})
            != plan["plan_fingerprint"]
        ):
            raise ValueError("predecessor plan fingerprint mismatch")
    if graph not in envelope["scope_plans"] or graph["scope_ordinal"] != ordinal:
        raise ValueError("predecessor scope plan is not bound to its envelope")
    if {r["scope_key"] for r in graph["records"]} != {scopes[ordinal - 1].scope_key}:
        raise ValueError("predecessor source-order scope mismatch")
    return ordinal


def build_next(records, scopes, ingestion, binding, vectors, predecessor):
    previous = validate_predecessor(predecessor, scopes)
    ordinal = previous + 1
    target = build_plan(
        records, [scopes[ordinal - 1]], ingestion, max_records=10_000, max_calls=1500
    )
    if target["selected_records"] != target["eligible_records"]:
        raise ValueError("complete next-history selection required")
    target.update(
        max_total_request_bytes=32_000_000,
        scope_ordinal=ordinal,
        coverage_domain="one-selected-scope-not-full-corpus",
    )
    target["plan_fingerprint"] = _hash(
        {k: v for k, v in target.items() if k != "plan_fingerprint"}
    )
    if (
        target["corpus_sha256"] != predecessor["plan"]["corpus_sha256"]
        or vectors != predecessor["plan"]["vectors"]
        or predecessor["plan"]["binding"]["manifest"] != binding["manifest"]
        or predecessor["plan"]["binding"]["ingestion"] != binding["ingestion"]
    ):
        raise ValueError("predecessor corpus/vector/source binding changed")
    prior = build_plan(
        records, [scopes[previous - 1]], ingestion, max_records=10_000, max_calls=1500
    )
    if prior["records"] != predecessor["graph_plan"]["records"]:
        raise ValueError("predecessor no longer represents its whole source history")
    envelope = {
        "runner": RUNNER,
        "binding": binding,
        "scope_plans": [target],
        "previous_scope_ordinal": previous,
        "target_scope_ordinal": ordinal,
        "corpus_sha256": target["corpus_sha256"],
        "vectors": vectors,
        "selection": "exact-next-ingestion-scope-after-complete-predecessor-no-question-or-gold",
        "max_calls": 1500,
        "max_total_request_bytes": 32_000_000,
        "publication_ready": False,
        "reserved_histories_executed": False,
        "source_sha256": {
            str(p).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                Path(__file__),
                Path("benchmarks/public_memory_graph_consecutive_batch.py"),
            ]
        },
    }
    return {**envelope, "plan_fingerprint": _hash(envelope)}


async def run(args):
    paths = {
        name: getattr(args, name) for name in ["manifest", "ingestion", "predecessor"]
    }
    content = {k: p.read_bytes() for k, p in paths.items()}
    binding = {k: hashlib.sha256(data).hexdigest() for k, data in content.items()}
    manifest, ingestion, previous = (json.loads(content[k]) for k in paths)
    scopes = bound_scopes(manifest, ingestion)
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"),
        schema=ingestion["postgres_schema"],
    )
    from graphiti_core.driver.neo4j_driver import Neo4jDriver

    class ReadOnlyDriver(Neo4jDriver):
        async def build_indices_and_constraints(self):
            return None

    _, password, _ = local_credentials()
    driver = ReadOnlyDriver("bolt://127.0.0.1:7687", "neo4j", password)
    client = SimpleNamespace(driver=driver)
    try:
        records = await inventory(store, scopes)
        vector = ReadOnlyVectorIndex(
            store, _IdentityOnlyEmbedding(ingestion["embedding"])
        )
        vectors = await vector_snapshot(store, vector, records, scopes)
        plan = build_next(records, scopes, ingestion, binding, vectors, previous)
        index = GraphitiSemanticIndex(store, graphiti_client=client)
        prior_checks = [
            await inspect_projection(client, index, records[r["memory_id"]])
            for r in previous["graph_plan"]["records"]
        ]
        if any(not c["complete"] for c in prior_checks):
            raise ValueError("predecessor graph is no longer complete")
        target = plan["scope_plans"][0]
        ordinal = plan["target_scope_ordinal"]
        scope = scopes[ordinal - 1]
        protected = await outside_snapshot(scopes, scope.scope_key)
        report = {
            "runner": RUNNER,
            "plan": plan,
            "status": "ready",
            "scope_ordinal": ordinal,
            "graph_plan": target,
            "predecessor_projection_count": len(prior_checks),
            "qa_metrics_available": False,
            "publication_ready": False,
            "store_or_vector_writes": 0,
            "reserved_histories_executed": False,
            "protected_snapshot_before": protected,
        }
        if args.live:
            if (
                not args.frozen_preflight
                or json.loads(args.frozen_preflight.read_text("utf-8"))["plan"] != plan
            ):
                raise ValueError("unchanged source-only frozen preflight required")
            key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
            if not key:
                raise ValueError("API key environment absent")
            with writer_lock(args.run_dir / "writer.lock"):
                _bind_json(args.run_dir / "plan.json", target)
                report.update(
                    await execute(
                        store,
                        records,
                        target,
                        run_dir=args.run_dir,
                        api_key=key,
                        cache_dir=args.embedding_cache,
                    )
                )
            report["selected_scope_projection_complete"] = report.pop(
                "full_corpus_graph_coverage_certified"
            )
            report["full_corpus_graph_coverage_certified"] = False
        after = await inventory(store, scopes)
        report["corpus_unchanged"] = (
            _hash({k: r.model_dump(mode="json") for k, r in after.items()})
            == plan["corpus_sha256"]
        )
        report["vectors_unchanged"] = (
            await vector_snapshot(store, vector, after, scopes) == vectors
        )
        report["other_scopes_unchanged"] = (
            await outside_snapshot(scopes, scope.scope_key) == protected
        )
        if not all(
            report[k]
            for k in ["corpus_unchanged", "vectors_unchanged", "other_scopes_unchanged"]
        ):
            report["status"] = "integrity_failed"
        report["execution_metadata"] = execution_metadata()
        return report
    finally:
        await store.close()
        await driver.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["manifest", "ingestion", "predecessor", "run-dir", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--embedding-cache", type=Path)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve earlier receipts")
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
                ]
            }
        )
    )
    return 0 if report["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
