"""Dry-run, cache, and host-decision contracts for the V5 live runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.relation_path_decision_quality import expected_decision
from benchmarks.relation_path_planner_live import DEFAULT_CATALOG, DEFAULT_DATASET
from benchmarks.relation_path_planner_quality import (
    load_dataset,
    load_relation_catalog,
)
from benchmarks.relation_path_two_stage_live import (
    _apply_sealed_quality_gates,
    _validate_sealed_first_run,
    build_plan,
    execute_live,
)
from doppel_memory.intelligence import StructuredGenerationRequest


class _GoldObservationModel:
    name = "tests.gold-live-path-observation-model"
    version = "1"

    def __init__(self, by_query: dict[str, Any]) -> None:
        self.by_query = by_query
        self.calls = 0

    async def generate(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        self.calls += 1
        case = self.by_query[str(request.input["query"])]
        decision, reason = expected_decision(case)
        if decision == "execute":
            semantics = "exact"
            steps = [
                step.model_dump(mode="json") for step in case.expected_path_steps
            ]
            confidence = 0.9
        elif reason == "over_bound":
            semantics = "exact"
            steps = [
                {"relation_types": ["HELD_BY"], "direction": "outbound"},
                {"relation_types": ["EMPLOYED_BY"], "direction": "outbound"},
                {"relation_types": ["LOCATED_AT"], "direction": "outbound"},
            ]
            confidence = 0.9
        else:
            semantics = reason
            steps = []
            confidence = 0
        return {
            "schema_version": 5,
            "operation": "lookup",
            "temporal_view": "unbounded",
            "search_text": str(request.input["query"]),
            "entity_mentions": case.expected_entity_mentions,
            "relation_types": [],
            "subject": "owner",
            "subject_id": "untrusted",
            "observed_path_semantics": semantics,
            "observed_path_steps": steps,
            "observed_path_truncated": False,
            "path_confidence": confidence,
        }


def _model() -> _GoldObservationModel:
    dataset = load_dataset(DEFAULT_DATASET)
    return _GoldObservationModel({case.query: case for case in dataset.cases})


def test_v5_dry_run_declares_two_stage_authority_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOPPEL_API_KEY", "must-not-appear")
    plan = build_plan(
        dataset_path=DEFAULT_DATASET,
        catalog_path=DEFAULT_CATALOG,
        partitions=["dev", "heldout", "adversarial"],
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        schema_mode="json_object",
        max_completion_tokens=1024,
        max_tokens_parameter="max_tokens",
        thinking="disabled",
        max_calls=32,
        cache_enabled=True,
    )

    assert plan["selected_case_count"] == 32
    assert plan["corpus_role"] == "opened_regression"
    assert plan["eligible_as_unseen_evidence"] is False
    assert plan["planner_protocol"] == "v5_model_observation_host_decision"
    assert plan["paid_calls_enabled"] is False
    assert "must-not-appear" not in json.dumps(plan)


@pytest.mark.asyncio
async def test_v5_live_regression_caches_observations_and_host_decisions(
    tmp_path: Path,
) -> None:
    dataset = load_dataset(DEFAULT_DATASET)
    definitions = load_relation_catalog(DEFAULT_CATALOG)
    model = _model()
    partitions = ["dev", "heldout", "adversarial"]

    first = await execute_live(
        dataset=dataset,
        definitions=definitions,
        model=model,
        partitions=partitions,
        cache_dir=tmp_path,
        max_calls=32,
        provider_metadata={"model": "fake"},
    )
    second = await execute_live(
        dataset=dataset,
        definitions=definitions,
        model=model,
        partitions=partitions,
        cache_dir=tmp_path,
        max_calls=0,
        provider_metadata={"model": "fake"},
    )

    assert model.calls == 32
    assert first["decision_metrics"]["decision_accuracy"] == 1
    assert first["decision_metrics"]["over_bound_reason_accuracy"] == 1
    assert first["decision_metrics"]["wrong_execute_count"] == 0
    assert first["budget"]["provider_calls"] == 32
    assert first["model_execution_authority"] is False
    assert first["host_executable_path_bound"] == 2
    sealed_gate = _apply_sealed_quality_gates(
        first, {"passed": True, "thresholds": {}, "failures": []}
    )
    assert sealed_gate["passed"] is True
    assert sealed_gate["pre_registered"] is True
    assert second["cache"]["hits"] == 32
    assert second["budget"]["provider_calls"] == 0
    assert second["execution"]["complete"] is True


def test_sealed_first_run_requires_frozen_data_empty_cache_and_new_output(
    tmp_path: Path,
) -> None:
    frozen_dataset = (
        Path(__file__).resolve().parents[1]
        / "benchmarks/datasets/relation-path-planner-quality-zh-v2.json"
    )
    cache_dir = tmp_path / "fresh-cache"
    output = tmp_path / "sealed.json"

    _validate_sealed_first_run(
        dataset_path=frozen_dataset,
        cache_dir=cache_dir,
        cache_disabled=False,
        output=output,
    )

    cache_dir.mkdir()
    (cache_dir / "existing.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="empty dedicated cache"):
        _validate_sealed_first_run(
            dataset_path=frozen_dataset,
            cache_dir=cache_dir,
            cache_disabled=False,
            output=output,
        )


def test_sealed_first_run_rejects_opened_dataset_and_implicit_output(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match="dataset.frozen=true"):
        _validate_sealed_first_run(
            dataset_path=DEFAULT_DATASET,
            cache_dir=tmp_path / "cache",
            cache_disabled=False,
            output=tmp_path / "sealed.json",
        )

    frozen_dataset = (
        Path(__file__).resolve().parents[1]
        / "benchmarks/datasets/relation-path-planner-quality-zh-v2.json"
    )
    with pytest.raises(RuntimeError, match="explicit --output"):
        _validate_sealed_first_run(
            dataset_path=frozen_dataset,
            cache_dir=tmp_path / "cache",
            cache_disabled=False,
            output=None,
        )
