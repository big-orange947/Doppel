"""Live multi-instance reliability gate for PostgreSQL, pgvector, and Graphiti.

The benchmark uses only the dedicated ``doppel_ablation`` database and run-scoped
Neo4j groups. It makes no external HTTP or LLM call. Without ``--live`` it prints the
frozen workload contract and does not read credentials or connect to a backend.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import time
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from benchmarks.heterogeneous_retrieval_live import _LiveGraphClientAdapter
from benchmarks.personal_retrieval_ablation import (
    PG_DATABASE,
    PG_HOST,
    PG_PORT,
    PG_USER,
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
from doppel_memory.indexing import IndexMaintainer
from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryFilter,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    MemoryStateConflictError,
    WriteStatus,
)
from doppel_memory.postgres_store import PostgreSQLStore
from doppel_memory.relation import RelationPathQuery, RelationPathStep
from doppel_memory.vector import PostgreSQLVectorIndex, VectorIndexConfig

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data/doppel/multi-instance-reliability-v2-live.json"
RUNNER = "doppel.multi-instance-reliability-live.v2"
CONTRACT_VERSION = 2
DEFAULT_INSTANCES = 4
DEFAULT_POOL_SIZE_PER_INSTANCE = 2
DEFAULT_SCOPES = 8
DEFAULT_RECORDS_PER_SCOPE = 16
DEFAULT_DUPLICATE_ATTEMPTS = 4
DEFAULT_GRAPH_ROUNDS = 4
DEFAULT_SEED = 947
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
FILTERS = MemoryFilter(
    tags={"personal-memory"},
    states={MemoryState.CONFIRMED},
    exclude_authorities={FactAuthority.AGENT_OUTPUT},
)
THRESHOLDS = {
    "max_migration_errors": 0,
    "max_write_errors": 0,
    "max_idempotency_violations": 0,
    "max_physical_duplicates": 0,
    "max_scope_leakage": 0,
    "max_transition_race_violations": 0,
    "max_vector_failures": 0,
    "max_unclassified_vector_failures": 0,
    "max_vector_replay_mutations": 0,
    "max_vector_search_misses": 0,
    "max_graph_path_misses": 0,
    "max_stale_graph_hits": 0,
    "max_reconciliation_failures": 0,
    "max_restart_failures": 0,
    "max_cleanup_errors": 0,
    "max_write_p95_ms": 500.0,
    "max_vector_search_p95_ms": 1_000.0,
    "max_graph_search_p95_ms": 1_000.0,
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--live", action="store_true")
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--instances", type=int, default=DEFAULT_INSTANCES)
    result.add_argument("--scopes", type=int, default=DEFAULT_SCOPES)
    result.add_argument(
        "--records-per-scope", type=int, default=DEFAULT_RECORDS_PER_SCOPE
    )
    result.add_argument(
        "--duplicate-attempts", type=int, default=DEFAULT_DUPLICATE_ATTEMPTS
    )
    result.add_argument("--graph-rounds", type=int, default=DEFAULT_GRAPH_ROUNDS)
    result.add_argument("--seed", type=int, default=DEFAULT_SEED)
    result.add_argument(
        "--postgres-password-env", default="DOPPEL_ABLATION_PG_PASSWORD"
    )
    result.add_argument(
        "--neo4j-uri", default=os.environ.get("DOPPEL_NEO4J_URI", "bolt://127.0.0.1:7687")
    )
    result.add_argument("--neo4j-user", default="neo4j")
    result.add_argument("--neo4j-password-env", default="DOPPEL_NEO4J_PASSWORD")
    result.add_argument("--embedding-model", default="BAAI/bge-small-zh-v1.5")
    result.add_argument("--embedding-dimensions", type=int, default=512)
    result.add_argument("--embedding-cache-dir", type=Path, default=None)
    result.add_argument("--embedding-batch-size", type=int, default=32)
    return result


def _validate_shape(
    *,
    instances: int,
    scopes: int,
    records_per_scope: int,
    duplicate_attempts: int,
    graph_rounds: int,
) -> None:
    if not 2 <= instances <= 16:
        raise ValueError("instances must be between 2 and 16")
    if not 2 <= scopes <= 64:
        raise ValueError("scopes must be between 2 and 64")
    if not 6 <= records_per_scope <= 256:
        raise ValueError("records-per-scope must be between 6 and 256")
    if not 2 <= duplicate_attempts <= 16:
        raise ValueError("duplicate-attempts must be between 2 and 16")
    if not 1 <= graph_rounds <= 100:
        raise ValueError("graph-rounds must be between 1 and 100")


def workload_contract(
    *,
    instances: int = DEFAULT_INSTANCES,
    scopes: int = DEFAULT_SCOPES,
    records_per_scope: int = DEFAULT_RECORDS_PER_SCOPE,
    duplicate_attempts: int = DEFAULT_DUPLICATE_ATTEMPTS,
    graph_rounds: int = DEFAULT_GRAPH_ROUNDS,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    _validate_shape(
        instances=instances,
        scopes=scopes,
        records_per_scope=records_per_scope,
        duplicate_attempts=duplicate_attempts,
        graph_rounds=graph_rounds,
    )
    logical_records = scopes * records_per_scope
    payload = {
        "contract_version": CONTRACT_VERSION,
        "seed": seed,
        "instances": instances,
        "pool_size_per_instance": DEFAULT_POOL_SIZE_PER_INSTANCE,
        "total_pool_connection_budget": instances * DEFAULT_POOL_SIZE_PER_INSTANCE,
        "scopes": scopes,
        "records_per_scope": records_per_scope,
        "logical_records": logical_records,
        "write_attempts": logical_records * duplicate_attempts,
        "duplicate_attempts_per_record": duplicate_attempts,
        "transition_races": scopes,
        "hard_deletes": scopes,
        "stale_graph_records": scopes,
        "live_graph_records": scopes,
        "graph_rounds": graph_rounds,
        "external_http_calls": 0,
        "llm_calls": 0,
        "provider_tokens": 0,
        "thresholds": THRESHOLDS,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {
        **payload,
        "fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def _dsn(password: str) -> str:
    return (
        f"postgresql://{quote(PG_USER, safe='')}:{quote(password, safe='')}@"
        f"{PG_HOST}:{PG_PORT}/{quote(PG_DATABASE, safe='')}"
    )


def _scopes(count: int, run_id: str) -> list[MemoryScope]:
    return [
        MemoryScope(
            user_id=f"reliability-owner-{index:02d}:{run_id}",
            agent_id="doppel-reliability",
            platform="benchmark",
            chat_type="private",
            chat_id=f"scope-{index:02d}",
        )
        for index in range(count)
    ]


def _attempt_record(
    scope: MemoryScope,
    scope_index: int,
    slot: int,
    attempt: int,
) -> MemoryRecord:
    token = f"REL-{scope_index:02d}-{slot:03d}-947"
    at = NOW + timedelta(seconds=scope_index * 1_000 + slot)
    return MemoryRecord(
        memory_id=f"mi-{scope_index:02d}-{slot:03d}-attempt-{attempt:02d}",
        scope=scope,
        kind="fact",
        content=f"并发可靠性记忆 {token}，属于第{scope_index}个主体的第{slot}条事实。",
        actor=Actor.OWNER,
        authority=FactAuthority.HUMAN_SELF,
        state=MemoryState.CONFIRMED,
        tags=["personal-memory", "multi-instance-reliability"],
        idempotency_key=f"logical-slot-{slot:03d}",
        source_event_id=f"event-{scope_index:02d}-{slot:03d}",
        source_message_id=f"message-{scope_index:02d}-{slot:03d}",
        extractor=RUNNER,
        created_at=at,
        updated_at=at,
        metadata={
            "subject": Actor.OWNER,
            "subject_id": scope.user_id,
            "temporal_status": "current",
            "valid_from": at.isoformat(),
            "valid_to": None,
            "token": token,
        },
    )


async def _scan_all(store: PostgreSQLStore, scope: MemoryScope) -> list[MemoryRecord]:
    records: list[MemoryRecord] = []
    cursor = ""
    while True:
        page = await store.scan(
            scope,
            filters=MemoryFilter(include_inactive=True),
            cursor=cursor,
            limit=100,
        )
        records.extend(page.records)
        if not page.has_more:
            return records
        cursor = page.next_cursor


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 3)


def _latency_summary(values: Sequence[float]) -> dict[str, float]:
    return {
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
        "mean": round(statistics.mean(values), 3) if values else 0.0,
    }


async def _run_reconciler(
    store: PostgreSQLStore,
    index: PostgreSQLVectorIndex,
    scope: MemoryScope,
) -> tuple[int, int]:
    maintainer = IndexMaintainer(store, index)
    checkpoint = None
    failures = 0
    pages = 0
    while pages < 1_000:
        report = await maintainer.reconcile(
            scope, checkpoint=checkpoint, page_size=8
        )
        pages += 1
        failures += report.failed
        if report.committable_checkpoint is None:
            return pages, failures + 1
        checkpoint = report.committable_checkpoint
        if report.complete:
            return pages, failures
    return pages, failures + 1


async def _seed_graph(
    driver: Any,
    *,
    run_id: str,
    scopes: Sequence[MemoryScope],
    records_by_slot: dict[tuple[int, int], MemoryRecord],
) -> None:
    nodes: list[dict[str, str]] = []
    episodes: list[dict[str, str]] = []
    edges: list[dict[str, Any]] = []
    for scope_index, scope in enumerate(scopes):
        for slot, label in ((0, "stale"), (4, "live")):
            record = records_by_slot[(scope_index, slot)]
            object_name = f"可靠性相机-{scope_index:02d}-{label}"
            holder_name = f"保管人-{scope_index:02d}-{label}"
            source_uuid = f"{run_id}:entity:{scope_index}:{label}:object"
            target_uuid = f"{run_id}:entity:{scope_index}:{label}:holder"
            episode_uuid = f"{run_id}:episode:{scope_index}:{label}"
            nodes.extend(
                [
                    {
                        "uuid": source_uuid,
                        "name": object_name,
                        "group_id": scope.scope_key,
                    },
                    {
                        "uuid": target_uuid,
                        "name": holder_name,
                        "group_id": scope.scope_key,
                    },
                ]
            )
            episodes.append(
                {
                    "uuid": episode_uuid,
                    "name": _graphiti_episode_name(
                        record.memory_id, "f" * 64, record.version
                    ),
                    "group_id": scope.scope_key,
                }
            )
            edges.append(
                {
                    "source_uuid": source_uuid,
                    "target_uuid": target_uuid,
                    "group_id": scope.scope_key,
                    "uuid": f"{run_id}:edge:{scope_index}:{label}",
                    "name": "HELD_BY",
                    "fact": f"{object_name}由{holder_name}保管。",
                    "episodes": [episode_uuid],
                    "valid_at": NOW,
                    "created_at": NOW,
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
        "SET edge.group_id=item.group_id, edge.uuid=item.uuid, "
        "edge.name=item.name, edge.fact=item.fact, edge.episodes=item.episodes, "
        "edge.valid_at=item.valid_at, edge.created_at=item.created_at",
        edges=edges,
    )


def _path_query(scope_index: int, label: str, scope: MemoryScope) -> RelationPathQuery:
    object_name = f"可靠性相机-{scope_index:02d}-{label}"
    return RelationPathQuery(
        query_text=f"{object_name}由谁保管？",
        entity_mentions=[object_name],
        steps=[RelationPathStep(relation_types=["HELD_BY"], direction="outbound")],
        subject=Actor.OWNER,
        subject_id=scope.user_id,
        valid_at=NOW + timedelta(days=1),
    )


async def _graph_search(
    index: GraphitiRelationIndex,
    *,
    scope_index: int,
    label: str,
    scope: MemoryScope,
) -> tuple[list[str], float]:
    started = time.perf_counter()
    paths = await index.search_relation_paths(
        _path_query(scope_index, label, scope),
        [scope],
        filters=FILTERS,
        limit=5,
    )
    latency = (time.perf_counter() - started) * 1_000
    ids = list(
        dict.fromkeys(
            memory_id
            for path in paths
            for memory_id in path.supporting_memory_ids
        )
    )
    return ids, latency


def quality_gate(metrics: dict[str, Any], cleanup_errors: Sequence[str]) -> dict[str, Any]:
    checks = {
        "migration_errors": metrics["migration_errors"]
        <= THRESHOLDS["max_migration_errors"],
        "write_errors": metrics["write_errors"] <= THRESHOLDS["max_write_errors"],
        "idempotency": metrics["idempotency_violations"]
        <= THRESHOLDS["max_idempotency_violations"],
        "physical_duplicates": metrics["physical_duplicates"]
        <= THRESHOLDS["max_physical_duplicates"],
        "scope_isolation": metrics["scope_leakage"]
        <= THRESHOLDS["max_scope_leakage"],
        "transition_races": metrics["transition_race_violations"]
        <= THRESHOLDS["max_transition_race_violations"],
        "vector_failures": metrics["vector_failures"]
        <= THRESHOLDS["max_vector_failures"],
        "vector_failure_accounting": metrics["unclassified_vector_failures"]
        <= THRESHOLDS["max_unclassified_vector_failures"],
        "vector_replay": metrics["vector_replay_mutations"]
        <= THRESHOLDS["max_vector_replay_mutations"],
        "vector_search": metrics["vector_search_misses"]
        <= THRESHOLDS["max_vector_search_misses"],
        "graph_paths": metrics["graph_path_misses"]
        <= THRESHOLDS["max_graph_path_misses"],
        "stale_graph_revalidation": metrics["stale_graph_hits"]
        <= THRESHOLDS["max_stale_graph_hits"],
        "reconciliation": metrics["reconciliation_failures"]
        <= THRESHOLDS["max_reconciliation_failures"],
        "restart_recovery": metrics["restart_failures"]
        <= THRESHOLDS["max_restart_failures"],
        "cleanup": len(cleanup_errors) <= THRESHOLDS["max_cleanup_errors"],
        "write_latency": metrics["latency_ms"]["write"]["p95"]
        <= THRESHOLDS["max_write_p95_ms"],
        "vector_search_latency": metrics["latency_ms"]["vector_search"]["p95"]
        <= THRESHOLDS["max_vector_search_p95_ms"],
        "graph_search_latency": metrics["latency_ms"]["graph_search"]["p95"]
        <= THRESHOLDS["max_graph_search_p95_ms"],
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "ok": not failures,
        "status": "complete" if not failures else "failed",
        "checks": checks,
        "failures": failures,
        "thresholds": THRESHOLDS,
    }


async def run_live(
    contract: dict[str, Any],
    *,
    postgres_password: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
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

    run_id = f"doppel-mi-{uuid4().hex}"
    scopes = _scopes(int(contract["scopes"]), run_id)
    dsn = _dsn(postgres_password)
    stores: list[PostgreSQLStore] = []
    restarted_stores: list[PostgreSQLStore] = []
    drivers: list[Any] = []
    groups = [scope.scope_key for scope in scopes]
    graph_seeded = False
    postgres_reset = False
    graph_cleaned = False
    cleanup_errors: list[str] = []
    hard_failure = ""
    write_latencies: list[float] = []
    vector_search_latencies: list[float] = []
    graph_search_latencies: list[float] = []
    migration_errors = 0
    write_errors = 0
    idempotency_violations = 0
    physical_duplicates = 0
    scope_leakage = 0
    transition_race_violations = 0
    vector_failures = 0
    vector_failure_observations: list[dict[str, str]] = []
    vector_replay_mutations = 0
    vector_search_misses = 0
    graph_path_misses = 0
    stale_graph_hits = 0
    reconciliation_failures = 0
    restart_failures = 0
    created_count = 0
    duplicate_count = 0
    vector_health: dict[str, Any] = {}
    records_by_slot: dict[tuple[int, int], MemoryRecord] = {}
    write_wall_ms = 0.0

    def observe_vector_failure(stage: str, exc: BaseException | str) -> None:
        if isinstance(exc, BaseException):
            error_type = type(exc).__name__
            message = str(exc)
        else:
            error_type = "InvariantViolation"
            message = str(exc)
        vector_failure_observations.append(
            {
                "stage": stage,
                "error_type": error_type,
                "message": message[:500],
            }
        )
    try:
        await _reset_ablation_postgres(
            host=PG_HOST,
            port=PG_PORT,
            database=PG_DATABASE,
            user=PG_USER,
            password=postgres_password,
        )
        stores = [
            PostgreSQLStore(
                dsn,
                min_pool_size=1,
                max_pool_size=int(contract["pool_size_per_instance"]),
            )
            for _ in range(int(contract["instances"]))
        ]
        migration_results = await asyncio.gather(
            *(store.health() for store in stores), return_exceptions=True
        )
        migration_errors = sum(
            isinstance(result, BaseException) for result in migration_results
        )
        if migration_errors:
            raise RuntimeError("one or more concurrent PostgreSQL migrations failed")

        attempts: list[tuple[int, int, int, MemoryRecord, PostgreSQLStore]] = []
        for scope_index, scope in enumerate(scopes):
            for slot in range(int(contract["records_per_scope"])):
                for attempt in range(int(contract["duplicate_attempts_per_record"])):
                    attempts.append(
                        (
                            scope_index,
                            slot,
                            attempt,
                            _attempt_record(scope, scope_index, slot, attempt),
                            stores[(scope_index + slot + attempt) % len(stores)],
                        )
                    )

        async def write_one(item: tuple[int, int, int, MemoryRecord, PostgreSQLStore]):
            started = time.perf_counter()
            try:
                result = await item[4].put(
                    item[3], idempotency_key=item[3].idempotency_key
                )
                return item[:3], result, (time.perf_counter() - started) * 1_000
            except Exception as exc:  # noqa: BLE001 - benchmark report boundary
                return item[:3], exc, (time.perf_counter() - started) * 1_000

        write_started = time.perf_counter()
        write_results = await asyncio.gather(*(write_one(item) for item in attempts))
        write_wall_ms = (time.perf_counter() - write_started) * 1_000
        by_logical: dict[tuple[int, int], Counter[str]] = {}
        for (scope_index, slot, _), result, latency in write_results:
            write_latencies.append(latency)
            counter = by_logical.setdefault((scope_index, slot), Counter())
            if isinstance(result, BaseException):
                write_errors += 1
                counter["error"] += 1
            else:
                counter[result.status.value] += 1
                created_count += int(result.status is WriteStatus.CREATED)
                duplicate_count += int(result.status is WriteStatus.DUPLICATE)
        for counter in by_logical.values():
            idempotency_violations += int(
                counter[WriteStatus.CREATED.value] != 1
                or counter[WriteStatus.DUPLICATE.value]
                != int(contract["duplicate_attempts_per_record"]) - 1
                or counter["error"] != 0
            )

        stored_records: list[MemoryRecord] = []
        for scope_index, scope in enumerate(scopes):
            records = await _scan_all(stores[scope_index % len(stores)], scope)
            stored_records.extend(records)
            expected = int(contract["records_per_scope"])
            physical_duplicates += abs(len(records) - expected)
            keys = [record.idempotency_key for record in records]
            physical_duplicates += len(keys) - len(set(keys))
            scope_leakage += sum(record.scope.scope_key != scope.scope_key for record in records)
            for record in records:
                slot = int(record.idempotency_key.rsplit("-", 1)[-1])
                records_by_slot[(scope_index, slot)] = record

        vector_indexes = [
            PostgreSQLVectorIndex(
                store,
                embedding_provider,
                VectorIndexConfig(create_extension=True, create_hnsw_index=False),
            )
            for store in stores
        ]
        init_results = await asyncio.gather(
            *(index.initialize() for index in vector_indexes), return_exceptions=True
        )
        for result in init_results:
            if isinstance(result, BaseException):
                vector_failures += 1
                observe_vector_failure("initialize", result)
        initial_report = await vector_indexes[0].index_records(stored_records)
        vector_failures += initial_report.failed
        for failure in initial_report.failures:
            observe_vector_failure(
                f"initial_index:{failure.stage}",
                f"{failure.error_type}: {failure.message}",
            )
        replay_results = await asyncio.gather(
            *(
                vector_indexes[index % len(vector_indexes)].upsert(record)
                for index, record in enumerate(stored_records * 2)
            ),
            return_exceptions=True,
        )
        for result in replay_results:
            if isinstance(result, BaseException):
                vector_failures += 1
                observe_vector_failure("replay_upsert", result)
            elif result.status.value != "skipped":
                vector_replay_mutations += 1

        async def vector_search_one(scope_index: int, slot: int = 3) -> None:
            nonlocal vector_search_misses, scope_leakage
            scope = scopes[scope_index]
            expected = records_by_slot[(scope_index, slot)]
            token = str(expected.metadata["token"])
            started = time.perf_counter()
            hits = await vector_indexes[scope_index % len(vector_indexes)].search(
                token, [scope], filters=FILTERS, limit=5
            )
            vector_search_latencies.append((time.perf_counter() - started) * 1_000)
            vector_search_misses += int(
                expected.memory_id not in {hit.memory_id for hit in hits}
            )
            scope_leakage += sum(
                hit.scope is None or hit.scope.scope_key != scope.scope_key
                for hit in hits
            )

        await asyncio.gather(*(vector_search_one(index) for index in range(len(scopes))))

        drivers = [
            AsyncGraphDatabase.driver(
                neo4j_uri,
                auth=(neo4j_user, neo4j_password),
                connection_timeout=3.0,
                connection_acquisition_timeout=3.0,
                max_transaction_retry_time=0.0,
            )
            for _ in stores
        ]
        await asyncio.gather(*(driver.verify_connectivity() for driver in drivers))
        await _seed_graph(
            drivers[0], run_id=run_id, scopes=scopes, records_by_slot=records_by_slot
        )
        graph_seeded = True
        graph_indexes = [
            GraphitiRelationIndex(
                store, graphiti_client=_LiveGraphClientAdapter(driver)
            )
            for store, driver in zip(stores, drivers, strict=True)
        ]

        async def graph_check(scope_index: int, label: str, round_index: int) -> None:
            nonlocal graph_path_misses
            expected_slot = 0 if label == "stale" else 4
            ids, latency = await _graph_search(
                graph_indexes[(scope_index + round_index) % len(graph_indexes)],
                scope_index=scope_index,
                label=label,
                scope=scopes[scope_index],
            )
            graph_search_latencies.append(latency)
            graph_path_misses += int(
                records_by_slot[(scope_index, expected_slot)].memory_id not in ids
            )

        await asyncio.gather(
            *(
                graph_check(scope_index, label, round_index)
                for round_index in range(int(contract["graph_rounds"]))
                for scope_index in range(len(scopes))
                for label in ("stale", "live")
            )
        )

        async def transition_race(scope_index: int) -> tuple[int, int]:
            record = records_by_slot[(scope_index, 1)]

            async def attempt(store: PostgreSQLStore) -> str:
                try:
                    await store.transition(
                        scopes[scope_index],
                        record.memory_id,
                        MemoryState.EXPIRED,
                        expected_state=MemoryState.CONFIRMED,
                    )
                    return "won"
                except MemoryStateConflictError:
                    return "conflict"

            results = await asyncio.gather(attempt(stores[0]), attempt(stores[1]))
            return results.count("won"), results.count("conflict")

        race_results = await asyncio.gather(
            *(transition_race(index) for index in range(len(scopes)))
        )
        transition_race_violations += sum(
            won != 1 or conflict != 1 for won, conflict in race_results
        )

        for scope_index, scope in enumerate(scopes):
            expired_graph = records_by_slot[(scope_index, 0)]
            await stores[scope_index % len(stores)].transition(
                scope,
                expired_graph.memory_id,
                MemoryState.EXPIRED,
                expected_state=MemoryState.CONFIRMED,
            )
            deleted = records_by_slot[(scope_index, 2)]
            if not await stores[(scope_index + 1) % len(stores)].forget(
                scope, deleted.memory_id, hard=True
            ):
                restart_failures += 1

        stale_results = await asyncio.gather(
            *(
                _graph_search(
                    graph_indexes[scope_index % len(graph_indexes)],
                    scope_index=scope_index,
                    label="stale",
                    scope=scopes[scope_index],
                )
                for scope_index in range(len(scopes))
            )
        )
        for ids, latency in stale_results:
            graph_search_latencies.append(latency)
            stale_graph_hits += len(ids)

        reconcile_results = await asyncio.gather(
            *(
                _run_reconciler(
                    stores[(scope_index + replica) % len(stores)],
                    vector_indexes[(scope_index + replica) % len(vector_indexes)],
                    scope,
                )
                for scope_index, scope in enumerate(scopes)
                for replica in range(2)
            )
        )
        reconciliation_failures += sum(failures for _, failures in reconcile_results)
        vector_health = await vector_indexes[0].health()
        expected_indexed = (
            int(contract["logical_records"])
            - int(contract["transition_races"])
            - int(contract["stale_graph_records"])
            - int(contract["hard_deletes"])
        )
        vector_failures += int(vector_health["indexed_records"] != expected_indexed)
        if vector_health["indexed_records"] != expected_indexed:
            observe_vector_failure(
                "post_reconcile_count",
                f"expected {expected_indexed}, found {vector_health['indexed_records']}",
            )

        await asyncio.gather(*(store.close() for store in stores))
        stores = []
        restarted_stores = [
            PostgreSQLStore(
                dsn,
                min_pool_size=1,
                max_pool_size=int(contract["pool_size_per_instance"]),
            )
            for _ in range(int(contract["instances"]))
        ]
        restarted_indexes = [
            PostgreSQLVectorIndex(
                store,
                embedding_provider,
                VectorIndexConfig(create_extension=True, create_hnsw_index=False),
            )
            for store in restarted_stores
        ]
        restart_health = await asyncio.gather(
            *(store.health() for store in restarted_stores), return_exceptions=True
        )
        restart_failures += sum(
            isinstance(result, BaseException) for result in restart_health
        )
        for scope_index, scope in enumerate(scopes):
            expected = records_by_slot[(scope_index, 3)]
            hits = await restarted_indexes[scope_index % len(restarted_indexes)].search(
                str(expected.metadata["token"]), [scope], filters=FILTERS, limit=5
            )
            restart_failures += int(
                expected.memory_id not in {hit.memory_id for hit in hits}
            )
            ids, latency = await _graph_search(
                GraphitiRelationIndex(
                    restarted_stores[scope_index % len(restarted_stores)],
                    graphiti_client=_LiveGraphClientAdapter(
                        drivers[scope_index % len(drivers)]
                    ),
                ),
                scope_index=scope_index,
                label="live",
                scope=scope,
            )
            graph_search_latencies.append(latency)
            restart_failures += int(
                records_by_slot[(scope_index, 4)].memory_id not in ids
            )
    except Exception as exc:  # noqa: BLE001 - preserve first live failure
        hard_failure = f"{type(exc).__name__}: {exc}"
    finally:
        if graph_seeded and drivers:
            try:
                await drivers[0].execute_query(
                    "MATCH (node) WHERE node.group_id IN $groups DETACH DELETE node",
                    groups=groups,
                )
                raw = await drivers[0].execute_query(
                    "MATCH (node) WHERE node.group_id IN $groups "
                    "RETURN count(node) AS remaining",
                    groups=groups,
                )
                rows = _graph_query_records(raw)
                graph_cleaned = bool(
                    rows and int(rows[0].get("remaining", 0) or 0) == 0
                )
                if not graph_cleaned:
                    cleanup_errors.append("neo4j:fixtures-remain")
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(f"neo4j:{type(exc).__name__}")
        elif not graph_seeded:
            graph_cleaned = True
        for driver in drivers:
            try:
                await driver.close()
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(f"neo4j-close:{type(exc).__name__}")
        for store in [*stores, *restarted_stores]:
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

    metrics = {
        "migration_errors": migration_errors,
        "write_errors": write_errors,
        "created": created_count,
        "duplicates": duplicate_count,
        "idempotency_violations": idempotency_violations,
        "physical_duplicates": physical_duplicates,
        "scope_leakage": scope_leakage,
        "transition_race_violations": transition_race_violations,
        "vector_failures": vector_failures,
        "vector_failure_observations": vector_failure_observations,
        "unclassified_vector_failures": max(
            vector_failures - len(vector_failure_observations), 0
        ),
        "vector_replay_mutations": vector_replay_mutations,
        "vector_search_misses": vector_search_misses,
        "graph_path_misses": graph_path_misses,
        "stale_graph_hits": stale_graph_hits,
        "reconciliation_failures": reconciliation_failures,
        "restart_failures": restart_failures,
        "vector_health_before_cleanup": vector_health,
        "latency_ms": {
            "write": _latency_summary(write_latencies),
            "vector_search": _latency_summary(vector_search_latencies),
            "graph_search": _latency_summary(graph_search_latencies),
        },
        "write_wall_ms": round(write_wall_ms, 3),
        "write_throughput_ops_per_second": round(
            int(contract["write_attempts"]) / (write_wall_ms / 1_000)
            if write_wall_ms > 0
            else 0.0,
            3,
        ),
    }
    gate = quality_gate(metrics, cleanup_errors)
    if hard_failure:
        gate = {
            **gate,
            "ok": False,
            "status": "hard_failure",
            "failures": ["hard_failure", *gate["failures"]],
        }
    return {
        "result_schema_version": 1,
        "runner": RUNNER,
        "contract": contract,
        "runtime": {
            "postgres": f"{PG_HOST}:{PG_PORT}/{PG_DATABASE}",
            "instances": int(contract["instances"]),
            "vector": _embedding_runtime_metadata(embedding_provider),
            "graph": "neo4j_graphiti_typed_relation_path",
            "llm_calls": 0,
            "external_http_calls": 0,
            "provider_tokens": 0,
            "credentials_persisted": False,
        },
        "metrics": metrics,
        "cleanup": {
            "neo4j_cleanup_performed": graph_cleaned,
            "postgres_cleanup_performed": postgres_reset,
            "errors": cleanup_errors,
        },
        "hard_failure": hard_failure or None,
        "gate": gate,
    }


def _canonical_report_hash(report: dict[str, Any]) -> str:
    payload = dict(report)
    payload.pop("report_sha256", None)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    contract = workload_contract(
        instances=args.instances,
        scopes=args.scopes,
        records_per_scope=args.records_per_scope,
        duplicate_attempts=args.duplicate_attempts,
        graph_rounds=args.graph_rounds,
        seed=args.seed,
    )
    if not args.live:
        print(json.dumps({"runner": RUNNER, "mode": "dry-run", "contract": contract}, ensure_ascii=False, indent=2))
        return 0
    postgres_password = os.environ.get(args.postgres_password_env, "")
    neo4j_password = os.environ.get(args.neo4j_password_env, "")
    if not postgres_password or not neo4j_password:
        raise SystemExit("live mode requires local PostgreSQL and Neo4j password environment variables")
    provider = _LocalEmbeddingProvider(
        args.embedding_model,
        dimensions=args.embedding_dimensions,
        cache_dir=args.embedding_cache_dir,
        batch_size=args.embedding_batch_size,
    )
    report = asyncio.run(
        run_live(
            contract,
            postgres_password=postgres_password,
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=neo4j_password,
            embedding_provider=provider,
        )
    )
    report["report_sha256"] = _canonical_report_hash(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "report_sha256": report["report_sha256"],
                "hard_failure": report["hard_failure"],
                "gate": report["gate"],
                "metrics": report["metrics"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["gate"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
