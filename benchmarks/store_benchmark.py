"""Run reproducible performance and isolation checks against stable Stores."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import platform
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from benchmarks.dataset import (
    SyntheticDataset,
    SyntheticDatasetConfig,
    generate_dataset,
    load_dataset_config,
)
from doppel_memory import (
    InMemoryStore,
    MemoryFilter,
    MemoryKind,
    MemoryStore,
    SQLiteStore,
    WriteStatus,
    __version__,
)

RESULT_SCHEMA_VERSION = 1


async def run_store_benchmark(
    config: SyntheticDatasetConfig,
    *,
    backend: str,
    database: str | None = None,
    warmup: int = 3,
) -> dict[str, Any]:
    """Run one benchmark without retaining backend state between invocations."""
    if warmup < 0:
        raise ValueError("warmup must be >= 0")
    temporary_directory: tempfile.TemporaryDirectory[str] | None = None
    if backend == "memory":
        store: MemoryStore = InMemoryStore()
    elif backend == "sqlite":
        if database is None:
            temporary_directory = tempfile.TemporaryDirectory(
                prefix="doppel-benchmark-"
            )
            database = str(Path(temporary_directory.name) / "benchmark.sqlite3")
        elif Path(database).exists():
            raise ValueError("benchmark SQLite database must not already exist")
        store = SQLiteStore(database=database)
    else:
        raise ValueError(f"unsupported benchmark backend: {backend!r}")

    try:
        return await benchmark_store(config, store, backend_name=backend, warmup=warmup)
    finally:
        await store.close()
        if temporary_directory is not None:
            temporary_directory.cleanup()


async def benchmark_store(
    config: SyntheticDatasetConfig,
    store: MemoryStore,
    *,
    backend_name: str,
    warmup: int = 3,
) -> dict[str, Any]:
    """Benchmark a caller-owned Store, including third-party implementations."""
    if warmup < 0:
        raise ValueError("warmup must be >= 0")
    if not backend_name.strip():
        raise ValueError("backend_name must not be empty")
    return await _execute(
        generate_dataset(config),
        store,
        backend=backend_name.strip(),
        warmup=warmup,
    )


async def _execute(
    dataset: SyntheticDataset,
    store: MemoryStore,
    *,
    backend: str,
    warmup: int,
) -> dict[str, Any]:
    errors: list[str] = []

    write_latencies: list[float] = []
    write_start = perf_counter()
    created = 0
    for record in dataset.records:
        started = perf_counter()
        result = await store.put(record, idempotency_key=record.idempotency_key)
        write_latencies.append(_milliseconds_since(started))
        if result.status is WriteStatus.CREATED:
            created += 1
        else:
            errors.append(f"initial write {record.memory_id}: {result.status.value}")
    write_seconds = perf_counter() - write_start

    records_by_id = {record.memory_id: record for record in dataset.records}
    duplicate_latencies: list[float] = []
    duplicate_failures = 0
    duplicate_start = perf_counter()
    for query in dataset.queries:
        record = records_by_id[query.expected_memory_id]
        started = perf_counter()
        result = await store.put(record, idempotency_key=record.idempotency_key)
        duplicate_latencies.append(_milliseconds_since(started))
        if result.status is not WriteStatus.DUPLICATE:
            duplicate_failures += 1
    duplicate_seconds = perf_counter() - duplicate_start

    for query in dataset.queries[:warmup]:
        await store.search(query.text, [query.scope], limit=10)

    search_latencies: list[float] = []
    missing_expected = 0
    forbidden_hits = 0
    scope_leakage = 0
    search_start = perf_counter()
    for query in dataset.queries:
        started = perf_counter()
        hits = await store.search(query.text, [query.scope], limit=10)
        search_latencies.append(_milliseconds_since(started))
        hit_ids = {hit.memory_id for hit in hits}
        if query.expected_memory_id not in hit_ids:
            missing_expected += 1
        forbidden_hits += len(hit_ids.intersection(query.forbidden_memory_ids))
        scope_leakage += sum(
            hit.scope is None or hit.scope.scope_key != query.scope.scope_key
            for hit in hits
        )
    search_seconds = perf_counter() - search_start

    filter_latencies: list[float] = []
    filter_scope_leakage = 0
    filter_start = perf_counter()
    for query in dataset.queries:
        started = perf_counter()
        hits = await store.search(
            "",
            [query.scope],
            filters=MemoryFilter(kinds={MemoryKind.FACT}, importance_min=0.5),
            limit=10,
        )
        filter_latencies.append(_milliseconds_since(started))
        filter_scope_leakage += sum(
            hit.scope is None or hit.scope.scope_key != query.scope.scope_key
            for hit in hits
        )
        if any(hit.kind != MemoryKind.FACT for hit in hits):
            errors.append("filtered search returned a non-fact memory")
        if any(
            records_by_id[hit.memory_id].importance < 0.5
            for hit in hits
            if hit.memory_id in records_by_id
        ):
            errors.append("filtered search returned a low-importance memory")
    filter_seconds = perf_counter() - filter_start

    scan_latencies: list[float] = []
    scanned_ids: set[str] = set()
    scan_duplicate_records = 0
    scan_scope_leakage = 0
    scan_start = perf_counter()
    for scope in dataset.scopes:
        cursor = ""
        while True:
            started = perf_counter()
            page = await store.scan(
                scope, cursor=cursor, limit=dataset.config.page_size
            )
            scan_latencies.append(_milliseconds_since(started))
            for record in page.records:
                if record.memory_id in scanned_ids:
                    scan_duplicate_records += 1
                scanned_ids.add(record.memory_id)
                if record.scope.scope_key != scope.scope_key:
                    scan_scope_leakage += 1
            if not page.has_more:
                break
            if not page.next_cursor or page.next_cursor == cursor:
                errors.append("scan returned a non-advancing cursor")
                break
            cursor = page.next_cursor
    scan_seconds = perf_counter() - scan_start
    scan_count_mismatch = abs(len(scanned_ids) - dataset.config.record_count)

    total_scope_leakage = scope_leakage + filter_scope_leakage + scan_scope_leakage
    correctness = {
        "passed": not any(
            (
                errors,
                duplicate_failures,
                missing_expected,
                forbidden_hits,
                total_scope_leakage,
                scan_duplicate_records,
                scan_count_mismatch,
            )
        ),
        "scope_leakage_count": total_scope_leakage,
        "forbidden_memory_hits": forbidden_hits,
        "missing_expected_memories": missing_expected,
        "duplicate_write_failures": duplicate_failures,
        "scan_duplicate_records": scan_duplicate_records,
        "scan_count_mismatch": scan_count_mismatch,
        "errors": errors,
    }
    return {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "doppel_version": __version__,
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": {
            "dataset_version": dataset.config.dataset_version,
            "generator": dataset.config.generator,
            "fingerprint": dataset.config.fingerprint,
            "seed": dataset.config.seed,
            "scope_count": dataset.config.scope_count,
            "records_per_scope": dataset.config.records_per_scope,
            "record_count": dataset.config.record_count,
            "query_samples": dataset.config.query_samples,
            "page_size": dataset.config.page_size,
        },
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "backend": {
            "name": backend,
            "capabilities": store.capabilities.model_dump(),
        },
        "metrics": {
            "write": _metric(
                len(dataset.records), write_seconds, write_latencies, created=created
            ),
            "duplicate_write": _metric(
                len(dataset.queries),
                duplicate_seconds,
                duplicate_latencies,
            ),
            "exact_scope_search": _metric(
                len(dataset.queries), search_seconds, search_latencies
            ),
            "filtered_search": _metric(
                len(dataset.queries), filter_seconds, filter_latencies
            ),
            "scan": _metric(
                len(scan_latencies),
                scan_seconds,
                scan_latencies,
                records_scanned=len(scanned_ids),
                records_per_second=(
                    len(scanned_ids) / scan_seconds if scan_seconds else 0.0
                ),
            ),
        },
        "correctness": correctness,
    }


def _metric(
    operations: int,
    seconds: float,
    latencies: Sequence[float],
    **extra: float,
) -> dict[str, Any]:
    return {
        "operations": operations,
        "total_seconds": round(seconds, 6),
        "operations_per_second": round(operations / seconds, 3) if seconds else 0.0,
        "latency_ms": {
            "min": _rounded(min(latencies, default=0.0)),
            "p50": _rounded(_percentile(latencies, 50)),
            "p95": _rounded(_percentile(latencies, 95)),
            "p99": _rounded(_percentile(latencies, 99)),
            "max": _rounded(max(latencies, default=0.0)),
        },
        **{key: _rounded(value) for key, value in extra.items()},
    }


def _percentile(values: Sequence[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile / 100 * len(ordered)) - 1)
    return ordered[index]


def _milliseconds_since(started: float) -> float:
    return (perf_counter() - started) * 1_000


def _rounded(value: float) -> float:
    return round(value, 3)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark Doppel Store performance and exact-scope isolation."
    )
    parser.add_argument("--backend", choices=("memory", "sqlite"), default="sqlite")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).parent / "datasets" / "synthetic-small.json",
    )
    parser.add_argument(
        "--database",
        help="SQLite path; omitted uses and removes a temporary database.",
    )
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = load_dataset_config(args.dataset)
    result = asyncio.run(
        run_store_benchmark(
            config,
            backend=args.backend,
            database=args.database,
            warmup=args.warmup,
        )
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"benchmark result: {args.output}")
    else:
        sys.stdout.write(rendered)
    return 0 if result["correctness"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
