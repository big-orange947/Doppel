"""Contracts for the live hybrid path-candidate development benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import benchmarks.hybrid_path_candidate_ablation as hybrid_ablation
from benchmarks.candidate_relation_path_ablation import load_dataset
from benchmarks.hybrid_path_candidate_ablation import (
    RUNNER,
    _DatasetPlanner,
    _metric_row,
    _record,
)
from benchmarks.personal_relation_path_ablation import _timestamp
from doppel_memory.models import MemoryScope
from doppel_memory.query import PersonalMemoryQueryRequest

ROOT = Path(__file__).resolve().parents[1]
DATASET = (
    ROOT / "benchmarks" / "datasets" / "candidate-relation-path-ablation-zh-v2.json"
)


@pytest.mark.asyncio
async def test_dataset_planner_binds_only_benchmark_time_and_entities() -> None:
    valid_at = _timestamp("2026-06-01T00:00:00+00:00")
    planner = _DatasetPlanner(
        query="相机现在放在哪里？",
        entity_mentions=["相机"],
        valid_at=valid_at,
    )
    request = PersonalMemoryQueryRequest(
        query="相机现在放在哪里？",
        now=_timestamp("2026-09-23T00:00:00+00:00"),
        default_subject="owner",
        default_subject_id="owner-1",
    )

    draft = await planner.plan(request)

    assert draft.operation == "lookup"
    assert draft.temporal_view == "as_of"
    assert draft.as_of == valid_at
    assert draft.entity_mentions == ["相机"]
    assert draft.subject_id == "owner-1"
    assert draft.relation_types == []


def test_fixture_projection_preserves_temporal_provenance() -> None:
    dataset = load_dataset(DATASET)
    item = dataset.fixtures[0]
    scope = MemoryScope(user_id="owner-1", agent_id="agent-1")

    record = _record(item, scope)

    assert record.memory_id == item.memory_id
    assert record.scope == scope
    assert record.metadata["valid_from"] == item.valid_from
    assert record.metadata["evidence"] == [
        {"evidence_id": f"dataset:{item.memory_id}"}
    ]
    assert "personal-memory" in record.tags


def test_metric_row_keeps_related_noise_separate_from_forbidden() -> None:
    case = SimpleNamespace(
        query_id="q1",
        category="test",
        partition="dev",
        required_hop_memory_ids=[["m1"]],
        forbidden_memory_ids=["m2"],
        candidate_noise_memory_ids=["m3"],
        recovery_expected=True,
    )

    row = _metric_row(
        case,
        memory_ids=["m1", "m3"],
        scope_keys=["scope-a", "scope-a"],
        authorized_scope_key="scope-a",
        graph_route_queries=2,
        latency_ms=4.0,
    )

    assert row["candidate_noise_memory_ids"] == ["m3"]
    assert row["forbidden_memory_ids"] == ["m2"]
    assert row["dedupe_ok"] is True
    assert row["graph_route_queries"] == 2


@pytest.mark.asyncio
async def test_runtime_failure_report_is_structured_and_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FakeProvider:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

        async def warmup(self) -> None:
            return None

    async def fail_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        raise RuntimeError("leaked-local-secret")

    output = tmp_path / "failure.json"
    monkeypatch.setenv("DOPPEL_TEST_NEO4J_PASSWORD", "neo4j-secret")
    monkeypatch.setenv("DOPPEL_TEST_PG_PASSWORD", "postgres-secret")
    monkeypatch.setattr(hybrid_ablation, "_LocalEmbeddingProvider", _FakeProvider)
    monkeypatch.setattr(hybrid_ablation, "run_ablation", fail_run)
    args = argparse.Namespace(
        dataset=DATASET,
        output=output,
        neo4j_uri="bolt://127.0.0.1:1",
        neo4j_user="neo4j",
        neo4j_password_env="DOPPEL_TEST_NEO4J_PASSWORD",
        postgres_password_env="DOPPEL_TEST_PG_PASSWORD",
        embedding_model="tests",
        embedding_dimensions=2,
        embedding_cache_dir=None,
        embedding_batch_size=1,
    )

    assert await hybrid_ablation._main_async(args) == 1
    serialized = output.read_text(encoding="utf-8")
    report = json.loads(serialized)
    assert report["runner"] == RUNNER
    assert report["hard_failure"] == "RuntimeError"
    assert report["gate"] == {
        "ok": False,
        "failures": ["runtime_unavailable"],
    }
    assert "leaked-local-secret" not in serialized
    assert "neo4j-secret" not in serialized
    assert "postgres-secret" not in serialized
