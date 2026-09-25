"""Live retrieval runner for the frozen heterogeneous personal-memory corpus."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import subprocess
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from benchmarks.combined_retrieval_live import (
    _record_rejection_reasons,
    _seed_graph,
    _store_revalidation_failures,
)
from benchmarks.heterogeneous_retrieval_quality import (
    HeterogeneousMemory,
    HeterogeneousQuery,
    HeterogeneousRetrievalDataset,
    load_dataset,
)
from benchmarks.personal_relation_path_ablation import _percentile, _timestamp
from benchmarks.personal_retrieval_ablation import (
    PG_DATABASE,
    PG_HOST,
    PG_PORT,
    PG_USER,
    _build_vector_candidates,
    _build_vector_index,
    _embedding_runtime_metadata,
    _LocalEmbeddingProvider,
    _PersonalMemoryRerankerAdapter,
    _probe_postgres,
    _reset_ablation_postgres,
    _SentenceTransformersRelationReranker,
)
from doppel_memory.graphiti_store import GraphitiRelationIndex, _graph_query_records
from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryFilter,
    MemoryRecord,
    MemoryScope,
    MemoryState,
)
from doppel_memory.personal_rerank import PersonalMemoryRerankConfig
from doppel_memory.query import (
    PersonalMemoryQueryConfig,
    PersonalMemoryQueryDraftV2,
    PersonalMemoryQueryEngine,
    PersonalMemoryQueryRequest,
)
from doppel_memory.query_path import PersonalMemoryRelationPathDraftV4
from doppel_memory.relation_path_retrieval import (
    HybridRetrievalAssembly,
    assemble_hybrid_retrieval_candidates,
    build_relation_path_retrieval_plan,
    search_relation_path_routes,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "benchmarks/datasets/heterogeneous-retrieval-zh-v2.json"
DEFAULT_OUTPUT = ROOT / "data/doppel/heterogeneous-retrieval-v2-live.json"
RUNNER = "doppel.heterogeneous-retrieval-live.v1"
PROFILES = (
    "independent_lexical_vector",
    "oracle_graph_path",
    "assembled_oracle_hybrid",
    "assembled_oracle_hybrid_memory_reranking",
)
ANSWERABLE_CATEGORIES = (
    "current_residence",
    "temporary_residence_as_of",
    "corrected_fact",
    "episode_count",
    "one_hop_relation",
    "two_hop_relation",
    "document_fact",
    "cross_conversation",
    "subject_correction",
)
THRESHOLDS = {
    "min_evidence_recall_at_5": 0.85,
    "min_complete_evidence_rate_at_10": 0.80,
    "min_category_evidence_recall_at_10": 0.75,
    "min_related_evidence_recall_at_10": 0.75,
    "min_exact_episode_count_rate_at_10": 0.90,
    "max_hard_forbidden_hits": 0,
    "max_scope_leakage": 0,
    "max_subject_violations": 0,
    "max_ineligible_hits": 0,
    "max_temporal_violations": 0,
    "max_orphan_provenance": 0,
    "max_store_revalidation_failures": 0,
    "max_path_budget_omissions": 0,
    "max_reorder_membership_violations": 0,
    "max_candidates_per_query": 20,
}
FILTERS = MemoryFilter(
    tags={"personal-memory"},
    states={MemoryState.CONFIRMED},
    exclude_authorities={FactAuthority.AGENT_OUTPUT},
)


class _DatasetPlanner:
    name = "doppel.benchmark.heterogeneous-v1-oracle-time-planner"
    version = "1"

    def __init__(self, case: HeterogeneousQuery, scope: MemoryScope) -> None:
        self.case = case
        self.scope = scope

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraftV2:
        temporal_view = cast(
            Literal["current", "as_of", "prior"],
            {
                "current": "current",
                "as_of": "as_of",
                "history": "prior",
            }[self.case.temporal_view],
        )
        return PersonalMemoryQueryDraftV2(
            operation=self.case.intent,
            temporal_view=temporal_view,
            search_text=self.case.query,
            entity_mentions=self.case.entity_mentions,
            subject=request.default_subject,
            subject_id=self.scope.user_id,
            as_of=(
                _timestamp(self.case.valid_at)
                if self.case.temporal_view == "as_of"
                else None
            ),
            confidence=1.0,
            explanation="frozen labels supply operation, time view, and subject only",
        )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--partition", choices=("dev", "all"), default="dev")
    result.add_argument(
        "--sealed-first-run",
        action="store_true",
        help="required to open the frozen sealed and adversarial partitions",
    )
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
    result.add_argument("--reranker-model", required=True)
    result.add_argument(
        "--reranker-score-normalization",
        choices=("identity", "sigmoid"),
        default="sigmoid",
    )
    result.add_argument("--reranker-cache-dir", type=Path, default=None)
    result.add_argument("--reranker-batch-size", type=int, default=16)
    result.add_argument("--reranker-device", default="cuda")
    result.add_argument("--rerank-window", type=int, default=64)
    return result


def _select_queries(
    dataset: HeterogeneousRetrievalDataset,
    partition: str,
    *,
    sealed_first_run: bool,
) -> list[HeterogeneousQuery]:
    if partition == "all":
        if not sealed_first_run:
            raise ValueError("all partitions require --sealed-first-run")
        return list(dataset.queries)
    if sealed_first_run:
        raise ValueError("--sealed-first-run is only valid with --partition all")
    return [query for query in dataset.queries if query.partition == "dev"]


async def run_live(
    dataset: HeterogeneousRetrievalDataset,
    queries: Sequence[HeterogeneousQuery],
    *,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    postgres_password: str,
    embedding_provider: Any,
    memory_reranker: Any,
    rerank_window: int = 64,
) -> dict[str, Any]:
    from neo4j import AsyncGraphDatabase  # pyright: ignore[reportMissingImports]

    if not 1 <= rerank_window <= 100:
        raise ValueError("rerank window must be between 1 and 100")
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
    run_id = f"doppel-heterogeneous-v1-{uuid4().hex}"
    scopes = {
        name: MemoryScope(
            user_id=f"{scope.user_id}:{run_id}", agent_id=scope.agent_id
        )
        for name, scope in dataset.scopes.items()
    }
    groups = [scope.scope_key for scope in scopes.values()]
    records = [_record(memory, scopes[memory.scope]) for memory in dataset.memories]
    records_by_id = {record.memory_id: record for record in records}
    memories_by_id = {memory.memory_id: memory for memory in dataset.memories}
    rows_by_profile: dict[str, list[dict[str, Any]]] = {
        profile: [] for profile in PROFILES
    }
    assembly_totals: Counter[str] = Counter()
    reranking_assembly_totals: Counter[str] = Counter()
    rerank_statuses: Counter[str] = Counter()
    reorder_membership_violations = 0
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
        config = PersonalMemoryQueryConfig(limit=100, semantic_candidate_limit=100)
        engine = PersonalMemoryQueryEngine(
            store,
            config,
            semantic_index=vector_index,
        )
        reranked_engine = PersonalMemoryQueryEngine(
            store,
            config,
            semantic_index=vector_index,
            memory_reranker=memory_reranker,
            rerank_config=PersonalMemoryRerankConfig(
                max_candidates=rerank_window,
                max_input_chars=100_000,
                timeout_seconds=120,
            ),
        )
        graph_index = GraphitiRelationIndex(
            store, graphiti_client=_LiveGraphClientAdapter(driver)
        )
        graph_write_attempted = True
        await _seed_graph(
            driver,
            cast(Any, dataset),
            run_id=run_id,
            scopes=scopes,
            records=records_by_id,
        )

        for case in queries:
            scope = scopes[case.scope]
            valid_at = _timestamp(case.valid_at)
            now = max(valid_at, datetime(2026, 9, 25, tzinfo=UTC))

            base_started = time.perf_counter()
            base_result = await engine.query(
                _DatasetPlanner(case, scope),
                case.query,
                [scope],
                now=now,
                default_subject=Actor.OWNER,
                default_subject_id=scope.user_id,
            )
            base_latency = (time.perf_counter() - base_started) * 1000

            rerank_started = time.perf_counter()
            reranked_result = await reranked_engine.query(
                _DatasetPlanner(case, scope),
                case.query,
                [scope],
                now=now,
                default_subject=Actor.OWNER,
                default_subject_id=scope.user_id,
            )
            rerank_latency = (time.perf_counter() - rerank_started) * 1000
            base_window = base_result.hits[:rerank_window]
            reranked_window = reranked_result.hits[:rerank_window]
            if {hit.record.memory_id for hit in base_window} != {
                hit.record.memory_id for hit in reranked_window
            }:
                reorder_membership_violations += 1
            status = (
                reranked_result.memory_reranking.status
                if reranked_result.memory_reranking is not None
                else "not_run"
            )
            rerank_statuses[status] += 1

            path_plan = _oracle_path_plan(case, scope)
            path_started = time.perf_counter()
            path_hits = await search_relation_path_routes(
                graph_index,
                path_plan,
                [scope],
                filters=FILTERS,
                limit=20,
            )
            path_latency = (time.perf_counter() - path_started) * 1000

            assembly_started = time.perf_counter()
            assembly = await assemble_hybrid_retrieval_candidates(
                store,
                base_window,
                path_hits,
                [scope],
                filters=FILTERS,
                limit=20,
                base_reserve=5,
            )
            assembly_latency = (time.perf_counter() - assembly_started) * 1000
            _update_assembly_totals(assembly_totals, assembly)

            reranking_assembly_started = time.perf_counter()
            reranking_assembly = await assemble_hybrid_retrieval_candidates(
                store,
                reranked_window,
                path_hits,
                [scope],
                filters=FILTERS,
                limit=20,
                base_reserve=5,
            )
            reranking_assembly_latency = (
                time.perf_counter() - reranking_assembly_started
            ) * 1000
            _update_assembly_totals(
                reranking_assembly_totals, reranking_assembly
            )

            base_ids = [hit.record.memory_id for hit in base_result.hits[:20]]
            independent_window_ids = [
                hit.record.memory_id for hit in base_window
            ]
            path_ids = list(
                dict.fromkeys(
                    memory_id
                    for hit in path_hits
                    for memory_id in hit.candidate.supporting_memory_ids
                )
            )
            assembled_ids = [
                candidate.record.memory_id for candidate in assembly.candidates
            ]
            reranked_ids = [
                candidate.record.memory_id
                for candidate in reranking_assembly.candidates
            ]
            profile_rows = (
                (
                    "independent_lexical_vector",
                    base_ids,
                    [hit.record.scope.scope_key for hit in base_result.hits[:20]],
                    base_latency,
                    [hit.candidate_evidence.sources for hit in base_result.hits[:20]],
                    base_ids,
                ),
                (
                    "oracle_graph_path",
                    path_ids,
                    [hit.candidate.scope.scope_key for hit in path_hits],
                    path_latency,
                    [["relation_path:oracle"] for _ in path_ids],
                    path_ids,
                ),
                (
                    "assembled_oracle_hybrid",
                    assembled_ids,
                    [
                        candidate.record.scope.scope_key
                        for candidate in assembly.candidates
                    ],
                    base_latency + path_latency + assembly_latency,
                    [candidate.discovery_sources for candidate in assembly.candidates],
                    assembled_ids,
                ),
                (
                    "assembled_oracle_hybrid_memory_reranking",
                    reranked_ids,
                    [
                        candidate.record.scope.scope_key
                        for candidate in reranking_assembly.candidates
                    ],
                    rerank_latency + path_latency + reranking_assembly_latency,
                    [
                        candidate.discovery_sources
                        for candidate in reranking_assembly.candidates
                    ],
                    independent_window_ids,
                ),
            )
            for (
                profile,
                ids,
                result_scopes,
                latency,
                sources,
                candidate_window_ids,
            ) in profile_rows:
                rows_by_profile[profile].append(
                    _row(
                        case,
                        ids=ids,
                        result_scopes=result_scopes,
                        authorized_scope=scope.scope_key,
                        authorized_subject=scope.user_id,
                        latency_ms=latency,
                        records=records_by_id,
                        memories=memories_by_id,
                        sources=sources,
                        candidate_window_ids=candidate_window_ids,
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
        profile: _summarize(rows) for profile, rows in rows_by_profile.items()
    }
    complete_selection = len(queries) == len(dataset.queries)
    gate = quality_gate(
        profiles,
        reranking_assembly_totals,
        selection_complete=complete_selection,
        expected_rerank_calls=len(queries),
        rerank_statuses=rerank_statuses,
        reorder_membership_violations=reorder_membership_violations,
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
            "memories": len(dataset.memories),
            "queries": len(dataset.queries),
            "selected_queries": len(queries),
            "selected_partitions": sorted({query.partition for query in queries}),
            "frozen": dataset.frozen,
            "publication_ready": dataset.publication_ready,
        },
        "runtime": {
            "store": "postgresql",
            "vector": "pgvector",
            "graph": "neo4j_graphiti_oracle_relation_path",
            "embedding": _embedding_runtime_metadata(embedding_provider),
            "memory_reranker": {
                "name": memory_reranker.name,
                "version": memory_reranker.version,
                "window": rerank_window,
            },
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
        "reranking_assembly": dict(reranking_assembly_totals),
        "rerank_statuses": dict(rerank_statuses),
        "reorder_membership_violations": reorder_membership_violations,
        "gate": gate,
    }


class _LiveGraphClientAdapter:
    """Delay the optional Graphiti benchmark dependency until live execution."""

    def __new__(cls, driver: Any) -> Any:
        from benchmarks.personal_relation_path_ablation import _LiveGraphClient

        return _LiveGraphClient(driver)


def _oracle_path_plan(case: HeterogeneousQuery, scope: MemoryScope) -> Any:
    path_steps = case.required_routes[0] if case.required_routes else []
    draft = PersonalMemoryRelationPathDraftV4(
        operation=case.intent,
        temporal_view="as_of",
        search_text=case.query,
        entity_mentions=case.entity_mentions,
        subject=Actor.OWNER,
        subject_id=scope.user_id,
        as_of=_timestamp(case.valid_at),
        path_steps=path_steps,
        path_confidence=1.0 if path_steps else 0.0,
        path_decision="execute" if path_steps else "abstain",
        path_reason="exact" if path_steps else "nonrelation",
    )
    return build_relation_path_retrieval_plan(
        draft,
        allowed_relation_types=("HELD_BY", "LIVES_IN"),
    )


def _record(item: HeterogeneousMemory, scope: MemoryScope) -> MemoryRecord:
    valid_from = _timestamp(item.valid_from)
    subject = Actor.OWNER if item.subject_id.startswith("owner-") else Actor.CONTACT
    actor = {
        "human_self": Actor.OWNER,
        "peer_statement": Actor.CONTACT,
        "agent_output": Actor.AGENT,
    }[item.authority]
    subject_id = (
        scope.user_id if subject == Actor.OWNER else item.subject_id.lower()
    )
    return MemoryRecord(
        memory_id=item.memory_id,
        scope=scope,
        kind=item.kind,
        content=item.content,
        actor=actor,
        authority=FactAuthority(item.authority),
        state=MemoryState(item.state),
        tags=item.tags,
        extractor="benchmark.heterogeneous-v1",
        created_at=valid_from,
        updated_at=valid_from,
        metadata={
            "subject": subject,
            "subject_id": subject_id,
            "personal_memory_type": item.kind,
            "topic_key": item.fact_key,
            "event_key": item.event_key,
            "temporal_status": item.temporal_status,
            "valid_from": item.valid_from,
            "valid_to": item.valid_to or None,
            "conversation_id": item.conversation_id,
            "source_kind": item.source_kind,
            "evidence": [{"evidence_id": item.evidence_id}],
        },
    )


def _update_assembly_totals(
    totals: Counter[str], assembly: HybridRetrievalAssembly
) -> None:
    totals.update(
        {
            "rejected_base_hits": assembly.rejected_base_hits,
            "rejected_path_hits": assembly.rejected_path_hits,
            "omitted_path_hits": assembly.omitted_path_hits,
            "truncated_queries": int(assembly.truncated),
            "retained_paths": len(assembly.relation_paths),
        }
    )
    _record_rejection_reasons(totals, assembly)


def _row(
    case: HeterogeneousQuery,
    *,
    ids: list[str],
    result_scopes: list[str],
    authorized_scope: str,
    authorized_subject: str,
    latency_ms: float,
    records: dict[str, MemoryRecord],
    memories: dict[str, HeterogeneousMemory],
    sources: list[list[str]],
    candidate_window_ids: list[str],
) -> dict[str, Any]:
    valid_at = cast(datetime, _timestamp(case.valid_at))
    subject_violations = ineligible = temporal_violations = orphan = 0
    estimated_characters = 0
    for memory_id in ids:
        record = records.get(memory_id)
        memory = memories.get(memory_id)
        if record is None or memory is None:
            orphan += 1
            continue
        estimated_characters += len(record.content)
        if str(record.metadata.get("subject_id") or "") != authorized_subject:
            subject_violations += 1
        if (
            record.state is not MemoryState.CONFIRMED
            or record.authority is FactAuthority.AGENT_OUTPUT
        ):
            ineligible += 1
        start = cast(datetime, _timestamp(memory.valid_from))
        end = cast(datetime | None, _timestamp(memory.valid_to))
        ended_before_query = (
            case.temporal_view != "history"
            and end is not None
            and end <= valid_at
        )
        if start > valid_at or ended_before_query:
            temporal_violations += 1
    required_event_keys = sorted(
        {
            memories[memory_id].event_key
            for memory_id in case.required_memory_ids
            if memories[memory_id].event_key
        }
    )
    observed_event_keys_at_10 = sorted(
        {
            memories[memory_id].event_key
            for memory_id in ids[:10]
            if memory_id in memories
            and memories[memory_id].kind == "episode"
            and memories[memory_id].temporal_status == "historical"
            and memories[memory_id].fact_key == "travel:completed"
            and memories[memory_id].subject_id == case.subject_id
        }
    )
    return {
        "case_id": case.case_id,
        "partition": case.partition,
        "category": case.category,
        "ids": ids,
        "required": case.required_memory_ids,
        "related": case.related_memory_ids,
        "hard_forbidden": case.hard_forbidden_memory_ids,
        "answerable": case.answerable,
        "expected_count": case.expected_count,
        "required_event_keys": required_event_keys,
        "observed_event_keys_at_10": observed_event_keys_at_10,
        "scope_leakage": sum(scope != authorized_scope for scope in result_scopes),
        "subject_violations": subject_violations,
        "ineligible_hits": ineligible,
        "temporal_violations": temporal_violations,
        "orphan_provenance": orphan,
        "latency_ms": latency_ms,
        "estimated_context_characters": estimated_characters,
        "sources": sources,
        "candidate_window_ids": candidate_window_ids,
    }


def _summarize(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    grouped_category: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_partition: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped_category[str(row["category"])].append(row)
        grouped_partition[str(row["partition"])].append(row)
    summary = _summarize_slice(rows)
    summary["by_category"] = {
        name: _summarize_slice(items, include_details=False)
        for name, items in sorted(grouped_category.items())
    }
    summary["by_partition"] = {
        name: _summarize_slice(items, include_details=False)
        for name, items in sorted(grouped_partition.items())
    }
    return summary


def _summarize_slice(
    rows: Sequence[dict[str, Any]], *, include_details: bool = True
) -> dict[str, Any]:
    cutoffs = (1, 5, 10, 20)
    required_total = sum(len(row["required"]) for row in rows)
    related_total = sum(len(row["related"]) for row in rows if not row["answerable"])
    answerable = [row for row in rows if row["answerable"]]
    recall = {
        cutoff: sum(
            len(set(row["required"]) & set(row["ids"][:cutoff])) for row in rows
        )
        for cutoff in cutoffs
    }
    complete = {
        cutoff: sum(
            set(row["required"]).issubset(set(row["ids"][:cutoff]))
            for row in answerable
        )
        for cutoff in cutoffs
    }
    related_at_10 = sum(
        len(set(row["related"]) & set(row["ids"][:10]))
        for row in rows
        if not row["answerable"]
    )
    candidate_required = sum(
        len(set(row["required"]) & set(row.get("candidate_window_ids", [])))
        for row in rows
    )
    candidate_related = sum(
        len(set(row["related"]) & set(row.get("candidate_window_ids", [])))
        for row in rows
        if not row["answerable"]
    )
    reciprocal_ranks = []
    for row in rows:
        required = set(row["required"])
        if not required:
            continue
        rank = next(
            (
                index
                for index, memory_id in enumerate(row["ids"], start=1)
                if memory_id in required
            ),
            0,
        )
        reciprocal_ranks.append(1 / rank if rank else 0.0)
    count_rows = [row for row in rows if row["expected_count"] is not None]
    exact_counts = sum(_episode_count_exact(row) for row in count_rows)
    latencies = [float(row["latency_ms"]) for row in rows]
    source_counts: Counter[str] = Counter()
    for row in rows:
        for names in row["sources"]:
            source_counts.update(names)
    result: dict[str, Any] = {
        "queries": len(rows),
        "answerable_queries": len(answerable),
        "required_evidence": required_total,
        **{
            f"evidence_recall_at_{cutoff}": _ratio(recall[cutoff], required_total)
            for cutoff in cutoffs
        },
        **{
            f"complete_evidence_rate_at_{cutoff}": _ratio(
                complete[cutoff], len(answerable)
            )
            for cutoff in cutoffs
        },
        "related_evidence_recall_at_10": _ratio(related_at_10, related_total),
        "candidate_window_evidence_recall": _ratio(
            candidate_required, required_total
        ),
        "candidate_window_related_recall": _ratio(
            candidate_related, related_total
        ),
        "mrr": round(statistics.mean(reciprocal_ranks), 6)
        if reciprocal_ranks
        else 1.0,
        "exact_episode_count_rate_at_10": _ratio(exact_counts, len(count_rows)),
        "hard_forbidden_hits": sum(
            len(set(row["ids"]) & set(row["hard_forbidden"])) for row in rows
        ),
        "scope_leakage": sum(int(row["scope_leakage"]) for row in rows),
        "subject_violations": sum(int(row["subject_violations"]) for row in rows),
        "ineligible_hits": sum(int(row["ineligible_hits"]) for row in rows),
        "temporal_violations": sum(int(row["temporal_violations"]) for row in rows),
        "orphan_provenance": sum(int(row["orphan_provenance"]) for row in rows),
        "max_candidates": max((len(row["ids"]) for row in rows), default=0),
        "average_candidates": round(
            statistics.mean([len(row["ids"]) for row in rows]), 6
        )
        if rows
        else 0.0,
        "average_context_characters": round(
            statistics.mean(
                [int(row["estimated_context_characters"]) for row in rows]
            ),
            6,
        )
        if rows
        else 0.0,
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
        },
        "source_attribution": dict(sorted(source_counts.items())),
    }
    if include_details:
        result["details"] = [
            {
                "case_id": row["case_id"],
                "ids": row["ids"],
                "missing_at_5": sorted(
                    set(row["required"]) - set(row["ids"][:5])
                ),
                "missing_at_10": sorted(
                    set(row["required"]) - set(row["ids"][:10])
                ),
                "related_at_10": sorted(
                    set(row["related"]) & set(row["ids"][:10])
                ),
                "hard_forbidden_hits": sorted(
                    set(row["ids"]) & set(row["hard_forbidden"])
                ),
            }
            for row in rows
        ]
    return result


def _episode_count_exact(row: dict[str, Any]) -> bool:
    expected = int(row["expected_count"])
    required = set(row["required_event_keys"])
    observed = set(row["observed_event_keys_at_10"])
    return len(observed) == expected and observed == required


def quality_gate(
    profiles: dict[str, dict[str, Any]],
    assembly: Counter[str],
    *,
    selection_complete: bool,
    expected_rerank_calls: int,
    rerank_statuses: Counter[str],
    reorder_membership_violations: int,
    graph_cleaned: bool,
    postgres_reset: bool,
) -> dict[str, Any]:
    baseline = profiles["assembled_oracle_hybrid"]
    final = profiles["assembled_oracle_hybrid_memory_reranking"]
    checks = {
        "selection_complete": selection_complete,
        "evidence_recall_at_5": final["evidence_recall_at_5"]
        >= THRESHOLDS["min_evidence_recall_at_5"],
        "complete_evidence_rate_at_10": final["complete_evidence_rate_at_10"]
        >= THRESHOLDS["min_complete_evidence_rate_at_10"],
        "per_category_recall_at_10": all(
            final["by_category"][category]["evidence_recall_at_10"]
            >= THRESHOLDS["min_category_evidence_recall_at_10"]
            for category in ANSWERABLE_CATEGORIES
        ),
        "related_evidence_recall_at_10": final["by_category"][
            "no_answer_related"
        ]["related_evidence_recall_at_10"]
        >= THRESHOLDS["min_related_evidence_recall_at_10"],
        "mrr_non_regression": final["mrr"] >= baseline["mrr"],
        "exact_episode_count_rate_at_10": final["by_category"]["episode_count"][
            "exact_episode_count_rate_at_10"
        ]
        >= THRESHOLDS["min_exact_episode_count_rate_at_10"],
        "hard_forbidden_hits": final["hard_forbidden_hits"] == 0,
        "scope_leakage": final["scope_leakage"] == 0,
        "subject_violations": final["subject_violations"] == 0,
        "ineligible_hits": final["ineligible_hits"] == 0,
        "temporal_violations": final["temporal_violations"] == 0,
        "orphan_provenance": final["orphan_provenance"] == 0,
        "store_revalidation_failures": _store_revalidation_failures(assembly)
        == 0,
        "path_budget_omissions": assembly["omitted_path_hits"] == 0,
        "reorder_membership": reorder_membership_violations == 0,
        "reranker_statuses_accounted": sum(rerank_statuses.values())
        == expected_rerank_calls
        and set(rerank_statuses).issubset({"completed", "not_run"}),
        "candidate_bound": final["max_candidates"]
        <= THRESHOLDS["max_candidates_per_query"],
        "neo4j_cleanup": graph_cleaned,
        "postgres_cleanup": postgres_reset,
    }
    return {
        "ok": all(checks.values()),
        "status": "complete" if selection_complete else "dev_diagnostic",
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "thresholds": THRESHOLDS,
        "baseline_profile": "assembled_oracle_hybrid",
        "profile": "assembled_oracle_hybrid_memory_reranking",
    }


async def _main_async(args: argparse.Namespace) -> int:
    dataset = load_dataset(args.dataset)
    queries = _select_queries(
        dataset,
        args.partition,
        sealed_first_run=args.sealed_first_run,
    )
    neo4j_password = os.environ.get(args.neo4j_password_env, "")
    postgres_password = os.environ.get(args.postgres_password_env, "")
    if not neo4j_password or not postgres_password:
        raise RuntimeError("both local backend password variables are required")
    embedding_provider = _LocalEmbeddingProvider(
        args.embedding_model,
        dimensions=args.embedding_dimensions,
        cache_dir=args.embedding_cache_dir,
        batch_size=args.embedding_batch_size,
    )
    relation_reranker = _SentenceTransformersRelationReranker(
        args.reranker_model,
        score_normalization=args.reranker_score_normalization,
        cache_dir=args.reranker_cache_dir,
        batch_size=args.reranker_batch_size,
        device=args.reranker_device,
    )
    memory_reranker = _PersonalMemoryRerankerAdapter(relation_reranker)
    try:
        await embedding_provider.warmup()
        await relation_reranker.warmup()
        report = await run_live(
            dataset,
            queries,
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=neo4j_password,
            postgres_password=postgres_password,
            embedding_provider=embedding_provider,
            memory_reranker=memory_reranker,
            rerank_window=args.rerank_window,
        )
    except Exception as exc:  # noqa: BLE001
        report = {
            "result_schema_version": 1,
            "runner": RUNNER,
            "dataset": {
                "suite": dataset.suite,
                "fingerprint": dataset.fingerprint,
                "selected_queries": len(queries),
            },
            "hard_failure": type(exc).__name__,
            "runtime": {
                "llm_calls": 0,
                "external_http_calls": 0,
                "provider_tokens": 0,
                "credentials_persisted": False,
            },
            "gate": {"ok": False, "failures": ["runtime_unavailable"]},
        }
    report["reproducibility"] = _git_metadata(dataset.fingerprint)
    report["report_sha256"] = _fingerprint(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "report_sha256": report["report_sha256"],
                "hard_failure": report.get("hard_failure"),
                "gate": report.get("gate"),
                "profile_metrics": {
                    name: {
                        "evidence_recall_at_5": values["evidence_recall_at_5"],
                        "complete_evidence_rate_at_10": values[
                            "complete_evidence_rate_at_10"
                        ],
                        "mrr": values["mrr"],
                    }
                    for name, values in dict(report.get("profiles") or {}).items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.partition == "dev":
        return 0 if "hard_failure" not in report else 1
    return 0 if report.get("gate", {}).get("ok") is True else 1


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 1.0


def _fingerprint(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _git_metadata(dataset_fingerprint: str) -> dict[str, Any]:
    def run(*args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    status_entries = [item for item in completed.stdout.split("\0") if item]
    return {
        "implementation_commit": run("rev-parse", "HEAD"),
        "tracked_dirty_paths": [
            item[3:] for item in status_entries if not item.startswith("??")
        ],
        "dataset_fingerprint": dataset_fingerprint,
        "profile_contract": list(PROFILES),
        "oracle_graph_routes": True,
        "answer_support": "unassessed",
    }


def main() -> int:
    return asyncio.run(_main_async(parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
