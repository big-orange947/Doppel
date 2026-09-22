"""V4 decision scoring over the explicitly opened V1 regression corpus."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.relation_path_decision_quality import (
    expected_decision,
    run_relation_path_decision_quality,
)
from benchmarks.relation_path_planner_quality import (
    load_dataset,
    load_relation_catalog,
)
from doppel_memory.query import PersonalMemoryQueryRequest
from doppel_memory.query_path import PersonalMemoryRelationPathDraftV4

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmarks/datasets/relation-path-planner-quality-zh-v1.json"
CATALOG = ROOT / "benchmarks/catalogs/personal-relations-v1.json"


class _GoldDecisionPlanner:
    name = "tests.gold-relation-path-decision-v4"
    version = "1"

    def __init__(self, dataset: object) -> None:
        self.by_query = {case.query: case for case in dataset.cases}  # type: ignore[attr-defined]

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryRelationPathDraftV4:
        case = self.by_query[request.query]
        decision, reason = expected_decision(case)
        return PersonalMemoryRelationPathDraftV4(
            operation="lookup",
            temporal_view="unbounded",
            search_text=request.query,
            entity_mentions=case.expected_entity_mentions,
            subject=request.default_subject,
            subject_id=request.default_subject_id,
            path_decision=decision,
            path_reason=reason,
            path_steps=case.expected_path_steps,
            path_confidence=0.99 if case.expected_path_steps else 0,
        )


def test_opened_regression_has_each_v4_abstention_reason() -> None:
    dataset = load_dataset(DATASET)
    outcomes = [expected_decision(case) for case in dataset.cases]

    assert outcomes.count(("execute", "exact")) == 24
    assert outcomes.count(("abstain", "over_bound")) == 1
    assert outcomes.count(("abstain", "unsupported")) == 1
    assert outcomes.count(("abstain", "ambiguous")) == 2
    assert outcomes.count(("abstain", "nonrelation")) == 4


@pytest.mark.asyncio
async def test_gold_v4_planner_scores_paths_decisions_and_reasons() -> None:
    dataset = load_dataset(DATASET)
    report = await run_relation_path_decision_quality(
        dataset,
        _GoldDecisionPlanner(dataset),
        load_relation_catalog(CATALOG),
    )

    assert report["metrics"]["exact_path_accuracy"] == 1
    assert report["decision_metrics"] == {
        "case_count": 32,
        "decision_accuracy": 1.0,
        "reason_accuracy": 1.0,
        "execute_decision_accuracy": 1.0,
        "abstain_decision_accuracy": 1.0,
        "over_bound_reason_accuracy": 1.0,
        "wrong_execute_count": 0,
        "wrong_abstain_count": 0,
        "invalid_decision_count": 0,
    }
    assert report["decision_valid_case_metrics"] == report["decision_metrics"]
    assert report["decision_by_trait"]["over_bound"][
        "over_bound_reason_accuracy"
    ] == 1
    assert report["corpus_status"]["eligible_as_unseen_evidence"] is False
    assert report["corpus_status"]["role"] == "opened_regression"
