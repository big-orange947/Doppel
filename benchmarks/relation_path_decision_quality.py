"""Opened-corpus regression scoring for explicit relation-path V4 decisions."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from benchmarks.relation_path_planner_quality import (
    RelationPathPlannerCase,
    RelationPathPlannerDataset,
    run_relation_path_planner_quality,
)
from doppel_memory.query import PersonalMemoryQueryRequest
from doppel_memory.query_path import (
    PathDecision,
    PathDecisionReason,
    PersonalMemoryRelationPathDraftV4,
    PersonalMemoryRelationPathPlannerV4,
)
from doppel_memory.relation import RelationTypeDefinition


def expected_decision(
    case: RelationPathPlannerCase,
) -> tuple[PathDecision, PathDecisionReason]:
    """Project the opened V1 gold into the additive V4 decision vocabulary."""

    if case.expected_path_steps:
        return "execute", "exact"
    traits = set(case.traits)
    if "over_bound" in traits:
        return "abstain", "over_bound"
    if "unsupported_relation" in traits:
        return "abstain", "unsupported"
    if "ambiguous_relation" in traits:
        return "abstain", "ambiguous"
    return "abstain", "nonrelation"


class _CapturingV4Planner:
    def __init__(self, planner: PersonalMemoryRelationPathPlannerV4) -> None:
        self._planner = planner
        self.name = planner.name
        self.version = planner.version
        self.drafts: dict[str, PersonalMemoryRelationPathDraftV4] = {}

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryRelationPathDraftV4:
        draft = await self._planner.plan(request)
        self.drafts[request.query] = draft
        return draft


async def run_relation_path_decision_quality(
    dataset: RelationPathPlannerDataset,
    planner: PersonalMemoryRelationPathPlannerV4,
    definitions: list[RelationTypeDefinition],
) -> dict[str, Any]:
    """Score V4 decisions and reuse the versioned V3 path-shape metrics."""

    capturing = _CapturingV4Planner(planner)
    report = await run_relation_path_planner_quality(dataset, capturing, definitions)
    cases_by_id = {case.case_id: case for case in dataset.cases}
    for row in report["cases"]:
        case = cases_by_id[row["case_id"]]
        expected_action, expected_reason = expected_decision(case)
        draft = capturing.drafts.get(case.query)
        actual_action = draft.path_decision if draft is not None else None
        actual_reason = draft.path_reason if draft is not None else None
        row.update(
            {
                "expected_path_decision": expected_action,
                "expected_path_reason": expected_reason,
                "actual_path_decision": actual_action,
                "actual_path_reason": actual_reason,
                "path_decision_exact": actual_action == expected_action,
                "path_reason_exact": actual_reason == expected_reason,
            }
        )

    report["runner"] = "doppel.relation-path-decision-quality.v1"
    report["corpus_status"] = {
        "role": "opened_regression",
        "eligible_as_unseen_evidence": False,
        "notes": (
            "The V1 heldout/adversarial partitions were opened by the V3 sealed run; "
            "V4 results on them are regression evidence only."
        ),
    }
    report["decision_metrics"] = _summarize(report["cases"])
    valid_rows = [row for row in report["cases"] if not row["error"]]
    report["decision_valid_case_metrics"] = (
        _summarize(valid_rows) if valid_rows else None
    )
    report["decision_by_partition"] = _group(report["cases"], "partition")
    report["decision_by_category"] = _group(report["cases"], "category")
    trait_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in report["cases"]:
        for trait in row["traits"]:
            trait_rows[trait].append(row)
    report["decision_by_trait"] = {
        trait: _summarize(rows) for trait, rows in sorted(trait_rows.items())
    }
    return report


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    execute_rows = [row for row in rows if row["expected_path_decision"] == "execute"]
    abstain_rows = [row for row in rows if row["expected_path_decision"] == "abstain"]
    over_bound_rows = [
        row for row in rows if row["expected_path_reason"] == "over_bound"
    ]

    def ratio(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 6) if denominator else 1.0

    return {
        "case_count": count,
        "decision_accuracy": ratio(
            sum(row["path_decision_exact"] for row in rows), count
        ),
        "reason_accuracy": ratio(sum(row["path_reason_exact"] for row in rows), count),
        "execute_decision_accuracy": ratio(
            sum(row["path_decision_exact"] for row in execute_rows),
            len(execute_rows),
        ),
        "abstain_decision_accuracy": ratio(
            sum(row["path_decision_exact"] for row in abstain_rows),
            len(abstain_rows),
        ),
        "over_bound_reason_accuracy": ratio(
            sum(row["path_reason_exact"] for row in over_bound_rows),
            len(over_bound_rows),
        ),
        "wrong_execute_count": sum(
            row["expected_path_decision"] == "abstain"
            and row["actual_path_decision"] == "execute"
            for row in rows
        ),
        "wrong_abstain_count": sum(
            row["expected_path_decision"] == "execute"
            and row["actual_path_decision"] == "abstain"
            for row in rows
        ),
        "invalid_decision_count": sum(
            row["actual_path_decision"] is None for row in rows
        ),
    }


def _group(
    rows: list[dict[str, Any]], field: str
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[field])].append(row)
    return {key: _summarize(items) for key, items in sorted(grouped.items())}
