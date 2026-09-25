"""Offline contract tests for the multi-instance live reliability gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.multi_instance_reliability_live import (
    DEFAULT_DUPLICATE_ATTEMPTS,
    DEFAULT_GRAPH_ROUNDS,
    DEFAULT_INSTANCES,
    DEFAULT_POOL_SIZE_PER_INSTANCE,
    DEFAULT_RECORDS_PER_SCOPE,
    DEFAULT_SCOPES,
    _attempt_record,
    _canonical_report_hash,
    _percentile,
    _scopes,
    quality_gate,
    workload_contract,
)


def _passing_metrics() -> dict:
    return {
        "migration_errors": 0,
        "write_errors": 0,
        "idempotency_violations": 0,
        "physical_duplicates": 0,
        "scope_leakage": 0,
        "transition_race_violations": 0,
        "vector_failures": 0,
        "unclassified_vector_failures": 0,
        "vector_replay_mutations": 0,
        "vector_search_misses": 0,
        "graph_path_misses": 0,
        "stale_graph_hits": 0,
        "reconciliation_failures": 0,
        "restart_failures": 0,
        "latency_ms": {
            "write": {"p95": 1.0},
            "vector_search": {"p95": 1.0},
            "graph_search": {"p95": 1.0},
        },
    }


def test_default_contract_is_frozen_and_internally_consistent() -> None:
    contract = workload_contract()
    assert contract["instances"] == DEFAULT_INSTANCES
    assert contract["pool_size_per_instance"] == DEFAULT_POOL_SIZE_PER_INSTANCE
    assert contract["total_pool_connection_budget"] == 8
    assert contract["scopes"] == DEFAULT_SCOPES
    assert contract["records_per_scope"] == DEFAULT_RECORDS_PER_SCOPE
    assert contract["duplicate_attempts_per_record"] == DEFAULT_DUPLICATE_ATTEMPTS
    assert contract["graph_rounds"] == DEFAULT_GRAPH_ROUNDS
    assert contract["logical_records"] == 128
    assert contract["write_attempts"] == 512
    assert len(contract["fingerprint"]) == 64
    assert contract == workload_contract()


@pytest.mark.parametrize(
    "override",
    [
        {"instances": 1},
        {"scopes": 1},
        {"records_per_scope": 5},
        {"duplicate_attempts": 1},
        {"graph_rounds": 0},
    ],
)
def test_contract_rejects_nonconcurrent_or_unbounded_shapes(override: dict) -> None:
    with pytest.raises(ValueError):
        workload_contract(**override)


def test_workload_reuses_idempotency_only_inside_exact_scope() -> None:
    scopes = _scopes(2, "test-run")
    first = _attempt_record(scopes[0], 0, 3, 0)
    retry = _attempt_record(scopes[0], 0, 3, 1)
    other_scope = _attempt_record(scopes[1], 1, 3, 0)
    assert first.memory_id != retry.memory_id
    assert first.idempotency_key == retry.idempotency_key
    assert first.idempotency_key == other_scope.idempotency_key
    assert first.scope.scope_key != other_scope.scope.scope_key
    assert first.content == retry.content


def test_gate_requires_every_correctness_latency_and_cleanup_check() -> None:
    passing = _passing_metrics()
    assert quality_gate(passing, [])["ok"]
    for key in (
        "migration_errors",
        "write_errors",
        "idempotency_violations",
        "physical_duplicates",
        "scope_leakage",
        "transition_race_violations",
        "vector_failures",
        "unclassified_vector_failures",
        "vector_replay_mutations",
        "vector_search_misses",
        "graph_path_misses",
        "stale_graph_hits",
        "reconciliation_failures",
        "restart_failures",
    ):
        broken = json.loads(json.dumps(passing))
        broken[key] = 1
        assert not quality_gate(broken, [])["ok"], key
    assert not quality_gate(passing, ["cleanup failed"])["ok"]
    for stage in ("write", "vector_search", "graph_search"):
        broken = json.loads(json.dumps(passing))
        broken["latency_ms"][stage]["p95"] = 10_000
        assert not quality_gate(broken, [])["ok"], stage


def test_percentile_and_report_hash_are_deterministic() -> None:
    assert _percentile([], 0.95) == 0.0
    assert _percentile([1.0], 0.95) == 1.0
    assert _percentile([1.0, 2.0, 3.0], 0.5) == 2.0
    report = {"runner": "test", "gate": {"ok": True}}
    first = _canonical_report_hash(report)
    report["report_sha256"] = first
    assert _canonical_report_hash(report) == first


def test_result_schema_is_valid_draft_2020_12() -> None:
    root = Path(__file__).resolve().parents[1]
    schema = json.loads(
        (root / "benchmarks/multi-instance-reliability-result.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["runner"]["const"].endswith(".v2")
    assert set(schema["required"]) == set(schema["properties"])
