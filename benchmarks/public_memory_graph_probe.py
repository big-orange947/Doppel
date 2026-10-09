"""Read-only, source-anchored integration checks, never a QA/recall score.

Queries deliberately use stored edge anchors/types. They establish adapter and
provenance connectivity, not natural-language planning or semantic correctness.
No provider or embedder is constructed, and no benchmark question is loaded.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from benchmarks.evidence_rich_blind_diagnostic import local_credentials
from benchmarks.public_memory_comparison import inventory
from benchmarks.public_memory_expansion import local_diagnostic_dsn, save
from benchmarks.public_memory_high_config_preflight import bound_scopes
from benchmarks.public_memory_pilot import _hash
from doppel_memory.graphiti_store import (
    GRAPHITI_FALLBACK_EDGE_NAME,
    GraphitiRelationIndex,
)
from doppel_memory.indexing import memory_index_fingerprint
from doppel_memory.postgres_store import PostgreSQLStore
from doppel_memory.relation import RelationPathQuery, RelationPathStep, RelationQuery


async def probe(index, driver, records, plan, scopes) -> dict:
    checks = []
    for target in plan["records"]:
        record = records[target["memory_id"]]
        if (
            memory_index_fingerprint(record) != target["fingerprint"]
            or record.version != target["source_version"]
            or record.scope.scope_key != target["scope_key"]
        ):
            raise ValueError("probe source differs from frozen backfill target")
        rows, _, _ = await driver.execute_query(
            "MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity) "
            "WHERE r.group_id=$scope AND s.group_id=$scope AND t.group_id=$scope "
            "AND $episode IN coalesce(r.episodes,[]) AND r.name <> $fallback "
            "RETURN r.uuid AS edge_id,r.name AS relation_type,r.fact AS fact, "
            "s.name AS source_name ORDER BY r.uuid",
            scope=record.scope.scope_key,
            episode=target["episode_id"],
            fallback=GRAPHITI_FALLBACK_EDGE_NAME,
        )
        for row in rows:
            common = {
                "query_text": row["fact"],
                "entity_mentions": [row["source_name"]],
                "subject": record.metadata["subject"],
                "subject_id": record.metadata["subject_id"],
            }
            query = RelationQuery(**common, relation_types=[row["relation_type"]])
            hits = await index.search_relations(query, [record.scope], limit=100)
            paths = await index.search_relation_paths(
                RelationPathQuery(
                    **common,
                    steps=[RelationPathStep(relation_types=[row["relation_type"]])],
                ),
                [record.scope],
                limit=100,
            )
            wrong_subject = await index.search_relations(
                query.model_copy(
                    update={"subject_id": common["subject_id"] + ":mismatch"}
                ),
                [record.scope],
                limit=100,
            )
            other = next(s for s in scopes if s.scope_key != record.scope.scope_key)
            cross = await index.search_relations(query, [other], limit=100)
            check = {
                "memory_id": record.memory_id,
                "edge_id": row["edge_id"],
                "relation_returned_with_provenance": any(
                    h.memory_id == record.memory_id
                    and h.edge_id == row["edge_id"]
                    and h.scope == record.scope
                    and target["episode_id"] in h.episode_ids
                    for h in hits
                ),
                "one_hop_path_returned_with_provenance": any(
                    p.scope == record.scope
                    and record.memory_id in p.supporting_memory_ids
                    and any(
                        hop.edge_id == row["edge_id"]
                        and target["episode_id"] in hop.episode_ids
                        for hop in p.hops
                    )
                    for p in paths
                ),
                "wrong_subject_rejected": not wrong_subject,
                "cross_scope_safe": all(
                    h.scope == other and h.memory_id != record.memory_id for h in cross
                ),
            }
            check["ok"] = all(
                value
                for key, value in check.items()
                if key not in {"memory_id", "edge_id"}
            )
            checks.append(check)
    return {
        "runner": "doppel.public-memory-graph-source-probe.v1",
        "status": "complete" if checks and all(c["ok"] for c in checks) else "failed",
        "probe_count": len(checks),
        "checks": checks,
        "query_origin": "stored-edge-source-anchor-and-type",
        "one_hop_only": True,
        "natural_query_performance_measured": False,
        "graph_fact_correctness_measured": False,
        "qa_metrics_available": False,
        "publication_ready": False,
        "provider_calls": 0,
        "data_writes": 0,
    }


async def run(args) -> dict:
    from graphiti_core.driver.neo4j_driver import Neo4jDriver

    class ReadOnlyDriver(Neo4jDriver):
        async def build_indices_and_constraints(self):
            # Default initialization creates schema; this audit does not.
            return None

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    ingestion = json.loads(args.ingestion_report.read_text(encoding="utf-8"))
    backfill = json.loads(args.backfill_report.read_text(encoding="utf-8"))
    plan = backfill["plan"]
    payload = {k: v for k, v in plan.items() if k != "plan_fingerprint"}
    if (
        backfill["status"] != "complete"
        or _hash(payload) != plan["plan_fingerprint"]
        or plan["ingestion_plan_fingerprint"] != ingestion["plan"]["plan_fingerprint"]
    ):
        raise ValueError("completed bound backfill required")
    scopes = bound_scopes(manifest, ingestion)
    _, password, _ = local_credentials()
    driver = ReadOnlyDriver("bolt://127.0.0.1:7687", "neo4j", password)
    store = PostgreSQLStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"), schema=plan["postgres_schema"]
    )
    try:
        records = await inventory(store, scopes)
        before = _hash({k: r.model_dump(mode="json") for k, r in records.items()})
        if before != plan["corpus_sha256"]:
            raise ValueError("probe corpus differs from backfill")
        index = GraphitiRelationIndex(
            store, graphiti_client=SimpleNamespace(driver=driver)
        )
        report = await probe(index, driver, records, plan, scopes)
        after = await inventory(store, scopes)
        report["corpus_unchanged"] = before == _hash(
            {k: r.model_dump(mode="json") for k, r in after.items()}
        )
        report["backfill_plan_fingerprint"] = plan["plan_fingerprint"]
        if not report["corpus_unchanged"]:
            report["status"] = "failed"
        return report
    finally:
        await store.close()
        await driver.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "ingestion-report", "backfill-report", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve prior output")
    report = asyncio.run(run(args))
    save(args.output, report)
    print(
        json.dumps({k: report[k] for k in ("status", "probe_count", "provider_calls")})
    )
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
