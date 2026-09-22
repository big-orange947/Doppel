"""Dataset and evaluator contracts for natural-language path planning."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.build_relation_path_planner_v1 import build_dataset
from benchmarks.relation_path_planner_quality import (
    load_dataset,
    load_relation_catalog,
    run_relation_path_planner_quality,
)
from doppel_memory.query import PersonalMemoryQueryRequest
from doppel_memory.query_path import PersonalMemoryRelationPathDraftV3

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmarks/datasets/relation-path-planner-quality-zh-v1.json"
CATALOG = ROOT / "benchmarks/catalogs/personal-relations-v1.json"


class _GoldPlanner:
    name = "tests.gold-relation-path-planner-v3"
    version = "1"

    def __init__(self, dataset: object) -> None:
        self.by_query = {case.query: case for case in dataset.cases}  # type: ignore[attr-defined]

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryRelationPathDraftV3:
        case = self.by_query[request.query]
        return PersonalMemoryRelationPathDraftV3(
            operation="lookup",
            temporal_view="unbounded",
            search_text=request.query,
            entity_mentions=case.expected_entity_mentions,
            subject=request.default_subject,
            subject_id=request.default_subject_id,
            path_steps=case.expected_path_steps,
            path_confidence=0.99 if case.expected_path_steps else 0,
        )


def test_committed_path_planner_dataset_is_deterministic_and_independent() -> None:
    committed = json.loads(DATASET.read_text("utf-8"))
    assert committed == build_dataset()
    dataset = load_dataset(DATASET)

    assert dataset.frozen is False
    assert dataset.publication_ready is False
    assert len(dataset.cases) == 32
    assert {case.partition for case in dataset.cases} == {
        "dev",
        "heldout",
        "adversarial",
    }
    assert {case.category for case in dataset.cases} == {
        "one_hop",
        "two_hop",
        "no_path",
    }
    assert sum(case.category == "two_hop" for case in dataset.cases) == 12
    assert sum(case.category == "one_hop" for case in dataset.cases) == 12
    assert sum(case.category == "no_path" for case in dataset.cases) == 8
    assert any("inbound" in case.traits for case in dataset.cases)
    assert any("over_bound" in case.traits for case in dataset.cases)
    assert dataset.suite != "doppel-personal-relation-path-ablation-zh-v1"


@pytest.mark.asyncio
async def test_gold_planner_scores_every_axis_without_graph_execution() -> None:
    dataset = load_dataset(DATASET)
    definitions = load_relation_catalog(CATALOG)

    report = await run_relation_path_planner_quality(
        dataset, _GoldPlanner(dataset), definitions
    )

    assert report["metrics"] == {
        "case_count": 32,
        "valid_case_count": 32,
        "exact_path_accuracy": 1.0,
        "hop_count_accuracy": 1.0,
        "entity_mentions_accuracy": 1.0,
        "relation_type_accuracy": 1.0,
        "direction_accuracy": 1.0,
        "missed_path_count": 0,
        "false_path_count": 0,
        "no_path_accuracy": 1.0,
        "path_recall": 1.0,
        "forbidden_relation_type_hits": 0,
        "error_count": 0,
        "error_types": {},
    }
    assert report["valid_case_metrics"] == report["metrics"]
    assert report["execution"] == {
        "complete": True,
        "stopped_early": False,
        "stop_reason": "",
        "provider_error_count": 0,
        "planner_validation_error_count": 0,
        "not_run_case_count": 0,
    }
    assert set(report["by_partition"]) == {"dev", "heldout", "adversarial"}
    assert set(report["by_category"]) == {"one_hop", "two_hop", "no_path"}
    assert report["by_trait"]["inbound"]["exact_path_accuracy"] == 1
    assert report["by_trait"]["over_bound"]["no_path_accuracy"] == 1


@pytest.mark.asyncio
async def test_planner_errors_never_masquerade_as_correct_no_path() -> None:
    dataset = load_dataset(DATASET).model_copy(
        update={
            "cases": [
                next(case for case in load_dataset(DATASET).cases if case.category == "no_path")
            ]
        }
    )

    class FailingPlanner:
        name = "tests.failing-path-planner"
        version = "1"

        async def plan(self, request: PersonalMemoryQueryRequest):  # type: ignore[no-untyped-def]
            raise RuntimeError("synthetic failure")

    report = await run_relation_path_planner_quality(
        dataset, FailingPlanner(), load_relation_catalog(CATALOG)
    )

    assert report["metrics"]["valid_case_count"] == 0
    assert report["metrics"]["exact_path_accuracy"] == 0
    assert report["metrics"]["hop_count_accuracy"] == 0
    assert report["metrics"]["no_path_accuracy"] == 0
    assert report["metrics"]["error_types"] == {"RuntimeError": 1}
    assert report["valid_case_metrics"] is None


@pytest.mark.asyncio
async def test_partial_report_separates_valid_only_diagnostics_from_hard_score() -> None:
    source = load_dataset(DATASET)
    selected = source.model_copy(update={"cases": source.cases[:2]})

    class PartiallyFailingPlanner(_GoldPlanner):
        async def plan(
            self, request: PersonalMemoryQueryRequest
        ) -> PersonalMemoryRelationPathDraftV3:
            if request.query == selected.cases[1].query:
                raise RuntimeError("synthetic failure")
            return await super().plan(request)

    report = await run_relation_path_planner_quality(
        selected,
        PartiallyFailingPlanner(selected),
        load_relation_catalog(CATALOG),
    )

    assert report["metrics"]["case_count"] == 2
    assert report["metrics"]["valid_case_count"] == 1
    assert report["metrics"]["exact_path_accuracy"] == 0.5
    assert report["valid_case_metrics"]["case_count"] == 1
    assert report["valid_case_metrics"]["valid_case_count"] == 1
    assert report["valid_case_metrics"]["exact_path_accuracy"] == 1
