"""Smoke tests for the repository-only Store benchmark harness."""

from __future__ import annotations

import json

import pytest

from benchmarks.dataset import SyntheticDatasetConfig, generate_dataset
from benchmarks.store_benchmark import benchmark_store, run_store_benchmark
from doppel_memory import InMemoryStore


def _config() -> SyntheticDatasetConfig:
    return SyntheticDatasetConfig(
        dataset_version=1,
        generator="doppel.synthetic.v1",
        seed=947,
        scope_count=2,
        records_per_scope=6,
        query_samples=4,
        page_size=3,
    )


def test_synthetic_dataset_is_deterministic_and_scope_adversarial() -> None:
    first = generate_dataset(_config())
    second = generate_dataset(_config())
    assert first.config.fingerprint == second.config.fingerprint
    assert [record.model_dump() for record in first.records] == [
        record.model_dump() for record in second.records
    ]
    assert first.queries == second.queries
    assert all(query.forbidden_memory_ids for query in first.queries)
    assert all(
        sum(query.text in record.content for record in first.records)
        == first.config.scope_count
        for query in first.queries
    )


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
async def test_store_benchmark_smoke(backend: str, tmp_path) -> None:
    database = str(tmp_path / "benchmark.sqlite3") if backend == "sqlite" else None
    result = await run_store_benchmark(
        _config(), backend=backend, database=database, warmup=1
    )
    assert result["result_schema_version"] == 1
    assert result["dataset"]["record_count"] == 12
    assert result["backend"]["name"] == backend
    assert result["metrics"]["write"]["created"] == 12
    assert result["metrics"]["scan"]["records_scanned"] == 12
    assert result["correctness"] == {
        "passed": True,
        "scope_leakage_count": 0,
        "forbidden_memory_hits": 0,
        "missing_expected_memories": 0,
        "duplicate_write_failures": 0,
        "scan_duplicate_records": 0,
        "scan_count_mismatch": 0,
        "errors": [],
    }


async def test_third_party_runner_keeps_store_lifecycle_with_caller() -> None:
    store = InMemoryStore()
    result = await benchmark_store(
        _config(), store, backend_name="custom-memory", warmup=0
    )
    assert result["backend"]["name"] == "custom-memory"
    assert (await store.health())["records"] == 12


async def test_sqlite_benchmark_refuses_an_existing_database(tmp_path) -> None:
    database = tmp_path / "existing.sqlite3"
    database.touch()
    with pytest.raises(ValueError, match="must not already exist"):
        await run_store_benchmark(_config(), backend="sqlite", database=str(database))


def test_result_schema_tracks_the_runner_envelope() -> None:
    with open("benchmarks/result.schema.json", encoding="utf-8") as source:
        schema = json.load(source)
    assert schema["properties"]["result_schema_version"]["const"] == 1
    assert set(schema["required"]) == {
        "result_schema_version",
        "doppel_version",
        "generated_at",
        "dataset",
        "environment",
        "backend",
        "metrics",
        "correctness",
    }
