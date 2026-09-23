"""Live lexical/pgvector plus typed-path candidate assembly ablation.

This opened development benchmark reuses the 36-case relation-path dataset.  It is
not a natural-language path-generation score: exact and candidate topologies come from
the dataset so the run can isolate whether the bounded assembly layer adds useful
evidence without weakening scope, time, provenance, or independent retrieval.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from benchmarks.candidate_relation_path_ablation import (
    CandidatePathDataset,
    _draft,
    _summarize_profile,
    load_dataset,
)
from benchmarks.personal_relation_path_ablation import (
    _LiveGraphClient,
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
    utc_now,
)
from doppel_memory.query import (
    PersonalMemoryQueryConfig,
    PersonalMemoryQueryDraftV2,
    PersonalMemoryQueryEngine,
    PersonalMemoryQueryRequest,
)
from doppel_memory.relation_path_retrieval import (
    assemble_hybrid_retrieval_candidates,
    build_relation_path_retrieval_plan,
    search_relation_path_routes,
)

RUNNER = "doppel.hybrid-path-candidate-ablation.v2"
PROFILES = ("independent_lexical_vector", "typed_path", "assembled_union")
FILTERS = MemoryFilter(
    tags={"personal-memory"},
    states={MemoryState.CONFIRMED},
    exclude_authorities={FactAuthority.AGENT_OUTPUT},
)


class _DatasetPlanner:
    """Oracle time/entity projection used only to isolate retrieval assembly."""

    name = "doppel.benchmark.hybrid-path-dataset-planner"
    version = "1"

    def __init__(self, *, query: str, entity_mentions: list[str], valid_at: Any) -> None:
        self.query = query
        self.entity_mentions = entity_mentions
        self.valid_at = valid_at

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraftV2:
        return PersonalMemoryQueryDraftV2(
            operation="lookup",
            temporal_view="as_of",
            search_text=self.query,
            entity_mentions=self.entity_mentions,
            subject=request.default_subject,
            subject_id=request.default_subject_id,
            as_of=self.valid_at,
            confidence=1.0,
            explanation="benchmark-provided time and entity anchors",
        )


def _record(item: Any, scope: MemoryScope) -> MemoryRecord:
    valid_from = _timestamp(item.valid_from)
    created_at = valid_from or utc_now()
    metadata: dict[str, Any] = {
        "subject": Actor.OWNER,
        "subject_id": scope.user_id,
        "temporal_status": "current",
        "evidence": [{"evidence_id": f"dataset:{item.memory_id}"}],
    }
    if item.valid_from:
        metadata["valid_from"] = item.valid_from
    if item.valid_to:
        metadata["valid_to"] = item.valid_to
        metadata["temporal_status"] = "historical"
    return MemoryRecord(
        memory_id=item.memory_id,
        scope=scope,
        kind="fact",
        content=item.content,
        actor=Actor.OWNER,
        authority=FactAuthority.HUMAN_SELF,
        state=MemoryState.CONFIRMED,
        tags=["personal-memory"],
        extractor="benchmark.hybrid-path",
        created_at=created_at,
        updated_at=created_at,
        metadata=metadata,
    )


async def run_ablation(
    dataset: CandidatePathDataset,
    *,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    postgres_password: str,
    embedding_provider: Any,
) -> dict[str, Any]:
    """Run all three profiles on the same authoritative Store and live graph."""

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
    run_id = f"doppel-hybrid-path-{uuid4().hex}"
    driver = AsyncGraphDatabase.driver(
        neo4j_uri,
        auth=(neo4j_user, neo4j_password),
        connection_timeout=3.0,
        connection_acquisition_timeout=3.0,
        max_transaction_retry_time=0.0,
    )
    scope_by_name = {
        name: MemoryScope(user_id=f"{scope.user_id}:{run_id}", agent_id=scope.agent_id)
        for name, scope in dataset.scopes.items()
    }
    groups = [scope.scope_key for scope in scope_by_name.values()]
    records = [_record(item, scope_by_name[item.scope]) for item in dataset.fixtures]
    record_by_id = {record.memory_id: record for record in records}
    profile_rows: dict[str, list[dict[str, Any]]] = {
        profile: [] for profile in PROFILES
    }
    assembly_totals = {
        "rejected_base_hits": 0,
        "rejected_path_hits": 0,
        "omitted_path_hits": 0,
        "truncated_queries": 0,
        "retained_paths": 0,
    }
    cleanup_errors: list[str] = []
    graph_cleaned = False
    postgres_reset = False
    fixture_write_attempted = False
    try:
        await driver.verify_connectivity()
        for record in records:
            result = await store.put(record)
            if not result.accepted:
                raise RuntimeError(f"fixture write failed: {record.memory_id}")
        vector_index = await _build_vector_candidates(store, records, embedding_provider)
        query_engine = PersonalMemoryQueryEngine(
            store,
            PersonalMemoryQueryConfig(limit=20, semantic_candidate_limit=100),
            semantic_index=vector_index,
        )
        relation_index = GraphitiRelationIndex(
            store, graphiti_client=_LiveGraphClient(driver)
        )
        fixture_write_attempted = True
        await _seed_graph(
            driver,
            dataset=dataset,
            run_id=run_id,
            scopes=scope_by_name,
            records=record_by_id,
        )

        for case in dataset.queries:
            scope = scope_by_name[case.scope]
            valid_at = _timestamp(case.valid_at)
            planner = _DatasetPlanner(
                query=case.query,
                entity_mentions=case.entity_mentions,
                valid_at=valid_at,
            )
            base_started = time.perf_counter()
            base_result = await query_engine.query(
                planner,
                case.query,
                [scope],
                now=max(valid_at, utc_now()),
                default_subject=Actor.OWNER,
                default_subject_id=scope.user_id,
            )
            base_latency = (time.perf_counter() - base_started) * 1000

            plan = build_relation_path_retrieval_plan(
                _draft(case, scope),
                candidate_topologies=case.candidate_topologies,
                allowed_relation_types=dataset.relation_types,
            )
            path_started = time.perf_counter()
            path_hits = await search_relation_path_routes(
                relation_index,
                plan,
                [scope],
                filters=FILTERS,
                limit=20,
            )
            path_latency = (time.perf_counter() - path_started) * 1000

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
            assembly_totals["rejected_base_hits"] += assembly.rejected_base_hits
            assembly_totals["rejected_path_hits"] += assembly.rejected_path_hits
            assembly_totals["omitted_path_hits"] += assembly.omitted_path_hits
            assembly_totals["truncated_queries"] += int(assembly.truncated)
            assembly_totals["retained_paths"] += len(assembly.relation_paths)

            base_ids = [hit.record.memory_id for hit in base_result.hits]
            path_ids = list(
                dict.fromkeys(
                    memory_id
                    for hit in path_hits
                    for memory_id in hit.candidate.supporting_memory_ids
                )
            )
            assembled_ids = [item.record.memory_id for item in assembly.candidates]
            hard_forbidden, related_incomplete = _hybrid_retrieval_labels(
                case,
                records=record_by_id,
                scope=scope,
                valid_at=valid_at,
            )
            for profile, memory_ids, scope_keys, latency, route_queries in (
                (
                    "independent_lexical_vector",
                    base_ids,
                    [hit.record.scope.scope_key for hit in base_result.hits],
                    base_latency,
                    0,
                ),
                (
                    "typed_path",
                    path_ids,
                    [hit.candidate.scope.scope_key for hit in path_hits],
                    path_latency,
                    len(plan.routes),
                ),
                (
                    "assembled_union",
                    assembled_ids,
                    [item.record.scope.scope_key for item in assembly.candidates],
                    base_latency + path_latency + assembly_latency,
                    len(plan.routes),
                ),
            ):
                profile_rows[profile].append(
                    _metric_row(
                        case,
                        memory_ids=memory_ids,
                        scope_keys=scope_keys,
                        authorized_scope_key=scope.scope_key,
                        graph_route_queries=route_queries,
                        latency_ms=latency,
                        forbidden_memory_ids=hard_forbidden,
                        candidate_noise_memory_ids=related_incomplete,
                    )
                )
    finally:
        try:
            if fixture_write_attempted:
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
                    rows = _graph_query_records(raw)
                    graph_cleaned = bool(
                        rows and int(rows[0].get("remaining", 0) or 0) == 0
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

    profiles = {name: _summarize_profile(rows) for name, rows in profile_rows.items()}
    base = profiles["independent_lexical_vector"]
    path = profiles["typed_path"]
    assembled = profiles["assembled_union"]
    failures: list[str] = []
    if assembled["evidence_recall"] < max(
        base["evidence_recall"], path["evidence_recall"]
    ):
        failures.append("assembled_evidence_recall_regression")
    if assembled["complete_evidence_rate"] < max(
        base["complete_evidence_rate"], path["complete_evidence_rate"]
    ):
        failures.append("assembled_complete_evidence_regression")
    for field in ("forbidden_hits", "scope_leakage"):
        if assembled[field]:
            failures.append(field)
    if assembly_totals["rejected_base_hits"]:
        failures.append("base_revalidation_rejections")
    if assembly_totals["rejected_path_hits"]:
        failures.append("path_revalidation_rejections")
    if assembly_totals["omitted_path_hits"]:
        failures.append("path_budget_omissions")
    if not graph_cleaned:
        failures.append("neo4j_cleanup")
    if not postgres_reset:
        failures.append("postgres_cleanup")
    return {
        "result_schema_version": 2,
        "runner": RUNNER,
        "dataset": {
            "suite": dataset.suite,
            "version": dataset.suite_version,
            "fingerprint": dataset.fingerprint,
            "queries": len(dataset.queries),
            "frozen": dataset.frozen,
            "publication_ready": dataset.publication_ready,
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
        "assembly": assembly_totals,
        "label_contract": {
            "hard_forbidden": (
                "wrong scope, inactive time, disallowed authority/lifecycle, or "
                "missing authoritative memory provenance"
            ),
            "related_incomplete": (
                "active authoritative memory that is insufficient to prove a full path"
            ),
        },
        "gain": {
            "vs_independent_evidence_recall": round(
                assembled["evidence_recall"] - base["evidence_recall"], 6
            ),
            "vs_path_evidence_recall": round(
                assembled["evidence_recall"] - path["evidence_recall"], 6
            ),
            "vs_independent_complete_evidence": round(
                assembled["complete_evidence_rate"]
                - base["complete_evidence_rate"],
                6,
            ),
        },
        "gate": {"ok": not failures, "failures": failures},
    }


async def _seed_graph(
    driver: Any,
    *,
    dataset: CandidatePathDataset,
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
        episode_id = f"{run_id}:episode:{item.edge_id}"
        if item.memory_id:
            record = records[item.memory_id]
            episodes.append(
                {
                    "uuid": episode_id,
                    "name": _graphiti_episode_name(
                        item.memory_id, "d" * 64, record.version
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


def _metric_row(
    case: Any,
    *,
    memory_ids: list[str],
    scope_keys: list[str],
    authorized_scope_key: str,
    graph_route_queries: int,
    latency_ms: float,
    forbidden_memory_ids: list[str] | None = None,
    candidate_noise_memory_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "query_id": case.query_id,
        "category": case.category,
        "partition": case.partition,
        "memory_ids": memory_ids,
        "required_hop_memory_ids": case.required_hop_memory_ids,
        "forbidden_memory_ids": (
            case.forbidden_memory_ids
            if forbidden_memory_ids is None
            else forbidden_memory_ids
        ),
        "candidate_noise_memory_ids": (
            case.candidate_noise_memory_ids
            if candidate_noise_memory_ids is None
            else candidate_noise_memory_ids
        ),
        "authorized_scope_key": authorized_scope_key,
        "scope_keys": scope_keys,
        "recovery_expected": case.recovery_expected,
        "dual_attribution_expected": False,
        "both_attributed": False,
        "dedupe_ok": len(memory_ids) == len(set(memory_ids)),
        "graph_route_queries": graph_route_queries,
        "latency_ms": latency_ms,
    }


def _hybrid_retrieval_labels(
    case: Any,
    *,
    records: dict[str, MemoryRecord],
    scope: MemoryScope,
    valid_at: Any,
) -> tuple[list[str], list[str]]:
    """Project path-output labels into candidate-retrieval semantics.

    The source dataset's ``forbidden_memory_ids`` means that a record must not be
    returned as a complete typed path.  A Store-authoritative first hop can still be
    safe, useful candidate context.  This projection is domain-neutral: it checks
    authority, lifecycle, provenance, exact scope, and validity rather than query IDs,
    entities, relation labels, or natural-language vocabulary.
    """

    hard_forbidden: list[str] = []
    related = list(case.candidate_noise_memory_ids)
    for memory_id in case.forbidden_memory_ids:
        record = records.get(memory_id)
        if record is not None and _is_authoritative_at(record, scope, valid_at):
            if memory_id not in related:
                related.append(memory_id)
        else:
            hard_forbidden.append(memory_id)
    return hard_forbidden, related


def _is_authoritative_at(
    record: MemoryRecord, scope: MemoryScope, valid_at: Any
) -> bool:
    if record.scope.scope_key != scope.scope_key:
        return False
    if record.state is not MemoryState.CONFIRMED:
        return False
    if record.authority is FactAuthority.AGENT_OUTPUT:
        return False
    if "personal-memory" not in record.tags:
        return False
    if not record.metadata.get("evidence"):
        return False
    valid_from = _timestamp(str(record.metadata.get("valid_from", "") or ""))
    valid_to = _timestamp(str(record.metadata.get("valid_to", "") or ""))
    if valid_from is not None and valid_from > valid_at:
        return False
    return valid_to is None or valid_to >= valid_at


async def _main_async(args: argparse.Namespace) -> int:
    dataset = load_dataset(args.dataset)
    neo4j_password = os.environ.get(args.neo4j_password_env, "")
    postgres_password = os.environ.get(args.postgres_password_env, "")
    if not neo4j_password:
        raise RuntimeError(f"{args.neo4j_password_env} is required")
    if not postgres_password:
        raise RuntimeError(f"{args.postgres_password_env} is required")
    provider = _LocalEmbeddingProvider(
        args.embedding_model,
        dimensions=args.embedding_dimensions,
        cache_dir=args.embedding_cache_dir,
        batch_size=args.embedding_batch_size,
    )
    try:
        await provider.warmup()
        report = await run_ablation(
            dataset,
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=neo4j_password,
            postgres_password=postgres_password,
            embedding_provider=provider,
        )
    except Exception as exc:  # noqa: BLE001
        report = {
            "result_schema_version": 2,
            "runner": RUNNER,
            "dataset": {
                "suite": dataset.suite,
                "version": dataset.suite_version,
                "fingerprint": dataset.fingerprint,
            },
            "runtime": {
                "llm_calls": 0,
                "external_http_calls": 0,
                "provider_tokens": 0,
                "credentials_persisted": False,
            },
            "hard_failure": type(exc).__name__,
            "gate": {"ok": False, "failures": ["runtime_unavailable"]},
        }
    report["report_sha256"] = hashlib.sha256(
        json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["gate"]["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("benchmarks/datasets/candidate-relation-path-ablation-zh-v2.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/doppel/hybrid-path-candidate-ablation.json"),
    )
    parser.add_argument(
        "--neo4j-uri", default=os.environ.get("DOPPEL_NEO4J_URI", "bolt://127.0.0.1:7687")
    )
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password-env", default="DOPPEL_NEO4J_PASSWORD")
    parser.add_argument(
        "--postgres-password-env", default="DOPPEL_ABLATION_PG_PASSWORD"
    )
    parser.add_argument("--embedding-model", default="BAAI/bge-small-zh-v1.5")
    parser.add_argument("--embedding-dimensions", type=int, default=512)
    parser.add_argument("--embedding-cache-dir", type=Path, default=None)
    parser.add_argument("--embedding-batch-size", type=int, default=32)
    return asyncio.run(_main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
