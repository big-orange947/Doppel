from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks import query_plan_v2_ablation as ablation
from benchmarks.personal_retrieval_ablation import load_ablation_dataset
from benchmarks.relation_planner_quality import run_relation_planner_quality
from doppel_memory import (
    PersonalMemoryQueryDraftV2,
    PersonalMemoryQueryRequest,
)


class _GoldV2Planner:
    name = "tests.gold-query-plan-v2"
    version = "1"

    def __init__(self, dataset: Any) -> None:
        self.dataset = dataset
        self.by_query = {item.query: item for item in dataset.queries}

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraftV2:
        item = self.by_query[request.query]
        operation, temporal_views = ablation._expected_axes(item)
        preferred_view = ablation._temporal_view_from_shape(
            item.intent,
            as_of=item.as_of,
            time_from=item.time_from,
            time_to=item.time_to,
        )
        assert preferred_view in temporal_views
        return PersonalMemoryQueryDraftV2(
            operation=operation,
            temporal_view=preferred_view,
            search_text=item.query,
            entity_mentions=item.entity_mentions,
            relation_hints=item.relation_hints,
            relation_types=self.dataset.relation_type_labels[item.query_id],
            as_of=item.as_of,
            time_from=item.time_from,
            time_to=item.time_to,
            subject=request.default_subject,
            subject_id=request.default_subject_id,
        )


def test_dry_plan_fixes_equal_240_case_arms_without_reading_key(
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
    args = ablation._parser().parse_args([])

    plan = ablation.build_plan(args)

    assert plan["mode"] == "dry_run"
    assert plan["query_count_per_arm"] == 240
    assert plan["max_calls_per_arm"] == 240
    assert plan["max_total_provider_calls"] == 480
    assert plan["settings"] == {
        "model": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com",
        "schema_mode": "json_object",
        "max_completion_tokens": 768,
        "max_tokens_parameter": "max_tokens",
        "thinking": "disabled",
        "temperature": 0,
    }


@pytest.mark.asyncio
async def test_v2_gold_axes_score_independently_on_all_240_queries() -> None:
    dataset = load_ablation_dataset(ablation.DEFAULT_DATASET)
    inner = _GoldV2Planner(dataset)
    planner = ablation._CapturingV2CompatibilityPlanner(inner)

    report = await run_relation_planner_quality(dataset, planner)
    report = ablation._augment_report(
        report, dataset, arm="v2", drafts=planner.drafts
    )

    assert report["metrics"]["case_count"] == 240
    assert report["metrics"]["valid_case_count"] == 240
    assert report["metrics"]["operation_accuracy"] == 1
    assert report["metrics"]["temporal_view_accuracy"] == 1
    assert report["metrics"]["orthogonal_semantics_accuracy"] == 1
    assert report["metrics"]["temporal_plan_accuracy"] == 1
    assert report["metrics"]["typed_structure_accuracy"] == 1
    assert report["axis_failures"] == {
        "operation": [],
        "temporal_view": [],
        "confusions": {},
    }
    assert all(case["actual"]["schema_version"] == 2 for case in report["cases"])
    assert all("legacy_projection" in case for case in report["cases"])
    assert set(report["orthogonal_by_partition"]) == {
        "adversarial",
        "dev",
        "heldout",
    }
    assert all(
        metrics["typed_structure_accuracy"] == 1
        for metrics in report["orthogonal_by_category"].values()
    )


def test_expected_axes_do_not_turn_past_action_grammar_into_prior_state() -> None:
    dataset = load_ablation_dataset(ablation.DEFAULT_DATASET)
    repairs = [
        query
        for query in dataset.queries
        if query.intent == "lookup"
        and query.as_of is None
        and query.time_from is None
        and query.time_to is None
    ]

    assert repairs
    for query in repairs:
        operation, temporal_views = ablation._expected_axes(query)
        assert operation == "lookup"
        assert temporal_views == {"unbounded"}


def test_relation_catalog_is_restricted_to_dataset_host_allowlist() -> None:
    dataset = load_ablation_dataset(ablation.DEFAULT_DATASET)

    definitions = ablation._load_relation_definitions(
        ablation.DEFAULT_CATALOG, dataset
    )

    assert {definition.name for definition in definitions} == set(
        dataset.relation_types
    )


def test_promotion_gate_fails_each_declared_regression() -> None:
    metric_names = (
        "operation_accuracy",
        "temporal_view_accuracy",
        "temporal_plan_accuracy",
        "subject_binding_accuracy",
        "entity_recall",
        "relation_recall",
        "relation_type_exact_accuracy",
        "relation_type_recall",
        "relation_type_precision",
    )
    baseline = {
        "execution": {"complete": True},
        "metrics": {"valid_case_count": 240, **dict.fromkeys(metric_names, 0.9)},
    }
    candidate = json.loads(json.dumps(baseline))
    reports = {"v1": baseline, "v2": candidate}

    assert ablation._promotion_gate(reports)["passed"] is True
    for metric in metric_names:
        candidate["metrics"][metric] = 0.8
        gate = ablation._promotion_gate(reports)
        assert gate["passed"] is False
        assert metric in gate["failures"]
        candidate["metrics"][metric] = 0.9


def test_promotion_gate_handles_unmeasured_metrics_without_crashing() -> None:
    metrics = {
        "valid_case_count": 0,
        "operation_accuracy": 0,
        "temporal_view_accuracy": 0,
        "temporal_plan_accuracy": 0,
        "subject_binding_accuracy": 0,
        "entity_recall": None,
        "relation_recall": None,
        "relation_type_exact_accuracy": 0,
        "relation_type_recall": None,
        "relation_type_precision": None,
    }
    report = {"execution": {"complete": False}, "metrics": metrics}

    gate = ablation._promotion_gate({"v1": report, "v2": report})

    assert gate["passed"] is False
    assert gate["failures"] == ["provider_complete"]


@pytest.mark.asyncio
async def test_pair_writes_both_reports_and_preserves_failed_promotion_gate(
    tmp_path: Path, monkeypatch: Any
) -> None:
    args = ablation._parser().parse_args(
        ["--live", "--output-root", str(tmp_path)]
    )
    monkeypatch.setattr(
        ablation,
        "_input_identity",
        lambda *_: {"source": "fixed"},
    )

    async def fake_arm(
        arm: str, args: Any, dataset: Any, definitions: Any
    ) -> dict[str, Any]:
        del args, dataset, definitions
        value = 0.9 if arm == "v1" else 0.8
        metrics = {
            "valid_case_count": 240,
            "operation_accuracy": value,
            "temporal_view_accuracy": value,
            "temporal_plan_accuracy": value,
            "subject_binding_accuracy": value,
            "entity_recall": value,
            "relation_recall": value,
            "relation_type_exact_accuracy": value,
            "relation_type_recall": value,
            "relation_type_precision": value,
        }
        return {
            "execution": {"complete": True, "stop_reason": ""},
            "planner": {"name": arm, "version": "1"},
            "metrics": metrics,
            "usage": {},
            "budget": {"calls": 0},
            "cache": {"hits": 0, "misses": 0},
            "cases": [],
        }

    monkeypatch.setattr(ablation, "_run_arm", fake_arm)

    code, run_dir = await ablation.run_pair(args)

    assert code == 1
    assert (run_dir / "plan.json").is_file()
    assert (run_dir / "v1.json").is_file()
    assert (run_dir / "v2.json").is_file()
    comparison = json.loads((run_dir / "comparison.json").read_bytes())
    assert comparison["completed"] is True
    assert comparison["promotion_gate"]["passed"] is False
    assert "operation_accuracy" in comparison["promotion_gate"]["failures"]
    assert (run_dir / "comparison.json.sha256").is_file()


@pytest.mark.asyncio
async def test_pair_stops_if_inputs_change_after_plan(
    tmp_path: Path, monkeypatch: Any
) -> None:
    args = ablation._parser().parse_args(
        ["--live", "--output-root", str(tmp_path)]
    )
    identities = iter(({"source": "planned"}, {"source": "changed"}))
    monkeypatch.setattr(ablation, "_input_identity", lambda *_: next(identities))

    code, run_dir = await ablation.run_pair(args)

    assert code == 1
    comparison = json.loads((run_dir / "comparison.json").read_bytes())
    assert comparison["completed"] is False
    assert comparison["stop_reason"] == "inputs_changed"
    assert comparison["reports"] == {}


@pytest.mark.asyncio
async def test_pair_sanitizes_unexpected_arm_failure(
    tmp_path: Path, monkeypatch: Any
) -> None:
    args = ablation._parser().parse_args(
        ["--live", "--output-root", str(tmp_path)]
    )
    monkeypatch.setattr(ablation, "_input_identity", lambda *_: {"source": "fixed"})

    async def fail_arm(*_: Any) -> dict[str, Any]:
        raise RuntimeError("must-not-appear secret-provider-payload")

    monkeypatch.setattr(ablation, "_run_arm", fail_arm)

    code, run_dir = await ablation.run_pair(args)

    assert code == 1
    raw = (run_dir / "comparison.json").read_text(encoding="utf-8")
    assert "must-not-appear" not in raw
    comparison = json.loads(raw)
    assert comparison["stop_reason"] == "v1_execution_error"
    assert comparison["failure_type"] == "RuntimeError"


def test_live_cache_only_run_does_not_require_api_key(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
    observed: dict[str, Any] = {}

    async def fake_pair(args: Any) -> tuple[int, Path]:
        observed["max_calls"] = args.max_calls_per_arm
        return 1, tmp_path

    monkeypatch.setattr(ablation, "run_pair", fake_pair)

    assert ablation.main(["--live", "--max-calls-per-arm", "0"]) == 1
    assert observed == {"max_calls": 0}
    assert "DOPPEL_API_KEY" not in __import__("os").environ
