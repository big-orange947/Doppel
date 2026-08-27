"""Smoke tests for the repository-only Store benchmark harness."""

from __future__ import annotations

import json

import pytest

from benchmarks.dataset import SyntheticDatasetConfig, generate_dataset
from benchmarks.store_benchmark import benchmark_store, run_store_benchmark
from benchmarks.style_quality import (
    load_style_quality_dataset,
    run_style_quality_benchmark,
)
from benchmarks.vector_quality import load_vector_quality_dataset
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


async def test_style_quality_benchmark_has_independent_positive_and_negative_gates() -> (
    None
):
    result = await run_style_quality_benchmark(load_style_quality_dataset())

    assert result["result_schema_version"] == 1
    assert result["dataset"]["name"] == "doppel.observable-style.v1"
    assert result["professor"]["directive_count"] > 0
    assert result["professor"]["prompt_chars"] <= 800
    assert result["correctness"] == {"passed": True, "errors": []}
    cases = {case["name"]: case for case in result["cases"]}
    assert cases["matched-distribution"]["report"]["passed"] is True
    assert cases["contrasting-distribution"]["report"]["passed"] is False
    assert (
        cases["matched-distribution"]["report"]["aggregate_score"]
        > cases["contrasting-distribution"]["report"]["aggregate_score"]
    )


def test_style_result_schema_tracks_the_runner_envelope() -> None:
    with open("benchmarks/style-result.schema.json", encoding="utf-8") as source:
        schema = json.load(source)
    assert schema["properties"]["result_schema_version"]["const"] == 1
    assert schema["$defs"]["styleQualityReport"]["additionalProperties"] is False
    assert set(schema["required"]) == {
        "result_schema_version",
        "doppel_version",
        "generated_at",
        "dataset",
        "professor",
        "cases",
        "correctness",
    }


def test_vector_quality_fixture_is_scope_adversarial_and_deterministic() -> None:
    first = load_vector_quality_dataset()
    second = load_vector_quality_dataset()
    assert first.fingerprint == second.fingerprint
    assert first.name == "doppel.pgvector-fixture.v1"
    assert first.dimensions == 3
    record_scopes = {record.memory_id: record.scope for record in first.records}
    assert all(query.forbidden_memory_ids for query in first.queries)
    assert all(
        record_scopes[query.expected_memory_id] == query.scope
        and all(
            record_scopes[memory_id] != query.scope
            for memory_id in query.forbidden_memory_ids
        )
        for query in first.queries
    )


def test_vector_result_schema_tracks_the_runner_envelope() -> None:
    with open("benchmarks/vector-result.schema.json", encoding="utf-8") as source:
        schema = json.load(source)
    assert schema["properties"]["result_schema_version"]["const"] == 1
    assert schema["properties"]["correctness"]["additionalProperties"] is False
    assert set(schema["required"]) == {
        "result_schema_version",
        "doppel_version",
        "generated_at",
        "dataset",
        "index",
        "cases",
        "correctness",
    }
