"""Read-only corpus readiness audit before the high-config diagnostic.

No provider, embeddings, graph authoring, ingestion or scoring. A healthy Neo4j
with unrelated fixtures does not establish graph readiness for this corpus.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from benchmarks.evidence_rich_blind_diagnostic import local_credentials
from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_memory_comparison import inventory
from benchmarks.public_memory_expansion import local_diagnostic_dsn, save
from benchmarks.public_memory_pilot import _hash
from doppel_memory.graphiti_store import GRAPHITI_FALLBACK_EDGE_NAME
from doppel_memory.indexing import memory_index_fingerprint
from doppel_memory.models import ACTIVE_MEMORY_STATES, MemoryScope
from doppel_memory.postgres_store import PostgreSQLStore
from doppel_memory.vector import PostgreSQLVectorIndex
from integrations.aml.contract import memory_scope


def bound_scopes(manifest: dict, ingestion: dict) -> list[MemoryScope]:
    plan = ingestion["plan"]
    payload = dict(plan)
    fingerprint = payload.pop("plan_fingerprint")
    if (
        fingerprint != _hash(payload)
        or ingestion["postgres_schema"] != "public_memory_" + fingerprint[:12]
    ):
        raise ValueError("ingestion plan fingerprint/schema mismatch")
    scopes = {}
    for chunk in plan["chunks"]:
        scope = memory_scope(manifest["run_namespace"], chunk["user_id"])
        if scope.scope_key != chunk["scope_key"]:
            raise ValueError("ingestion scope binding mismatch")
        scopes[scope.scope_key] = scope
    if not scopes:
        raise ValueError("ingestion has no scopes")
    expected = {
        case["scope_key"]
        for case in manifest["cases"]
        if case["partition"] == "diagnostic"
    }
    if set(scopes) != expected:
        raise ValueError("scope inventory differs from diagnostic manifest")
    return list(scopes.values())


class _IdentityOnlyEmbedding:
    """Address the existing vector table without loading or invoking a model."""

    def __init__(self, identity: dict) -> None:
        self.name, self.version = identity["name"], identity["version"]
        self.dimensions = identity["dimensions"]

    async def embed(self, texts):
        raise RuntimeError("embedding is forbidden in readiness audit")


async def audit(manifest: dict, ingestion: dict) -> dict:
    if (
        ingestion.get("status") != "complete"
        or ingestion.get("all_histories_ingested") is not True
        or ingestion["plan"]["manifest_fingerprint"] != manifest["manifest_fingerprint"]
        or ingestion["plan"]["run_namespace"] != manifest["run_namespace"]
    ):
        raise ValueError("complete matching ingestion required")
    from neo4j import AsyncGraphDatabase

    _, neo_password, backend = local_credentials()
    store = PostgreSQLStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"),
        schema=ingestion["postgres_schema"],
    )
    graph = AsyncGraphDatabase.driver(
        "bolt://127.0.0.1:7687", auth=("neo4j", neo_password)
    )
    try:
        # Ingestion scope objects, not question labels or benchmark gold metadata.
        scopes = bound_scopes(manifest, ingestion)
        records = await inventory(store, scopes)
        before = _hash({key: r.model_dump(mode="json") for key, r in records.items()})
        index = PostgreSQLVectorIndex(
            store, _IdentityOnlyEmbedding(ingestion["embedding"])
        )
        pool = await store._ensure_pool()
        entries = await pool.fetch(
            f"SELECT memory_id, scope_key, record_fingerprint, source_version FROM {index._table_sql} "
            "WHERE scope_key = ANY($1::text[])",
            [scope.scope_key for scope in scopes],
        )
        vector_entries = {row["memory_id"]: row for row in entries}
        active = {
            key: r for key, r in records.items() if r.state in ACTIVE_MEMORY_STATES
        }
        missing_vectors = set(active).difference(vector_entries)
        extra_vectors = set(vector_entries).difference(active)
        stale_vectors = sum(
            entry["scope_key"] != active[key].scope.scope_key
            or entry["source_version"] != active[key].version
            or entry["record_fingerprint"] != memory_index_fingerprint(active[key])
            for key, entry in vector_entries.items()
            if key in active
        )
        await graph.verify_connectivity()
        counts = {}
        for scope in scopes:
            result, _, _ = await graph.execute_query(
                "MATCH (e:Episodic) WHERE e.group_id=$scope RETURN count(e) AS episodes",
                scope=scope.scope_key,
            )
            edges, _, _ = await graph.execute_query(
                "MATCH ()-[r:RELATES_TO]->() WHERE r.group_id=$scope "
                "AND coalesce(r.name,'') <> $fallback RETURN count(r) AS edges",
                scope=scope.scope_key,
                fallback=GRAPHITI_FALLBACK_EDGE_NAME,
            )
            counts[scope.scope_key] = {
                "episodes": result[0]["episodes"],
                "nonfallback_edges": edges[0]["edges"],
            }
        after = _hash(
            {
                key: r.model_dump(mode="json")
                for key, r in (await inventory(store, scopes)).items()
            }
        )
        if before != after:
            raise RuntimeError("corpus changed during readiness audit")
        missing = sum(count["episodes"] == 0 for count in counts.values())
        return {
            "runner": "doppel.public-memory-high-config-preflight.v1",
            "status": "blocked" if missing else "requires_graph_provenance_audit",
            "backend": backend,
            "scope_count": len(scopes),
            "record_count": len(records),
            "vector_profile": index.identity,
            "vector_entries": len(entries),
            "missing_vectors": len(missing_vectors),
            "unexpected_vectors": len(extra_vectors),
            "stale_vectors": stale_vectors,
            "vector_coverage_verified": not (
                missing_vectors or extra_vectors or stale_vectors
            ),
            "scopes_without_graph_episodes": missing,
            "graph_counts": counts,
            "manifest_fingerprint": manifest["manifest_fingerprint"],
            "ingestion_plan_fingerprint": ingestion["plan"]["plan_fingerprint"],
            "corpus_sha256_before": before,
            "corpus_sha256_after": after,
            "graph_coverage_certified": False,
            "high_config_run_allowed": False,
            "blocker": "corpus_graph_index_absent"
            if missing
            else "graph_provenance_receipt_missing",
            "record_or_index_writes": 0,
            "store_initialization_may_run_idempotent_ddl": True,
            "llm_calls": 0,
            "provider_tokens": 0,
            "qa_metrics_available": False,
            "publication_ready": False,
            "execution_metadata": execution_metadata(),
        }
    finally:
        await graph.close()
        await store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "ingestion-report", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve the prior audit")
    report = asyncio.run(
        audit(
            json.loads(args.manifest.read_text(encoding="utf-8")),
            json.loads(args.ingestion_report.read_text(encoding="utf-8")),
        )
    )
    save(args.output, report)
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "status",
                    "scope_count",
                    "record_count",
                    "scopes_without_graph_episodes",
                    "llm_calls",
                )
            }
        )
    )
    return 0 if report["high_config_run_allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
