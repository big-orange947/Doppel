"""Offline quality evaluation for the experimental relation-path Planner v3."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doppel_memory import StructuredOutputProviderError
from doppel_memory.query import PersonalMemoryQueryRequest
from doppel_memory.query_path import PersonalMemoryRelationPathPlannerV3
from doppel_memory.relation import RelationPathStep, RelationTypeDefinition


class RelationPathPlannerCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    partition: Literal["dev", "heldout", "adversarial"]
    category: Literal["one_hop", "two_hop", "no_path"]
    query: str
    expected_entity_mentions: list[str] = Field(default_factory=list)
    expected_path_steps: list[RelationPathStep] = Field(
        default_factory=list, max_length=2
    )
    traits: list[str] = Field(default_factory=list)
    forbidden_relation_types: list[str] = Field(default_factory=list)


class RelationPathPlannerDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    suite: str
    suite_version: str
    fingerprint: str
    frozen: bool
    publication_ready: bool
    relation_catalog: str
    cases: list[RelationPathPlannerCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_cases(self) -> RelationPathPlannerDataset:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("relation path planner case IDs must be unique")
        queries = [case.query for case in self.cases]
        if len(queries) != len(set(queries)):
            raise ValueError("relation path planner queries must be unique")
        return self


def load_dataset(path: Path) -> RelationPathPlannerDataset:
    return RelationPathPlannerDataset.model_validate_json(path.read_text("utf-8"))


def load_relation_catalog(path: Path) -> list[RelationTypeDefinition]:
    raw = json.loads(path.read_text("utf-8"))
    definitions = [RelationTypeDefinition.model_validate(item) for item in raw]
    names = [definition.name for definition in definitions]
    if len(names) != len(set(names)):
        raise ValueError("relation catalog names must be unique")
    return definitions


async def run_relation_path_planner_quality(
    dataset: RelationPathPlannerDataset,
    planner: PersonalMemoryRelationPathPlannerV3,
    definitions: list[RelationTypeDefinition],
) -> dict[str, Any]:
    allowed = [definition.name for definition in definitions]
    rows: list[dict[str, Any]] = []
    stop_reason = ""
    for case in dataset.cases:
        error_code = ""
        http_status: int | None = None
        if stop_reason:
            actual_steps = []
            entity_mentions = []
            error = "PlannerNotRun"
            error_code = "previous_fatal_provider_error"
        else:
            try:
                draft = await planner.plan(
                    PersonalMemoryQueryRequest(
                        query=case.query,
                        now=datetime(2026, 9, 19, tzinfo=UTC),
                        calendar_timezone="+08:00",
                        default_subject="owner",
                        default_subject_id="planner-quality-owner",
                        available_relation_types=allowed,
                        relation_type_definitions=definitions,
                    )
                )
                actual_steps = draft.path_steps
                error = ""
                entity_mentions = draft.entity_mentions
            except Exception as exc:  # noqa: BLE001 - sanitized evaluator outcome
                actual_steps = []
                entity_mentions = []
                error = type(exc).__name__
                if isinstance(exc, StructuredOutputProviderError):
                    error_code = exc.code
                    http_status = exc.status_code
                    stop_reason = exc.code
                elif error == "PlannerCallBudgetExceeded":
                    error_code = "budget_exhausted"
                    stop_reason = error_code
        expected_steps = case.expected_path_steps
        expected_shape = [step.model_dump(mode="json") for step in expected_steps]
        actual_shape = [step.model_dump(mode="json") for step in actual_steps]
        selected = {
            relation_type
            for step in actual_steps
            for relation_type in step.relation_types
        }
        forbidden = sorted(selected.intersection(case.forbidden_relation_types))
        valid = not error
        relation_type_matches = sum(
            actual.relation_types == expected.relation_types
            for actual, expected in zip(actual_steps, expected_steps, strict=False)
        )
        direction_matches = sum(
            actual.direction == expected.direction
            for actual, expected in zip(actual_steps, expected_steps, strict=False)
        )
        rows.append(
            {
                "case_id": case.case_id,
                "partition": case.partition,
                "category": case.category,
                "traits": case.traits,
                "expected_path_steps": expected_shape,
                "actual_path_steps": actual_shape,
                "path_selected": bool(actual_steps),
                "path_expected": bool(expected_steps),
                "expected_hop_count": len(expected_steps),
                "relation_type_matches": relation_type_matches,
                "direction_matches": direction_matches,
                "hop_count_ok": valid and len(actual_steps) == len(expected_steps),
                "path_exact": valid and actual_shape == expected_shape,
                "entity_mentions_exact": valid
                and set(entity_mentions) == set(case.expected_entity_mentions),
                "forbidden_relation_types": forbidden,
                "error": error,
                "error_code": error_code,
                "http_status": http_status,
            }
        )

    summary = _summarize(rows)
    by_partition = {
        key: _summarize(items)
        for key, items in _group_rows(rows, "partition").items()
    }
    by_category = {
        key: _summarize(items)
        for key, items in _group_rows(rows, "category").items()
    }
    trait_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for trait in row["traits"]:
            trait_rows[trait].append(row)
    by_trait = {key: _summarize(items) for key, items in sorted(trait_rows.items())}
    provider_errors = sum(
        row["error"] == "StructuredOutputProviderError" for row in rows
    )
    validation_errors = sum(row["error"] == "ValidationError" for row in rows)
    not_run = sum(row["error"] == "PlannerNotRun" for row in rows)
    return {
        "runner": "doppel.relation-path-planner-quality.v1",
        "dataset": {
            "suite": dataset.suite,
            "version": dataset.suite_version,
            "fingerprint": dataset.fingerprint,
            "cases": len(dataset.cases),
            "frozen": dataset.frozen,
            "publication_ready": dataset.publication_ready,
        },
        "planner": {"name": planner.name, "version": planner.version},
        "execution": {
            "complete": not stop_reason and not summary["error_count"],
            "stopped_early": bool(stop_reason),
            "stop_reason": stop_reason,
            "provider_error_count": provider_errors,
            "planner_validation_error_count": validation_errors,
            "not_run_case_count": not_run,
        },
        "metrics": summary,
        "by_partition": by_partition,
        "by_category": by_category,
        "by_trait": by_trait,
        "cases": rows,
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    expected_path = sum(row["path_expected"] for row in rows)
    expected_empty = count - expected_path
    expected_hops = sum(row["expected_hop_count"] for row in rows)
    return {
        "case_count": count,
        "valid_case_count": sum(not row["error"] for row in rows),
        "exact_path_accuracy": round(
            sum(row["path_exact"] for row in rows) / count, 6
        ),
        "hop_count_accuracy": round(
            sum(row["hop_count_ok"] for row in rows) / count, 6
        ),
        "entity_mentions_accuracy": round(
            sum(row["entity_mentions_exact"] for row in rows) / count, 6
        ),
        "relation_type_accuracy": round(
            sum(row["relation_type_matches"] for row in rows) / expected_hops, 6
        )
        if expected_hops
        else 1.0,
        "direction_accuracy": round(
            sum(row["direction_matches"] for row in rows) / expected_hops, 6
        )
        if expected_hops
        else 1.0,
        "missed_path_count": sum(
            row["path_expected"] and not row["path_selected"] for row in rows
        ),
        "false_path_count": sum(
            not row["path_expected"] and row["path_selected"] for row in rows
        ),
        "no_path_accuracy": round(
            (
                sum(
                    not row["error"] and not row["path_selected"]
                    for row in rows
                    if not row["path_expected"]
                )
                / expected_empty
            )
            if expected_empty
            else 1.0,
            6,
        ),
        "path_recall": round(
            (
                sum(
                    not row["error"] and row["path_selected"]
                    for row in rows
                    if row["path_expected"]
                )
                / expected_path
            )
            if expected_path
            else 1.0,
            6,
        ),
        "forbidden_relation_type_hits": sum(
            len(row["forbidden_relation_types"]) for row in rows
        ),
        "error_count": sum(bool(row["error"]) for row in rows),
        "error_types": dict(sorted(Counter(row["error"] for row in rows if row["error"]).items())),
    }


def _group_rows(
    rows: list[dict[str, Any]], field: str
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[field])].append(row)
    return dict(sorted(grouped.items()))
