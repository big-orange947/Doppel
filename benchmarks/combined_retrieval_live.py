"""Live end-to-end retrieval over the frozen combined V2 corpus."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from benchmarks.combined_retrieval_quality import (
    CombinedMemory,
    CombinedQuery,
    CombinedRetrievalDataset,
    load_dataset,
)
from benchmarks.personal_relation_path_ablation import (
    _LiveGraphClient,
    _percentile,
    _timestamp,
)
from benchmarks.personal_retrieval_ablation import (
    PG_DATABASE,
    PG_HOST,
    PG_PORT,
    PG_USER,
    _build_vector_candidates,
    _build_vector_index,
    _embedding_runtime_metadata,
    _LocalEmbeddingProvider,
    _probe_postgres,
    _reset_ablation_postgres,
)
from doppel_memory.graphiti_store import (
    GraphitiRelationIndex,
    _graph_query_records,
    _graphiti_episode_name,
)
from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryFilter,
    MemoryRecord,
    MemoryScope,
    MemoryState,
)
from doppel_memory.query import (
    PersonalMemoryQueryConfig,
    PersonalMemoryQueryDraftV2,
    PersonalMemoryQueryEngine,
    PersonalMemoryQueryRequest,
)
from doppel_memory.query_path import PersonalMemoryRelationPathDraftV4
from doppel_memory.relation import RelationPathCandidate, RelationPathExploreQuery
from doppel_memory.relation_path_retrieval import (
    CandidateRelationTopology,
    HybridRetrievalAssembly,
    assemble_hybrid_retrieval_candidates,
    build_relation_path_retrieval_plan,
    merge_relation_path_hits,
    rank_explored_relation_paths,
    search_relation_path_routes,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "benchmarks/datasets/combined-retrieval-zh-v2.json"
DEFAULT_TOPOLOGY = ROOT / "data/doppel/combined-retrieval-v2-topology.json"
DEFAULT_OUTPUT = ROOT / "data/doppel/combined-retrieval-v2-live.json"
RUNNER = "doppel.combined-retrieval-live.v1"
PROFILES = (
    "independent_lexical_vector",
    "typed_path",
    "explored_path",
    "assembled_hybrid",
    "assembled_hybrid_with_exploration",
)
FILTERS = MemoryFilter(
    tags={"personal-memory"},
    states={MemoryState.CONFIRMED},
    exclude_authorities={FactAuthority.AGENT_OUTPUT},
)
RETRIEVAL_THRESHOLDS = {
    "min_evidence_recall_at_5": 0.80,
    "min_complete_evidence_rate_at_10": 0.72,
    "min_one_hop_evidence_recall_at_5": 0.85,
    "min_two_hop_complete_evidence_rate_at_10": 0.65,
    "min_semantic_recall_at_5": 0.75,
    "min_two_hop_complete_gain": 0.05,
    "max_hard_forbidden_hits": 0,
    "max_scope_leakage": 0,
    "max_ineligible_hits": 0,
    "max_orphan_provenance": 0,
    "max_temporal_complete_path_failures": 0,
    "max_store_revalidation_failures": 0,
    "max_path_budget_omissions": 0,
    "max_candidates_per_query": 20,
}
EXPLORATION_THRESHOLDS = {
    "min_two_hop_complete_gain": 0.15,
    "max_hard_forbidden_hits": 0,
    "max_scope_leakage": 0,
    "max_ineligible_hits": 0,
    "max_orphan_provenance": 0,
    "max_temporal_complete_path_failures": 0,
    "max_store_revalidation_failures": 0,
    "max_path_budget_omissions": 0,
    "max_candidates_per_query": 20,
}


class _DatasetPlanner:
    name = "doppel.benchmark.combined-v2-dataset-planner"
    version = "1"

    def __init__(self, case: CombinedQuery, scope: MemoryScope) -> None:
        self.case = case
        self.scope = scope

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraftV2:
        return PersonalMemoryQueryDraftV2(
            operation="lookup",
            temporal_view="as_of",
            search_text=self.case.query,
            entity_mentions=self.case.entity_mentions,
            subject=request.default_subject,
            subject_id=self.scope.user_id,
            as_of=_timestamp(self.case.valid_at),
            confidence=1.0,
            explanation="frozen dataset supplies time and explicit entity anchors",
        )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    result.add_argument("--topology-report", type=Path, default=DEFAULT_TOPOLOGY)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument(
        "--neo4j-uri", default=os.environ.get("DOPPEL_NEO4J_URI", "bolt://127.0.0.1:7687")
    )
    result.add_argument("--neo4j-user", default="neo4j")
    result.add_argument("--neo4j-password-env", default="DOPPEL_NEO4J_PASSWORD")
    result.add_argument(
        "--postgres-password-env", default="DOPPEL_ABLATION_PG_PASSWORD"
    )
    result.add_argument("--embedding-model", default="BAAI/bge-small-zh-v1.5")
    result.add_argument("--embedding-dimensions", type=int, default=512)
    result.add_argument("--embedding-cache-dir", type=Path, default=None)
    result.add_argument("--embedding-batch-size", type=int, default=32)
    result.add_argument(
        "--gate",
        choices=("legacy", "exploration"),
        default="legacy",
        help="quality gate that controls the process exit status",
    )
    return result


def load_topologies(
    path: Path, dataset: CombinedRetrievalDataset
) -> tuple[dict[str, list[CandidateRelationTopology]], dict[str, Any]]:
    report = json.loads(path.read_text("utf-8"))
    binding = dict(report.get("binding") or {})
    if binding.get("dataset_fingerprint") != dataset.fingerprint:
        raise ValueError("topology report dataset fingerprint mismatch")
    acquisition = dict(report.get("acquisition") or {})
    if (
        not acquisition.get("complete")
        or int(acquisition.get("completed_case_count", 0)) != len(dataset.queries)
    ):
        raise ValueError("topology acquisition is incomplete")
    rows = list(report.get("rows") or [])
    if len(rows) != len(dataset.queries):
        raise ValueError("topology report row count mismatch")
    result: dict[str, list[CandidateRelationTopology]] = {}
    for row in rows:
        case_id = str(row.get("case_id") or "")
        if not case_id or case_id in result:
            raise ValueError("topology report case IDs must be unique")
        if row.get("error"):
            result[case_id] = []
            continue
        result[case_id] = [
            CandidateRelationTopology.model_validate(item)
            for item in list(row.get("observed_topologies") or [])
        ]
    if set(result) != {item.case_id for item in dataset.queries}:
        raise ValueError("topology report cases do not match dataset")
    return result, report


async def run_live(
    dataset: CombinedRetrievalDataset,
    topologies: dict[str, list[CandidateRelationTopology]],
    topology_report: dict[str, Any],
    *,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    postgres_password: str,
    embedding_provider: Any,
) -> dict[str, Any]:
    from neo4j import AsyncGraphDatabase  # pyright: ignore[reportMissingImports]

    postgres_reason = await _probe_postgres(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DATABASE,
        user=PG_USER,
        password=postgres_password,
    )
    if postgres_reason:
        raise RuntimeError("postgres runtime unavailable")
    await _reset_ablation_postgres(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DATABASE,
        user=PG_USER,
        password=postgres_password,
    )
    store = await _build_vector_index(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DATABASE,
        user=PG_USER,
        password=postgres_password,
    )
    driver = AsyncGraphDatabase.driver(
        neo4j_uri,
        auth=(neo4j_user, neo4j_password),
        connection_timeout=3.0,
        connection_acquisition_timeout=3.0,
        max_transaction_retry_time=0.0,
    )
    run_id = f"doppel-combined-v2-{uuid4().hex}"
    scopes = {
        name: MemoryScope(
            user_id=f"{item.user_id}:{run_id}", agent_id=item.agent_id
        )
        for name, item in dataset.scopes.items()
    }
    groups = [scope.scope_key for scope in scopes.values()]
    records = [_record(item, scopes[item.scope]) for item in dataset.fixtures]
    records_by_id = {item.memory_id: item for item in records}
    rows_by_profile: dict[str, list[dict[str, Any]]] = {
        name: [] for name in PROFILES
    }
    assembly_totals: Counter[str] = Counter()
    exploration_assembly_totals: Counter[str] = Counter()
    graph_cleaned = False
    postgres_reset = False
    graph_write_attempted = False
    cleanup_errors: list[str] = []
    try:
        await driver.verify_connectivity()
        for record in records:
            result = await store.put(record)
            if not result.accepted:
                raise RuntimeError(f"fixture write failed: {record.memory_id}")
        vector_index = await _build_vector_candidates(
            store, records, embedding_provider
        )
        engine = PersonalMemoryQueryEngine(
            store,
            PersonalMemoryQueryConfig(limit=20, semantic_candidate_limit=100),
            semantic_index=vector_index,
        )
        graph_index = GraphitiRelationIndex(
            store, graphiti_client=_LiveGraphClient(driver)
        )
        graph_write_attempted = True
        await _seed_graph(driver, dataset, run_id=run_id, scopes=scopes, records=records_by_id)

        for case in dataset.queries:
            scope = scopes[case.scope]
            valid_at = _timestamp(case.valid_at)
            base_started = time.perf_counter()
            base_result = await engine.query(
                _DatasetPlanner(case, scope),
                case.query,
                [scope],
                now=max(valid_at, datetime(2026, 9, 24, tzinfo=UTC)),
                default_subject=Actor.OWNER,
                default_subject_id=scope.user_id,
            )
            base_latency = (time.perf_counter() - base_started) * 1000

            path_plan = build_relation_path_retrieval_plan(
                PersonalMemoryRelationPathDraftV4(
                    operation="lookup",
                    temporal_view="as_of",
                    search_text=case.query,
                    entity_mentions=case.entity_mentions,
                    subject=Actor.OWNER,
                    subject_id=scope.user_id,
                    as_of=valid_at,
                    path_decision="abstain",
                    path_reason="nonrelation",
                ),
                candidate_topologies=topologies[case.case_id],
                allowed_relation_types=dataset.relation_types,
            )
            path_started = time.perf_counter()
            path_hits = await search_relation_path_routes(
                graph_index,
                path_plan,
                [scope],
                filters=FILTERS,
                limit=20,
            )
            path_latency = (time.perf_counter() - path_started) * 1000

            exploration_started = time.perf_counter()
            explored_candidates = (
                await graph_index.explore_relation_paths(
                    RelationPathExploreQuery(
                        query_text=case.query,
                        entity_mentions=case.entity_mentions,
                        allowed_relation_types=dataset.relation_types,
                        subject=Actor.OWNER,
                        subject_id=scope.user_id,
                        valid_at=valid_at,
                    ),
                    [scope],
                    filters=FILTERS,
                    limit=20,
                )
                if case.entity_mentions
                else []
            )
            explored_hits = rank_explored_relation_paths(
                explored_candidates, limit=20
            )
            exploration_latency = (
                time.perf_counter() - exploration_started
            ) * 1000
            combined_path_hits = merge_relation_path_hits(
                path_hits, explored_hits, limit=20
            )

            assembly_started = time.perf_counter()
            assembly = await assemble_hybrid_retrieval_candidates(
                store,
                base_result.hits,
                path_hits,
                [scope],
                filters=FILTERS,
                limit=20,
                base_reserve=5,
            )
            assembly_latency = (time.perf_counter() - assembly_started) * 1000
            assembly_totals.update(
                {
                    "rejected_base_hits": assembly.rejected_base_hits,
                    "rejected_path_hits": assembly.rejected_path_hits,
                    "omitted_path_hits": assembly.omitted_path_hits,
                    "truncated_queries": int(assembly.truncated),
                    "retained_paths": len(assembly.relation_paths),
                }
            )
            _record_rejection_reasons(assembly_totals, assembly)

            exploration_assembly_started = time.perf_counter()
            exploration_assembly = await assemble_hybrid_retrieval_candidates(
                store,
                base_result.hits,
                combined_path_hits,
                [scope],
                filters=FILTERS,
                limit=20,
                base_reserve=5,
            )
            exploration_assembly_latency = (
                time.perf_counter() - exploration_assembly_started
            ) * 1000
            exploration_assembly_totals.update(
                {
                    "rejected_base_hits": exploration_assembly.rejected_base_hits,
                    "rejected_path_hits": exploration_assembly.rejected_path_hits,
                    "omitted_path_hits": exploration_assembly.omitted_path_hits,
                    "truncated_queries": int(exploration_assembly.truncated),
                    "retained_paths": len(exploration_assembly.relation_paths),
                }
            )
            _record_rejection_reasons(
                exploration_assembly_totals, exploration_assembly
            )

            base_ids = [hit.record.memory_id for hit in base_result.hits]
            path_ids = list(
                dict.fromkeys(
                    memory_id
                    for hit in path_hits
                    for memory_id in hit.candidate.supporting_memory_ids
                )
            )
            explored_ids = list(
                dict.fromkeys(
                    memory_id
                    for candidate in explored_candidates
                    for memory_id in candidate.supporting_memory_ids
                )
            )
            hybrid_ids = [item.record.memory_id for item in assembly.candidates]
            exploration_hybrid_ids = [
                item.record.memory_id for item in exploration_assembly.candidates
            ]
            for profile, ids, result_scopes, latency, sources, path_returned in (
                (
                    "independent_lexical_vector",
                    base_ids,
                    [hit.record.scope.scope_key for hit in base_result.hits],
                    base_latency,
                    [hit.candidate_evidence.sources for hit in base_result.hits],
                    False,
                ),
                (
                    "typed_path",
                    path_ids,
                    [hit.candidate.scope.scope_key for hit in path_hits],
                    path_latency,
                    [["relation_path"] for _ in path_ids],
                    bool(path_hits),
                ),
                (
                    "explored_path",
                    explored_ids,
                    [candidate.scope.scope_key for candidate in explored_candidates],
                    exploration_latency,
                    [["relation_path:exploration"] for _ in explored_ids],
                    _complete_required_path_returned(case, explored_candidates),
                ),
                (
                    "assembled_hybrid",
                    hybrid_ids,
                    [item.record.scope.scope_key for item in assembly.candidates],
                    base_latency + path_latency + assembly_latency,
                    [item.discovery_sources for item in assembly.candidates],
                    bool(path_hits),
                ),
                (
                    "assembled_hybrid_with_exploration",
                    exploration_hybrid_ids,
                    [
                        item.record.scope.scope_key
                        for item in exploration_assembly.candidates
                    ],
                    base_latency
                    + path_latency
                    + exploration_latency
                    + exploration_assembly_latency,
                    [
                        item.discovery_sources
                        for item in exploration_assembly.candidates
                    ],
                    _complete_required_path_returned(
                        case,
                        [hit.candidate for hit in combined_path_hits],
                    ),
                ),
            ):
                rows_by_profile[profile].append(
                    _row(
                        case,
                        ids=ids,
                        result_scopes=result_scopes,
                        authorized_scope=scope.scope_key,
                        latency_ms=latency,
                        records=records_by_id,
                        sources=sources,
                        complete_path_returned=path_returned,
                    )
                )
    finally:
        try:
            if graph_write_attempted:
                try:
                    await driver.execute_query(
                        "MATCH (node) WHERE node.group_id IN $groups DETACH DELETE node",
                        groups=groups,
                    )
                    raw = await driver.execute_query(
                        "MATCH (node) WHERE node.group_id IN $groups "
                        "RETURN count(node) AS remaining",
                        groups=groups,
                    )
                    found = _graph_query_records(raw)
                    graph_cleaned = bool(
                        found and int(found[0].get("remaining", 0) or 0) == 0
                    )
                except Exception as exc:  # noqa: BLE001
                    cleanup_errors.append(f"neo4j:{type(exc).__name__}")
            else:
                graph_cleaned = True
        finally:
            try:
                await driver.close()
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(f"neo4j-close:{type(exc).__name__}")
            try:
                await store.close()
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(f"postgres-close:{type(exc).__name__}")
            try:
                await _reset_ablation_postgres(
                    host=PG_HOST,
                    port=PG_PORT,
                    database=PG_DATABASE,
                    user=PG_USER,
                    password=postgres_password,
                )
                postgres_reset = True
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(f"postgres-reset:{type(exc).__name__}")

    profiles = {
        name: _summarize(rows) for name, rows in rows_by_profile.items()
    }
    gate = retrieval_quality_gate(
        profiles,
        assembly_totals,
        topology_gate=dict(topology_report.get("quality_gate") or {}),
        graph_cleaned=graph_cleaned,
        postgres_reset=postgres_reset,
    )
    exploration_gate = exploration_quality_gate(
        profiles,
        exploration_assembly_totals,
        graph_cleaned=graph_cleaned,
        postgres_reset=postgres_reset,
    )
    return {
        "result_schema_version": 1,
        "runner": RUNNER,
        "dataset": {
            "suite": dataset.suite,
            "version": dataset.version,
            "fingerprint": dataset.fingerprint,
            "scopes": len(dataset.scopes),
            "memories": len(dataset.fixtures),
            "queries": len(dataset.queries),
            "frozen": dataset.frozen,
            "publication_ready": dataset.publication_ready,
        },
        "topology": {
            "report_sha256": _fingerprint(topology_report),
            "quality_gate": topology_report.get("quality_gate"),
            "metrics": topology_report.get("metrics"),
        },
        "runtime": {
            "store": "postgresql",
            "vector": "pgvector",
            "graph": "neo4j_graphiti_relation_path",
            "embedding": _embedding_runtime_metadata(embedding_provider),
            "llm_calls": 0,
            "external_http_calls": 0,
            "provider_tokens": 0,
            "credentials_persisted": False,
            "neo4j_cleanup_performed": graph_cleaned,
            "postgres_cleanup_performed": postgres_reset,
            "cleanup_errors": cleanup_errors,
        },
        "profiles": profiles,
        "assembly": dict(assembly_totals),
        "exploration_assembly": dict(exploration_assembly_totals),
        "gain": {
            "evidence_recall_at_5": round(
                profiles["assembled_hybrid"]["evidence_recall_at_5"]
                - profiles["independent_lexical_vector"]["evidence_recall_at_5"],
                6,
            ),
            "complete_evidence_rate_at_10": round(
                profiles["assembled_hybrid"]["complete_evidence_rate_at_10"]
                - profiles["independent_lexical_vector"][
                    "complete_evidence_rate_at_10"
                ],
                6,
            ),
            "two_hop_complete_evidence_rate_at_10": round(
                profiles["assembled_hybrid"]["by_category"]["two_hop_relation"][
                    "complete_evidence_rate_at_10"
                ]
                - profiles["independent_lexical_vector"]["by_category"][
                    "two_hop_relation"
                ]["complete_evidence_rate_at_10"],
                6,
            ),
        },
        "exploration_gain": {
            "evidence_recall_at_5_vs_typed_hybrid": round(
                profiles["assembled_hybrid_with_exploration"][
                    "evidence_recall_at_5"
                ]
                - profiles["assembled_hybrid"]["evidence_recall_at_5"],
                6,
            ),
            "complete_evidence_rate_at_10_vs_typed_hybrid": round(
                profiles["assembled_hybrid_with_exploration"][
                    "complete_evidence_rate_at_10"
                ]
                - profiles["assembled_hybrid"]["complete_evidence_rate_at_10"],
                6,
            ),
            "two_hop_complete_rate_at_10_vs_typed_hybrid": round(
                profiles["assembled_hybrid_with_exploration"]["by_category"][
                    "two_hop_relation"
                ]["complete_evidence_rate_at_10"]
                - profiles["assembled_hybrid"]["by_category"][
                    "two_hop_relation"
                ]["complete_evidence_rate_at_10"],
                6,
            ),
        },
        "exploration_gate": exploration_gate,
        "gate": gate,
    }


def _complete_required_path_returned(
    case: CombinedQuery, candidates: Sequence[RelationPathCandidate]
) -> bool:
    """Evaluate complete structural coverage without treating partial paths as proof."""

    required = {
        tuple(
            (tuple(step.relation_types), step.direction)
            for step in route
        )
        for route in case.required_routes
    }
    if not required:
        return False
    observed = {
        tuple(((hop.relation_type,), hop.direction) for hop in candidate.hops)
        for candidate in candidates
    }
    return bool(required.intersection(observed))


def _record(item: CombinedMemory, scope: MemoryScope) -> MemoryRecord:
    valid_from = _timestamp(item.valid_from)
    return MemoryRecord(
        memory_id=item.memory_id,
        scope=scope,
        kind="fact",
        content=item.content,
        actor=Actor.AGENT if item.authority == "agent_output" else Actor.OWNER,
        authority=FactAuthority(item.authority),
        state=MemoryState(item.state),
        tags=item.tags,
        extractor="benchmark.combined-v2",
        created_at=valid_from,
        updated_at=valid_from,
        metadata={
            "subject": Actor.OWNER,
            "subject_id": scope.user_id,
            "temporal_status": "historical" if item.valid_to else "current",
            "valid_from": item.valid_from,
            "valid_to": item.valid_to or None,
            "evidence": [{"evidence_id": item.evidence_id}],
        },
    )


async def _seed_graph(
    driver: Any,
    dataset: CombinedRetrievalDataset,
    *,
    run_id: str,
    scopes: dict[str, MemoryScope],
    records: dict[str, MemoryRecord],
) -> None:
    nodes = [
        {
            "uuid": f"{run_id}:{item.entity_id}",
            "name": item.name,
            "group_id": scopes[item.scope].scope_key,
        }
        for item in dataset.entities
    ]
    episodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for item in dataset.edges:
        record = records[item.memory_id]
        episode_id = f"{run_id}:episode:{item.edge_id}"
        episodes.append(
            {
                "uuid": episode_id,
                "name": _graphiti_episode_name(
                    item.memory_id, "e" * 64, record.version
                ),
                "group_id": record.scope.scope_key,
            }
        )
        edges.append(
            {
                "source_uuid": f"{run_id}:{item.source_entity_id}",
                "target_uuid": f"{run_id}:{item.target_entity_id}",
                "group_id": scopes[item.scope].scope_key,
                "uuid": f"{run_id}:{item.edge_id}",
                "name": item.relation_type,
                "fact": item.fact,
                "episodes": [episode_id],
                "valid_at": _timestamp(item.valid_at),
                "invalid_at": _timestamp(item.invalid_at),
                "created_at": _timestamp(item.valid_at),
            }
        )
    await driver.execute_query(
        "UNWIND $nodes AS item CREATE (:Entity {uuid: item.uuid, "
        "name: item.name, group_id: item.group_id})",
        nodes=nodes,
    )
    await driver.execute_query(
        "UNWIND $episodes AS item CREATE (:Episodic {uuid: item.uuid, "
        "name: item.name, group_id: item.group_id})",
        episodes=episodes,
    )
    await driver.execute_query(
        "UNWIND $edges AS item "
        "MATCH (source:Entity {uuid: item.source_uuid, group_id: item.group_id}) "
        "MATCH (target:Entity {uuid: item.target_uuid, group_id: item.group_id}) "
        "CREATE (source)-[edge:RELATES_TO]->(target) "
        "SET edge.group_id = item.group_id, edge.uuid = item.uuid, "
        "edge.name = item.name, edge.fact = item.fact, "
        "edge.episodes = item.episodes, edge.valid_at = item.valid_at, "
        "edge.invalid_at = item.invalid_at, edge.created_at = item.created_at",
        edges=edges,
    )


def _row(
    case: CombinedQuery,
    *,
    ids: list[str],
    result_scopes: list[str],
    authorized_scope: str,
    latency_ms: float,
    records: dict[str, MemoryRecord],
    sources: list[list[str]],
    complete_path_returned: bool,
) -> dict[str, Any]:
    valid_at = _timestamp(case.valid_at)
    ineligible = 0
    orphan = 0
    estimated_characters = 0
    for memory_id in ids:
        record = records.get(memory_id)
        if record is None:
            orphan += 1
            continue
        estimated_characters += len(record.content)
        if (
            record.scope.scope_key != authorized_scope
            or record.state is not MemoryState.CONFIRMED
            or record.authority is FactAuthority.AGENT_OUTPUT
            or _timestamp(str(record.metadata.get("valid_from") or "")) > valid_at
            or (
                record.metadata.get("valid_to")
                and _timestamp(str(record.metadata["valid_to"])) < valid_at
            )
        ):
            ineligible += 1
    return {
        "case_id": case.case_id,
        "category": case.category,
        "partition": case.partition,
        "ids": ids,
        "required": case.required_memory_ids,
        "related": case.related_memory_ids,
        "hard_forbidden": case.hard_forbidden_memory_ids,
        "answerable": case.answerable,
        "scope_leakage": sum(item != authorized_scope for item in result_scopes),
        "ineligible_hits": ineligible,
        "orphan_provenance": orphan,
        "latency_ms": latency_ms,
        "estimated_context_characters": estimated_characters,
        "sources": sources,
        "complete_path_returned": complete_path_returned,
    }


def _summarize(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    required_total = required_at_5 = complete_at_10 = answerable = 0
    hard_forbidden = related_hits = scope_leakage = ineligible = orphan = 0
    temporal_path_failures = 0
    reciprocal_ranks: list[float] = []
    candidate_counts: list[int] = []
    context_characters: list[int] = []
    latencies: list[float] = []
    source_counts: Counter[str] = Counter()
    details: list[dict[str, Any]] = []
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["category"]].append(row)
        required = set(row["required"])
        at_5 = set(row["ids"][:5])
        at_10 = set(row["ids"][:10])
        required_total += len(required)
        required_at_5 += len(required & at_5)
        if row["answerable"]:
            answerable += 1
            complete_at_10 += int(required.issubset(at_10))
        first_rank = next(
            (index for index, item in enumerate(row["ids"], start=1) if item in required),
            0,
        )
        if required:
            reciprocal_ranks.append(1 / first_rank if first_rank else 0.0)
        hard_forbidden += len(set(row["ids"]) & set(row["hard_forbidden"]))
        related_hits += len(set(row["ids"]) & set(row["related"]))
        scope_leakage += int(row["scope_leakage"])
        ineligible += int(row["ineligible_hits"])
        orphan += int(row["orphan_provenance"])
        temporal_path_failures += int(
            row["category"] == "temporal_incomplete_path"
            and row["complete_path_returned"]
        )
        candidate_counts.append(len(row["ids"]))
        context_characters.append(int(row["estimated_context_characters"]))
        latencies.append(float(row["latency_ms"]))
        for names in row["sources"]:
            source_counts.update(names)
        details.append(
            {
                "case_id": row["case_id"],
                "ids": row["ids"],
                "missing_at_5": sorted(required - at_5),
                "missing_at_10": sorted(required - at_10),
                "hard_forbidden_hits": sorted(
                    set(row["ids"]) & set(row["hard_forbidden"])
                ),
                "related_hits": sorted(set(row["ids"]) & set(row["related"])),
            }
        )
    summary = {
        "queries": len(rows),
        "answerable_queries": answerable,
        "required_evidence": required_total,
        "evidence_recall_at_5": _ratio(required_at_5, required_total),
        "complete_evidence_rate_at_10": _ratio(complete_at_10, answerable),
        "mrr": round(statistics.mean(reciprocal_ranks), 6)
        if reciprocal_ranks
        else 1.0,
        "hard_forbidden_hits": hard_forbidden,
        "related_context_hits": related_hits,
        "scope_leakage": scope_leakage,
        "ineligible_hits": ineligible,
        "orphan_provenance": orphan,
        "temporal_complete_path_failures": temporal_path_failures,
        "max_candidates": max(candidate_counts, default=0),
        "average_candidates": round(statistics.mean(candidate_counts), 6),
        "average_context_characters": round(
            statistics.mean(context_characters), 6
        ),
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
        },
        "source_attribution": dict(sorted(source_counts.items())),
        "details": details,
    }
    summary["by_category"] = {
        name: _summarize_category(items) for name, items in sorted(grouped.items())
    }
    return summary


def _summarize_category(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    required_total = sum(len(row["required"]) for row in rows)
    required_at_5 = sum(
        len(set(row["required"]) & set(row["ids"][:5])) for row in rows
    )
    answerable = [row for row in rows if row["answerable"]]
    complete = sum(
        set(row["required"]).issubset(set(row["ids"][:10])) for row in answerable
    )
    return {
        "queries": len(rows),
        "evidence_recall_at_5": _ratio(required_at_5, required_total),
        "complete_evidence_rate_at_10": _ratio(complete, len(answerable)),
    }


def retrieval_quality_gate(
    profiles: dict[str, dict[str, Any]],
    assembly: Counter[str],
    *,
    topology_gate: dict[str, Any],
    graph_cleaned: bool,
    postgres_reset: bool,
) -> dict[str, Any]:
    base = profiles["independent_lexical_vector"]
    hybrid = profiles["assembled_hybrid"]
    checks = {
        "topology_gate": topology_gate.get("passed") is True,
        "evidence_recall_at_5": hybrid["evidence_recall_at_5"]
        >= RETRIEVAL_THRESHOLDS["min_evidence_recall_at_5"],
        "complete_evidence_rate_at_10": hybrid["complete_evidence_rate_at_10"]
        >= RETRIEVAL_THRESHOLDS["min_complete_evidence_rate_at_10"],
        "one_hop_evidence_recall_at_5": hybrid["by_category"][
            "one_hop_relation"
        ]["evidence_recall_at_5"]
        >= RETRIEVAL_THRESHOLDS["min_one_hop_evidence_recall_at_5"],
        "two_hop_complete_evidence_rate_at_10": hybrid["by_category"][
            "two_hop_relation"
        ]["complete_evidence_rate_at_10"]
        >= RETRIEVAL_THRESHOLDS["min_two_hop_complete_evidence_rate_at_10"],
        "semantic_recall_at_5": hybrid["by_category"]["semantic_nonrelation"][
            "evidence_recall_at_5"
        ]
        >= RETRIEVAL_THRESHOLDS["min_semantic_recall_at_5"],
        "hybrid_recall_non_regression": hybrid["evidence_recall_at_5"]
        >= base["evidence_recall_at_5"],
        "hybrid_complete_non_regression": hybrid["complete_evidence_rate_at_10"]
        >= base["complete_evidence_rate_at_10"],
        "two_hop_complete_gain": (
            hybrid["by_category"]["two_hop_relation"][
                "complete_evidence_rate_at_10"
            ]
            - base["by_category"]["two_hop_relation"][
                "complete_evidence_rate_at_10"
            ]
        )
        >= RETRIEVAL_THRESHOLDS["min_two_hop_complete_gain"],
        "hard_forbidden_hits": hybrid["hard_forbidden_hits"] == 0,
        "scope_leakage": hybrid["scope_leakage"] == 0,
        "ineligible_hits": hybrid["ineligible_hits"] == 0,
        "orphan_provenance": hybrid["orphan_provenance"] == 0,
        "temporal_complete_path_failures": hybrid[
            "temporal_complete_path_failures"
        ]
        == 0,
        "store_revalidation_failures": _store_revalidation_failures(assembly)
        == 0,
        "path_budget_omissions": assembly["omitted_path_hits"] == 0,
        "candidate_bound": hybrid["max_candidates"]
        <= RETRIEVAL_THRESHOLDS["max_candidates_per_query"],
        "neo4j_cleanup": graph_cleaned,
        "postgres_cleanup": postgres_reset,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "thresholds": RETRIEVAL_THRESHOLDS,
    }


def exploration_quality_gate(
    profiles: dict[str, dict[str, Any]],
    assembly: Counter[str],
    *,
    graph_cleaned: bool,
    postgres_reset: bool,
) -> dict[str, Any]:
    """Gate additive exploration against the already-opened typed-only baseline."""

    typed = profiles["assembled_hybrid"]
    explored = profiles["assembled_hybrid_with_exploration"]
    two_hop_gain = (
        explored["by_category"]["two_hop_relation"][
            "complete_evidence_rate_at_10"
        ]
        - typed["by_category"]["two_hop_relation"][
            "complete_evidence_rate_at_10"
        ]
    )
    checks = {
        "recall_non_regression": explored["evidence_recall_at_5"]
        >= typed["evidence_recall_at_5"],
        "complete_evidence_non_regression": explored[
            "complete_evidence_rate_at_10"
        ]
        >= typed["complete_evidence_rate_at_10"],
        "semantic_non_regression": explored["by_category"][
            "semantic_nonrelation"
        ]["evidence_recall_at_5"]
        >= typed["by_category"]["semantic_nonrelation"]["evidence_recall_at_5"],
        "two_hop_complete_gain": two_hop_gain
        >= EXPLORATION_THRESHOLDS["min_two_hop_complete_gain"],
        "hard_forbidden_hits": explored["hard_forbidden_hits"] == 0,
        "scope_leakage": explored["scope_leakage"] == 0,
        "ineligible_hits": explored["ineligible_hits"] == 0,
        "orphan_provenance": explored["orphan_provenance"] == 0,
        "temporal_complete_path_failures": explored[
            "temporal_complete_path_failures"
        ]
        == 0,
        "store_revalidation_failures": _store_revalidation_failures(assembly)
        == 0,
        "path_budget_omissions": assembly["omitted_path_hits"] == 0,
        "candidate_bound": explored["max_candidates"]
        <= EXPLORATION_THRESHOLDS["max_candidates_per_query"],
        "neo4j_cleanup": graph_cleaned,
        "postgres_cleanup": postgres_reset,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "thresholds": EXPLORATION_THRESHOLDS,
        "two_hop_complete_gain": round(two_hop_gain, 6),
        "legacy_topology_gate_required": False,
    }


def _record_rejection_reasons(
    totals: Counter[str], assembly: HybridRetrievalAssembly
) -> None:
    for reason, count in assembly.rejected_base_reasons.items():
        totals[f"rejected_base_{reason}"] += count
    for reason, count in assembly.rejected_path_reasons.items():
        totals[f"rejected_path_{reason}"] += count


def _store_revalidation_failures(assembly: Counter[str]) -> int:
    """Count stale/orphan Store reads, not successful policy enforcement."""

    return sum(
        assembly[f"rejected_{source}_{reason}"]
        for source in ("base", "path")
        for reason in ("store_missing", "scope_mismatch")
    )


async def _main_async(args: argparse.Namespace) -> int:
    dataset = load_dataset(args.dataset)
    topologies, topology_report = load_topologies(args.topology_report, dataset)
    neo4j_password = os.environ.get(args.neo4j_password_env, "")
    postgres_password = os.environ.get(args.postgres_password_env, "")
    if not neo4j_password or not postgres_password:
        raise RuntimeError("both local backend password variables are required")
    provider = _LocalEmbeddingProvider(
        args.embedding_model,
        dimensions=args.embedding_dimensions,
        cache_dir=args.embedding_cache_dir,
        batch_size=args.embedding_batch_size,
    )
    try:
        await provider.warmup()
        report = await run_live(
            dataset,
            topologies,
            topology_report,
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=neo4j_password,
            postgres_password=postgres_password,
            embedding_provider=provider,
        )
    except Exception as exc:  # noqa: BLE001
        report = {
            "result_schema_version": 1,
            "runner": RUNNER,
            "dataset": {"suite": dataset.suite, "fingerprint": dataset.fingerprint},
            "hard_failure": type(exc).__name__,
            "runtime": {
                "llm_calls": 0,
                "external_http_calls": 0,
                "provider_tokens": 0,
                "credentials_persisted": False,
            },
            "gate": {"ok": False, "failures": ["runtime_unavailable"]},
        }
    report["report_sha256"] = _fingerprint(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if _selected_gate_passed(report, args.gate) else 1


def _selected_gate_passed(report: dict[str, Any], gate: str) -> bool:
    key = "exploration_gate" if gate == "exploration" else "gate"
    selected = report.get(key)
    return isinstance(selected, dict) and selected.get("ok") is True


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 1.0


def _fingerprint(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def main() -> int:
    return asyncio.run(_main_async(parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
