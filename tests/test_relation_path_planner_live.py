"""Budget, cache, and dry-run contracts for live path-planner evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.relation_path_planner_live import (
    DEFAULT_CATALOG,
    DEFAULT_DATASET,
    _quality_gate,
    build_plan,
    execute_live,
)
from benchmarks.relation_path_planner_quality import (
    load_dataset,
    load_relation_catalog,
)
from doppel_memory.intelligence import StructuredGenerationRequest
from doppel_memory.openai_compatible import StructuredOutputProviderError


class _GoldModel:
    name = "tests.gold-live-path-model"
    version = "1"

    def __init__(self, by_query: dict[str, Any]) -> None:
        self.by_query = by_query
        self.calls = 0

    async def generate(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        self.calls += 1
        case = self.by_query[str(request.input["query"])]
        return {
            "schema_version": 3,
            "operation": "lookup",
            "temporal_view": "unbounded",
            "search_text": str(request.input["query"]),
            "entity_mentions": case.expected_entity_mentions,
            "relation_types": [],
            "subject": "owner",
            "subject_id": "ignored-model-subject",
            "path_steps": [
                step.model_dump(mode="json") for step in case.expected_path_steps
            ],
            "path_confidence": 0.99 if case.expected_path_steps else 0,
        }


def _model() -> _GoldModel:
    dataset = load_dataset(DEFAULT_DATASET)
    return _GoldModel({case.query: case for case in dataset.cases})


def test_dry_run_plan_is_bounded_partitioned_and_secret_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOPPEL_API_KEY", "must-not-appear")

    plan = build_plan(
        dataset_path=DEFAULT_DATASET,
        catalog_path=DEFAULT_CATALOG,
        partitions=["dev"],
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        schema_mode="json_object",
        max_completion_tokens=1024,
        max_tokens_parameter="max_tokens",
        thinking="disabled",
        max_calls=12,
        cache_enabled=True,
    )

    assert plan["mode"] == "dry_run"
    assert plan["paid_calls_enabled"] is False
    assert plan["case_counts"] == {"dev": 11, "heldout": 0, "adversarial": 0}
    assert plan["maximum_provider_calls"] == 12
    assert plan["provider"]["retries"] == 0
    assert plan["provider"]["max_completion_tokens"] == 1024
    assert "must-not-appear" not in json.dumps(plan)


@pytest.mark.asyncio
async def test_live_runner_caches_raw_outputs_without_spending_on_second_run(
    tmp_path: Path,
) -> None:
    dataset = load_dataset(DEFAULT_DATASET)
    definitions = load_relation_catalog(DEFAULT_CATALOG)
    model = _model()

    first = await execute_live(
        dataset=dataset,
        definitions=definitions,
        model=model,
        partitions=["dev"],
        cache_dir=tmp_path,
        max_calls=12,
        provider_metadata={"model": "fake"},
    )
    second = await execute_live(
        dataset=dataset,
        definitions=definitions,
        model=model,
        partitions=["dev"],
        cache_dir=tmp_path,
        max_calls=0,
        provider_metadata={"model": "fake"},
    )

    assert model.calls == 11
    assert first["metrics"]["exact_path_accuracy"] == 1
    assert first["budget"]["provider_calls"] == 11
    assert second["cache"]["hits"] == 11
    assert second["cache"]["misses"] == 0
    assert second["budget"]["provider_calls"] == 0
    assert second["execution"]["complete"] is True


@pytest.mark.asyncio
async def test_budget_blocks_calls_before_provider_and_reports_incomplete(
    tmp_path: Path,
) -> None:
    dataset = load_dataset(DEFAULT_DATASET)
    model = _model()

    report = await execute_live(
        dataset=dataset,
        definitions=load_relation_catalog(DEFAULT_CATALOG),
        model=model,
        partitions=["dev"],
        cache_dir=tmp_path,
        max_calls=2,
        provider_metadata={"model": "fake"},
    )

    assert model.calls == 2
    assert report["budget"]["provider_calls"] == 2
    assert report["metrics"]["valid_case_count"] == 2
    assert report["metrics"]["error_count"] == 9
    assert report["execution"]["complete"] is False
    assert report["cases"][2]["error_code"] == "budget_exhausted"
    assert all(
        case["error"] == "PlannerNotRun" for case in report["cases"][3:]
    )


@pytest.mark.asyncio
async def test_systemic_provider_error_stops_after_one_attempt(tmp_path: Path) -> None:
    class FailingModel:
        name = "tests.failing-live-path-model"
        version = "1"

        def __init__(self) -> None:
            self.calls = 0

        async def generate(
            self, request: StructuredGenerationRequest
        ) -> dict[str, Any]:
            self.calls += 1
            raise StructuredOutputProviderError(
                "authentication_error",
                "sanitized synthetic error",
                status_code=401,
            )

    model = FailingModel()
    report = await execute_live(
        dataset=load_dataset(DEFAULT_DATASET),
        definitions=load_relation_catalog(DEFAULT_CATALOG),
        model=model,
        partitions=["dev"],
        cache_dir=tmp_path,
        max_calls=11,
        provider_metadata={"model": "fake"},
    )

    assert model.calls == 1
    assert report["budget"]["provider_calls"] == 1
    assert report["cases"][0]["error_code"] == "authentication_error"
    assert report["cases"][0]["http_status"] == 401
    assert report["cases"][1]["error_code"] == "previous_fatal_provider_error"
    assert report["execution"]["complete"] is False


def test_quality_gate_separates_completion_and_quality_thresholds() -> None:
    report = {
        "execution": {"complete": True},
        "metrics": {
            "exact_path_accuracy": 0.75,
            "no_path_accuracy": 1.0,
            "forbidden_relation_type_hits": 1,
        },
    }

    gate = _quality_gate(
        report,
        min_exact_path_accuracy=0.8,
        min_no_path_accuracy=1.0,
        max_forbidden_relation_type_hits=0,
    )

    assert gate["passed"] is False
    assert gate["failures"] == [
        "exact_path_accuracy below threshold",
        "forbidden relation-type hits exceed threshold",
    ]
