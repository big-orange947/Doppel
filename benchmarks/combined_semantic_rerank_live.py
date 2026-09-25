"""Live semantic-only overfetch and whole-memory reranking ablation."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.combined_retrieval_live import (
    DEFAULT_DATASET,
    FILTERS,
    _DatasetPlanner,
    _record,
)
from benchmarks.combined_retrieval_quality import (
    CombinedQuery,
    CombinedRetrievalDataset,
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
from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryRecord,
    MemoryScope,
    MemoryState,
)
from doppel_memory.personal_rerank import PersonalMemoryRerankConfig
from doppel_memory.query import PersonalMemoryQueryConfig, PersonalMemoryQueryEngine
from doppel_memory.relation_path_retrieval import assemble_hybrid_retrieval_candidates

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data/doppel/combined-semantic-rerank-live.json"
RUNNER = "doppel.combined-semantic-rerank-live.v1"
PROFILES = ("current_baseline", "expanded_baseline", "memory_reranked")
EXPECTED_BASELINE = {
    "recall_at_5": 0.416667,
    "recall_at_10": 0.416667,
    "recall_at_20": 0.75,
}
THRESHOLDS = {
    "min_candidate_recall_at_64": 0.90,
    "min_reranked_recall_at_5": 0.75,
    "min_reranked_recall_at_10": 0.85,
    "max_reorder_membership_violations": 0,
    "max_scope_leakage": 0,
    "max_ineligible_hits": 0,
    "max_candidates": 20,
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
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


async def run_live(
    dataset: CombinedRetrievalDataset,
    *,
    postgres_password: str,
    embedding_provider: Any,
    memory_reranker: Any,
    rerank_window: int,
) -> dict[str, Any]:
    if not 1 <= rerank_window <= 100:
        raise ValueError("rerank window must be between 1 and 100")
    semantic_cases = [
        item for item in dataset.queries if item.category == "semantic_nonrelation"
    ]
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
    run_token = hashlib.sha256(dataset.fingerprint.encode("utf-8")).hexdigest()[:12]
    scopes = {
        name: MemoryScope(
            user_id=f"{item.user_id}:semantic-rerank:{run_token}",
            agent_id=item.agent_id,
        )
        for name, item in dataset.scopes.items()
    }
    records = [_record(item, scopes[item.scope]) for item in dataset.fixtures]
    rows_by_profile: dict[str, list[dict[str, Any]]] = {
        name: [] for name in PROFILES
    }
    diagnostics: list[dict[str, Any]] = []
    rerank_statuses: dict[str, int] = {}
    reorder_membership_violations = 0
    postgres_reset = False
    cleanup_errors: list[str] = []
    try:
        for record in records:
            result = await store.put(record)
            if not result.accepted:
                raise RuntimeError(f"fixture write failed: {record.memory_id}")
        vector_index = await _build_vector_candidates(
            store, records, embedding_provider
        )
        base_engine = PersonalMemoryQueryEngine(
            store,
            PersonalMemoryQueryConfig(limit=100, semantic_candidate_limit=100),
            semantic_index=vector_index,
        )
        reranked_engine = PersonalMemoryQueryEngine(
            store,
            PersonalMemoryQueryConfig(limit=100, semantic_candidate_limit=100),
            semantic_index=vector_index,
            memory_reranker=memory_reranker,
            rerank_config=PersonalMemoryRerankConfig(
                max_candidates=rerank_window,
                max_input_chars=100_000,
                timeout_seconds=120,
            ),
        )

        for case in semantic_cases:
            scope = scopes[case.scope]
            now = max(_timestamp(case.valid_at), datetime(2026, 9, 25, tzinfo=UTC))
            base_started = time.perf_counter()
            base_result = await base_engine.query(
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
            if {item.record.memory_id for item in base_window} != {
                item.record.memory_id for item in reranked_window
            }:
                reorder_membership_violations += 1
            status = (
                reranked_result.memory_reranking.status
                if reranked_result.memory_reranking is not None
                else "not_run"
            )
            rerank_statuses[status] = rerank_statuses.get(status, 0) + 1

            current = await _assemble(store, base_result.hits[:20], scope, limit=20)
            expanded = await _assemble(store, base_result.hits, scope, limit=20)
            reranked = await _assemble(store, reranked_result.hits, scope, limit=20)
            base_raw_ids = [item.record.memory_id for item in base_result.hits]
            required = case.required_memory_ids[0]
            raw_rank = _rank(base_raw_ids, required)
            diagnostics.append(
                {
                    "case_id": case.case_id,
                    "required_memory_id": required,
                    "baseline_raw_rank": raw_rank,
                    "classification": classify_baseline_rank(raw_rank, rerank_window),
                    "reranking_status": status,
                }
            )
            for profile, assembly, latency in (
                ("current_baseline", current, base_latency),
                ("expanded_baseline", expanded, base_latency),
                ("memory_reranked", reranked, rerank_latency),
            ):
                rows_by_profile[profile].append(
                    _row(
                        case,
                        [item.record for item in assembly.candidates],
                        scope,
                        latency,
                    )
                )
    finally:
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

    profiles = {name: summarize(rows) for name, rows in rows_by_profile.items()}
    candidate_recall = _ratio(
        sum(
            item["baseline_raw_rank"] is not None
            and item["baseline_raw_rank"] <= rerank_window
            for item in diagnostics
        ),
        len(diagnostics),
    )
    gate = quality_gate(
        profiles,
        candidate_recall_at_64=candidate_recall,
        reorder_membership_violations=reorder_membership_violations,
        rerank_statuses=rerank_statuses,
        postgres_reset=postgres_reset,
    )
    return {
        "result_schema_version": 1,
        "runner": RUNNER,
        "dataset": {
            "suite": dataset.suite,
            "version": dataset.version,
            "fingerprint": dataset.fingerprint,
            "semantic_queries": len(semantic_cases),
            "memories": len(dataset.fixtures),
            "frozen": dataset.frozen,
            "publication_ready": dataset.publication_ready,
        },
        "runtime": {
            "store": "postgresql",
            "vector": "pgvector",
            "embedding": _embedding_runtime_metadata(embedding_provider),
            "reranker": {
                "name": memory_reranker.name,
                "version": memory_reranker.version,
                "window": rerank_window,
            },
            "llm_calls": 0,
            "external_http_calls": 0,
            "provider_tokens": 0,
            "credentials_persisted": False,
            "postgres_cleanup_performed": postgres_reset,
            "cleanup_errors": cleanup_errors,
        },
        "profiles": profiles,
        "candidate_recall_at_64": candidate_recall,
        "reorder_membership_violations": reorder_membership_violations,
        "rerank_statuses": rerank_statuses,
        "diagnostics": diagnostics,
        "gate": gate,
    }


async def _assemble(
    store: Any,
    hits: Sequence[Any],
    scope: MemoryScope,
    *,
    limit: int,
) -> Any:
    return await assemble_hybrid_retrieval_candidates(
        store,
        hits,
        [],
        [scope],
        filters=FILTERS,
        limit=limit,
        base_reserve=limit,
    )


def _row(
    case: CombinedQuery,
    records: Sequence[MemoryRecord],
    scope: MemoryScope,
    latency_ms: float,
) -> dict[str, Any]:
    ids = [item.memory_id for item in records]
    return {
        "case_id": case.case_id,
        "required": list(case.required_memory_ids),
        "ids": ids,
        "scope_leakage": sum(item.scope.scope_key != scope.scope_key for item in records),
        "ineligible_hits": sum(not _eligible(item) for item in records),
        "latency_ms": latency_ms,
    }


def _eligible(record: MemoryRecord) -> bool:
    return (
        record.state is MemoryState.CONFIRMED
        and record.authority is not FactAuthority.AGENT_OUTPUT
        and "personal-memory" in record.tags
    )


def summarize(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total = sum(len(item["required"]) for item in rows)
    reciprocal_ranks: list[float] = []
    for item in rows:
        positions = [_rank(item["ids"], required) for required in item["required"]]
        found = [position for position in positions if position is not None]
        reciprocal_ranks.append(1.0 / min(found) if found else 0.0)
    latencies = [float(item["latency_ms"]) for item in rows]
    return {
        "queries": len(rows),
        "recall_at_1": _recall_at(rows, 1, total),
        "recall_at_5": _recall_at(rows, 5, total),
        "recall_at_10": _recall_at(rows, 10, total),
        "recall_at_20": _recall_at(rows, 20, total),
        "mrr": round(statistics.mean(reciprocal_ranks), 6),
        "scope_leakage": sum(int(item["scope_leakage"]) for item in rows),
        "ineligible_hits": sum(int(item["ineligible_hits"]) for item in rows),
        "max_candidates": max((len(item["ids"]) for item in rows), default=0),
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
        },
        "details": list(rows),
    }


def quality_gate(
    profiles: dict[str, dict[str, Any]],
    *,
    candidate_recall_at_64: float,
    reorder_membership_violations: int,
    rerank_statuses: dict[str, int],
    postgres_reset: bool,
) -> dict[str, Any]:
    baseline = profiles["current_baseline"]
    reranked = profiles["memory_reranked"]
    checks = {
        "baseline_reproduced": all(
            baseline[name] == expected for name, expected in EXPECTED_BASELINE.items()
        ),
        "candidate_recall_at_64": candidate_recall_at_64
        >= THRESHOLDS["min_candidate_recall_at_64"],
        "reranked_recall_at_5": reranked["recall_at_5"]
        >= THRESHOLDS["min_reranked_recall_at_5"],
        "reranked_recall_at_10": reranked["recall_at_10"]
        >= THRESHOLDS["min_reranked_recall_at_10"],
        "mrr_non_regression": reranked["mrr"] >= baseline["mrr"],
        "reorder_membership": reorder_membership_violations
        <= THRESHOLDS["max_reorder_membership_violations"],
        "reranker_completed": rerank_statuses == {"completed": baseline["queries"]},
        "scope_leakage": reranked["scope_leakage"]
        <= THRESHOLDS["max_scope_leakage"],
        "ineligible_hits": reranked["ineligible_hits"]
        <= THRESHOLDS["max_ineligible_hits"],
        "candidate_bound": reranked["max_candidates"]
        <= THRESHOLDS["max_candidates"],
        "postgres_cleanup": postgres_reset,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "thresholds": THRESHOLDS,
        "expected_baseline": EXPECTED_BASELINE,
    }


def classify_baseline_rank(rank: int | None, rerank_window: int) -> str:
    if rank is None:
        return "score_gate_or_index_miss"
    if rank <= 5:
        return "top_5"
    if rank <= 20:
        return "ranking_error_in_context"
    if rank <= rerank_window:
        return "retrieved_outside_context"
    return "outside_rerank_window"


def _recall_at(rows: Sequence[dict[str, Any]], limit: int, total: int) -> float:
    found = sum(
        required in item["ids"][:limit]
        for item in rows
        for required in item["required"]
    )
    return _ratio(found, total)


def _rank(ids: Sequence[str], required: str) -> int | None:
    try:
        return list(ids).index(required) + 1
    except ValueError:
        return None


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 1.0


def _fingerprint(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


async def _main_async(args: argparse.Namespace) -> int:
    password = os.environ.get(args.postgres_password_env, "")
    if not password:
        raise RuntimeError("local PostgreSQL password variable is required")
    dataset = load_dataset(args.dataset)
    embedding = _LocalEmbeddingProvider(
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
        await embedding.warmup()
        await relation_reranker.warmup()
        report = await run_live(
            dataset,
            postgres_password=password,
            embedding_provider=embedding,
            memory_reranker=memory_reranker,
            rerank_window=args.rerank_window,
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
    return 0 if report["gate"]["ok"] else 1


def main() -> int:
    return asyncio.run(_main_async(parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
