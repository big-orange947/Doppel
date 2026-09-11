"""Paired v1/v2 personal-query Planner evaluation; dry-run by default."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from benchmarks.personal_retrieval_ablation import (
    AblationDataset,
    AblationQuery,
    _git_commit_hash,
    _source_tree_sha256,
    load_ablation_dataset,
)
from benchmarks.relation_planner_quality import (
    CachedStructuredOutputModel,
    PlannerCallBudgetExceeded,
    StructuredOutputCallBudget,
    UsageLedger,
    run_relation_planner_quality,
)
from doppel_memory import (
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
    PersonalMemoryQueryDraft,
    PersonalMemoryQueryDraftV2,
    PersonalMemoryQueryOperation,
    PersonalMemoryQueryPlannerV2,
    PersonalMemoryQueryRequest,
    PersonalMemoryQueryTemporalView,
    ReferencePersonalMemoryQueryPlanner,
    ReferencePersonalMemoryQueryPlannerV2,
    RelationTypeDefinition,
    StructuredOutputProviderError,
)
from doppel_memory.query import QueryIntent, QueryOperation, QueryTemporalView

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = (
    ROOT / "benchmarks/datasets/personal-relation-ablation-zh-v2.json"
)
DEFAULT_CATALOG = ROOT / "benchmarks/catalogs/personal-relations-v2.json"
DEFAULT_OPERATION_DATASET = (
    ROOT / "benchmarks/datasets/query-plan-operations-zh-v1.json"
)
ARMS = ("v1", "v2")


class QueryPlanOperationCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    query: str
    now: datetime
    calendar_timezone: str = "UTC"
    operation: Literal["lookup", "list", "count"]
    temporal_view: Literal[
        "unbounded", "current", "prior", "planned", "as_of", "interval"
    ]
    as_of: datetime | None = None
    time_from: datetime | None = None
    time_to: datetime | None = None
    expected_memory_types: list[str] = Field(default_factory=list)
    partition: Literal["dev", "heldout", "adversarial"]


class QueryPlanOperationDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    suite: str
    suite_version: str
    language: str
    frozen: bool = False
    publication_ready: bool = False
    description: str = ""
    cases: list[QueryPlanOperationCase] = Field(min_length=18)


def _load_operation_dataset(path: Path) -> QueryPlanOperationDataset:
    return QueryPlanOperationDataset.model_validate_json(path.read_bytes())


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _operation_from_intent(intent: str) -> QueryOperation:
    if intent == "count":
        return PersonalMemoryQueryOperation.COUNT
    if intent == "list":
        return PersonalMemoryQueryOperation.LIST
    return PersonalMemoryQueryOperation.LOOKUP


def _temporal_view_from_shape(
    intent: str,
    *,
    as_of: Any = None,
    time_from: Any = None,
    time_to: Any = None,
) -> QueryTemporalView:
    if as_of is not None:
        return PersonalMemoryQueryTemporalView.AS_OF
    if time_from is not None or time_to is not None:
        return PersonalMemoryQueryTemporalView.INTERVAL
    return cast(
        QueryTemporalView,
        {
            "current": PersonalMemoryQueryTemporalView.CURRENT,
            "history": PersonalMemoryQueryTemporalView.PRIOR,
            "planned": PersonalMemoryQueryTemporalView.PLANNED,
            "as_of": PersonalMemoryQueryTemporalView.AS_OF,
        }.get(intent, PersonalMemoryQueryTemporalView.UNBOUNDED),
    )


def _expected_axes(
    query: AblationQuery,
) -> tuple[QueryOperation, set[QueryTemporalView]]:
    operation = cast(
        QueryOperation,
        query.operation or _operation_from_intent(query.intent),
    )
    primary = cast(
        QueryTemporalView,
        query.temporal_view
        or _temporal_view_from_shape(
            query.intent,
            as_of=query.as_of,
            time_from=query.time_from,
            time_to=query.time_to,
        ),
    )
    accepted: set[QueryTemporalView] = {primary}
    accepted.update(cast(QueryTemporalView, item) for item in query.accepted_temporal_views)
    if query.temporal_view is None and query.accept_interval_covering_as_of:
        accepted.add(cast(QueryTemporalView, PersonalMemoryQueryTemporalView.INTERVAL))
    if (
        query.temporal_view is None
        and query.as_of is None
        and query.time_from is None
        and query.time_to is None
    ):
        accepted.update(
            _temporal_view_from_shape(intent)
            for intent in query.accepted_intents
        )
    return operation, accepted


def _legacy_intent(draft: PersonalMemoryQueryDraftV2) -> QueryIntent:
    if draft.operation == PersonalMemoryQueryOperation.COUNT:
        return "count"
    if draft.operation == PersonalMemoryQueryOperation.LIST:
        return "list"
    return cast(
        QueryIntent,
        {
            PersonalMemoryQueryTemporalView.CURRENT: "current",
            PersonalMemoryQueryTemporalView.PRIOR: "history",
            PersonalMemoryQueryTemporalView.PLANNED: "planned",
            PersonalMemoryQueryTemporalView.AS_OF: "as_of",
            PersonalMemoryQueryTemporalView.INTERVAL: "history",
        }.get(draft.temporal_view, "lookup"),
    )


def _compatibility_draft(draft: PersonalMemoryQueryDraftV2) -> PersonalMemoryQueryDraft:
    payload = draft.model_dump(mode="python", exclude={"schema_version", "operation", "temporal_view"})
    return PersonalMemoryQueryDraft(intent=_legacy_intent(draft), **payload)


class _CapturingV2CompatibilityPlanner:
    """Feed existing structural scoring while retaining the authoritative V2 draft."""

    def __init__(self, planner: PersonalMemoryQueryPlannerV2) -> None:
        self._planner = planner
        self.name = planner.name
        self.version = planner.version
        self.drafts: dict[str, PersonalMemoryQueryDraftV2] = {}

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraft:
        draft = PersonalMemoryQueryDraftV2.model_validate(
            await self._planner.plan(request)
        )
        self.drafts[request.query] = draft
        return _compatibility_draft(draft)


def _case_axes(
    case: dict[str, Any], query: AblationQuery, *, v2_draft: PersonalMemoryQueryDraftV2 | None
) -> dict[str, Any]:
    expected_operation, accepted_views = _expected_axes(query)
    if case["status"] != "valid" or case.get("actual") is None:
        return {
            "expected_operation": expected_operation,
            "accepted_temporal_views": sorted(accepted_views),
            "actual_operation": None,
            "actual_temporal_view": None,
            "operation_ok": False,
            "temporal_view_ok": False,
            "orthogonal_semantics_ok": False,
        }
    if v2_draft is not None:
        actual_operation = v2_draft.operation
        actual_view = v2_draft.temporal_view
    else:
        actual = case["actual"]
        actual_operation = _operation_from_intent(str(actual["intent"]))
        actual_view = _temporal_view_from_shape(
            str(actual["intent"]),
            as_of=actual.get("as_of"),
            time_from=actual.get("time_from"),
            time_to=actual.get("time_to"),
        )
    operation_ok = actual_operation == expected_operation
    temporal_view_ok = actual_view in accepted_views
    return {
        "expected_operation": expected_operation,
        "accepted_temporal_views": sorted(accepted_views),
        "actual_operation": actual_operation,
        "actual_temporal_view": actual_view,
        "operation_ok": operation_ok,
        "temporal_view_ok": temporal_view_ok,
        "orthogonal_semantics_ok": operation_ok and temporal_view_ok,
    }


def _base_structure_without_intent(case: dict[str, Any]) -> bool:
    return bool(
        case["temporal_plan_ok"]
        and case["subject_binding_ok"]
        and case["matched_entity_count"] == case["expected_entity_count"]
        and case["unexpected_entity_count"] == 0
        and case["matched_relation_count"] == case["expected_relation_count"]
        and case["unexpected_relation_count"] == 0
        and case["hard_filter_ok"]
    )


def _orthogonal_group_metrics(
    cases: list[dict[str, Any]], group_key: str
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for group in sorted({str(case[group_key]) for case in cases}):
        selected = [case for case in cases if str(case[group_key]) == group]
        valid = [case for case in selected if case["status"] == "valid"]
        result[group] = {
            "case_count": len(selected),
            "valid_case_count": len(valid),
            "operation_accuracy": _ratio(
                sum(case["operation_ok"] for case in valid), len(selected)
            ),
            "temporal_view_accuracy": _ratio(
                sum(case["temporal_view_ok"] for case in valid), len(selected)
            ),
            "orthogonal_semantics_accuracy": _ratio(
                sum(case["orthogonal_semantics_ok"] for case in valid),
                len(selected),
            ),
            "exact_structure_accuracy": _ratio(
                sum(case["structure_ok"] for case in valid), len(selected)
            ),
            "typed_structure_accuracy": _ratio(
                sum(case["typed_structure_ok"] for case in valid), len(selected)
            ),
        }
    return result


def _augment_report(
    report: dict[str, Any],
    dataset: AblationDataset,
    *,
    arm: str,
    drafts: dict[str, PersonalMemoryQueryDraftV2] | None = None,
) -> dict[str, Any]:
    queries = {query.query_id: query for query in dataset.queries}
    for case in report["cases"]:
        query = queries[case["query_id"]]
        draft = drafts.get(query.query) if drafts is not None else None
        axes = _case_axes(case, query, v2_draft=draft)
        case.update(axes)
        if draft is not None:
            case["legacy_projection"] = case["actual"]
            case["actual"] = draft.model_dump(mode="json")
            case["structure_ok"] = bool(
                axes["orthogonal_semantics_ok"]
                and _base_structure_without_intent(case)
            )
            case["typed_structure_ok"] = bool(
                case["structure_ok"] and case["relation_type_ok"]
            )

    cases = report["cases"]
    valid = [case for case in cases if case["status"] == "valid"]
    report["runner"] = "doppel.query-plan-v2-ablation.v1"
    report["query_schema"] = arm
    report["scoring_version"] = "orthogonal-query-plan-1"
    report["metrics"].update(
        {
            "operation_accuracy": _ratio(
                sum(case["operation_ok"] for case in valid), len(cases)
            ),
            "temporal_view_accuracy": _ratio(
                sum(case["temporal_view_ok"] for case in valid), len(cases)
            ),
            "orthogonal_semantics_accuracy": _ratio(
                sum(case["orthogonal_semantics_ok"] for case in valid), len(cases)
            ),
            "structural_failure_count": sum(
                not case["structure_ok"] for case in valid
            ),
            "exact_structure_accuracy": _ratio(
                sum(case["structure_ok"] for case in valid), len(cases)
            ),
            "typed_structure_accuracy": _ratio(
                sum(case["typed_structure_ok"] for case in valid), len(cases)
            ),
        }
    )
    report["axis_failures"] = {
        "operation": [
            case["query_id"]
            for case in valid
            if not case["operation_ok"]
        ],
        "temporal_view": [
            case["query_id"]
            for case in valid
            if not case["temporal_view_ok"]
        ],
        "confusions": dict(
            sorted(
                Counter(
                    f"{case['accepted_temporal_views']}->{case['actual_temporal_view']}"
                    for case in valid
                    if not case["temporal_view_ok"]
                ).items()
            )
        ),
    }
    report["orthogonal_by_partition"] = _orthogonal_group_metrics(
        cases, "partition"
    )
    report["orthogonal_by_category"] = _orthogonal_group_metrics(
        cases, "category"
    )
    report["compatibility_projection_note"] = (
        "by_partition/by_category retain legacy-intent scoring for historical "
        "comparison; orthogonal_by_partition/orthogonal_by_category are authoritative "
        "for Query Plan v2 semantics."
    )
    return report


def _input_identity(
    dataset: Path, catalog: Path, operation_dataset: Path
) -> dict[str, str]:
    return {
        "commit": _git_commit_hash(),
        "source_sha256": _source_tree_sha256(),
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "catalog_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
        "operation_dataset_sha256": hashlib.sha256(
            operation_dataset.read_bytes()
        ).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    dataset = load_ablation_dataset(args.dataset)
    relation_query_count = sum(
        query.partition != "deferred_cross_subject" for query in dataset.queries
    )
    operation_query_count = len(_load_operation_dataset(args.operation_dataset).cases)
    return {
        "runner": "doppel.query-plan-v2-ablation.v1",
        "mode": "live" if args.live else "dry_run",
        "publication_ready": False,
        "arms": list(ARMS),
        "relation_query_count_per_arm": relation_query_count,
        "operation_query_count_per_arm": operation_query_count,
        "query_count_per_arm": relation_query_count + operation_query_count,
        "max_calls_per_arm": args.max_calls_per_arm,
        "max_total_provider_calls": args.max_calls_per_arm * len(ARMS),
        "cache_enabled": True,
        "provider_retries": 0,
        "settings": {
            "model": args.model,
            "base_url": args.base_url,
            "schema_mode": args.schema_mode,
            "max_completion_tokens": args.max_completion_tokens,
            "max_tokens_parameter": args.max_tokens_parameter,
            "thinking": args.thinking,
            "temperature": 0,
        },
        "input_identity": _input_identity(
            args.dataset, args.relation_catalog, args.operation_dataset
        ),
        "promotion_gate": [
            "provider execution complete in both arms",
            "v2 valid drafts are not fewer than v1",
            "operation, temporal-view, temporal-plan, subject, entity, relation, and relation-type metrics do not regress",
        ],
        "notes": [
            "The dataset remains unfrozen and cannot support a publication claim.",
            "Both arms receive identical questions, host ontology, model settings, and call ceilings.",
            "Raw provider caches are schema/prompt-addressed; v1 and v2 entries cannot collide.",
            "No retrieval or answer generation is measured in this stage.",
            "The independent operation suite covers lookup/list/count across all six temporal views.",
        ],
    }


def _provider_config(args: argparse.Namespace) -> OpenAICompatibleStructuredOutputConfig:
    return OpenAICompatibleStructuredOutputConfig(
        model=args.model,
        base_url=args.base_url,
        schema_mode=args.schema_mode,
        max_completion_tokens=args.max_completion_tokens,
        max_tokens_parameter=args.max_tokens_parameter,
        temperature=0,
        thinking=args.thinking,
    )


def _load_relation_definitions(
    path: Path, dataset: AblationDataset
) -> list[RelationTypeDefinition]:
    catalog = TypeAdapter(list[RelationTypeDefinition]).validate_json(
        path.read_bytes()
    )
    by_name = {definition.name: definition for definition in catalog}
    expected = set(dataset.relation_types)
    missing = sorted(expected.difference(by_name))
    if missing:
        raise ValueError(
            "relation catalog is missing dataset allowlist definitions: "
            + ", ".join(missing)
        )
    return [by_name[name] for name in sorted(expected)]


def _operation_group_metrics(
    cases: list[dict[str, Any]], key: str
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for group in sorted({str(case[key]) for case in cases}):
        selected = [case for case in cases if str(case[key]) == group]
        valid = [case for case in selected if case["status"] == "valid"]
        result[group] = {
            "case_count": len(selected),
            "valid_case_count": len(valid),
            "operation_accuracy": _ratio(
                sum(case["operation_ok"] for case in valid), len(selected)
            ),
            "temporal_view_accuracy": _ratio(
                sum(case["temporal_view_ok"] for case in valid), len(selected)
            ),
            "coordinate_accuracy": _ratio(
                sum(case["coordinates_ok"] for case in valid), len(selected)
            ),
            "exact_semantics_accuracy": _ratio(
                sum(case["exact_semantics_ok"] for case in valid), len(selected)
            ),
        }
    return result


async def _run_operation_suite(
    dataset: QueryPlanOperationDataset,
    planner: Any,
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    stop_reason = ""
    for gold in dataset.cases:
        if stop_reason:
            cases.append(
                {
                    "case_id": gold.case_id,
                    "query": gold.query,
                    "partition": gold.partition,
                    "expected_operation": gold.operation,
                    "expected_temporal_view": gold.temporal_view,
                    "actual_operation": None,
                    "actual_temporal_view": None,
                    "operation_ok": False,
                    "temporal_view_ok": False,
                    "coordinates_ok": False,
                    "count_memory_type_ok": False,
                    "exact_semantics_ok": False,
                    "status": "not_run",
                    "error": "PlannerNotRun",
                }
            )
            continue
        try:
            draft = await planner.plan(
                PersonalMemoryQueryRequest(
                    query=gold.query,
                    now=gold.now,
                    calendar_timezone=gold.calendar_timezone,
                    default_subject_id="operation-suite-owner",
                )
            )
            if isinstance(draft, PersonalMemoryQueryDraftV2):
                actual_operation = draft.operation
                actual_view = draft.temporal_view
            else:
                legacy = PersonalMemoryQueryDraft.model_validate(draft)
                actual_operation = _operation_from_intent(legacy.intent)
                actual_view = _temporal_view_from_shape(
                    legacy.intent,
                    as_of=legacy.as_of,
                    time_from=legacy.time_from,
                    time_to=legacy.time_to,
                )
                draft = legacy
            operation_ok = actual_operation == gold.operation
            temporal_view_ok = actual_view == gold.temporal_view
            coordinates_ok = (
                draft.as_of == gold.as_of
                and draft.time_from == gold.time_from
                and draft.time_to == gold.time_to
            )
            count_memory_type_ok = (
                gold.operation != "count"
                or set(gold.expected_memory_types).issubset(draft.memory_types)
            )
            cases.append(
                {
                    "case_id": gold.case_id,
                    "query": gold.query,
                    "partition": gold.partition,
                    "expected_operation": gold.operation,
                    "expected_temporal_view": gold.temporal_view,
                    "actual_operation": actual_operation,
                    "actual_temporal_view": actual_view,
                    "operation_ok": operation_ok,
                    "temporal_view_ok": temporal_view_ok,
                    "coordinates_ok": coordinates_ok,
                    "count_memory_type_ok": count_memory_type_ok,
                    "exact_semantics_ok": operation_ok
                    and temporal_view_ok
                    and coordinates_ok
                    and count_memory_type_ok,
                    "status": "valid",
                }
            )
        except Exception as exc:  # noqa: BLE001 - content-free diagnostics only
            if isinstance(exc, PlannerCallBudgetExceeded):
                stop_reason = "budget_exhausted"
            elif (
                isinstance(exc, StructuredOutputProviderError)
                and exc.code == "authentication_error"
            ):
                stop_reason = "authentication_error"
            cases.append(
                {
                    "case_id": gold.case_id,
                    "query": gold.query,
                    "partition": gold.partition,
                    "expected_operation": gold.operation,
                    "expected_temporal_view": gold.temporal_view,
                    "actual_operation": None,
                    "actual_temporal_view": None,
                    "operation_ok": False,
                    "temporal_view_ok": False,
                    "coordinates_ok": False,
                    "count_memory_type_ok": False,
                    "exact_semantics_ok": False,
                    "status": "error",
                    "error": type(exc).__name__,
                }
            )
    valid = [case for case in cases if case["status"] == "valid"]
    count_cases = [
        case for case in valid if case["expected_operation"] == "count"
    ]
    metrics = {
        "case_count": len(cases),
        "valid_case_count": len(valid),
        "operation_accuracy": _ratio(
            sum(case["operation_ok"] for case in valid), len(cases)
        ),
        "temporal_view_accuracy": _ratio(
            sum(case["temporal_view_ok"] for case in valid), len(cases)
        ),
        "coordinate_accuracy": _ratio(
            sum(case["coordinates_ok"] for case in valid), len(cases)
        ),
        "count_memory_type_accuracy": _ratio(
            sum(case["count_memory_type_ok"] for case in count_cases),
            sum(case.operation == "count" for case in dataset.cases),
        ),
        "exact_semantics_accuracy": _ratio(
            sum(case["exact_semantics_ok"] for case in valid), len(cases)
        ),
    }
    return {
        "dataset": {
            "name": dataset.suite,
            "version": dataset.suite_version,
            "case_count": len(cases),
            "frozen": dataset.frozen,
            "publication_ready": dataset.publication_ready,
        },
        "execution": {
            "complete": len(valid) == len(cases),
            "error_count": len(cases) - len(valid),
            "stop_reason": stop_reason,
        },
        "metrics": metrics,
        "by_operation": _operation_group_metrics(cases, "expected_operation"),
        "by_temporal_view": _operation_group_metrics(
            cases, "expected_temporal_view"
        ),
        "by_partition": _operation_group_metrics(cases, "partition"),
        "cases": cases,
    }


def _unavailable_operation_suite(dataset: QueryPlanOperationDataset) -> dict[str, Any]:
    return {
        "dataset": {"name": dataset.suite, "case_count": len(dataset.cases)},
        "execution": {"complete": False, "error_count": 0},
        "metrics": {},
        "cases": [],
    }


async def _run_arm(
    arm: str,
    args: argparse.Namespace,
    dataset: AblationDataset,
    operation_dataset: QueryPlanOperationDataset,
    definitions: list[RelationTypeDefinition],
) -> dict[str, Any]:
    usage = UsageLedger()
    provider = OpenAICompatibleStructuredOutputModel(
        _provider_config(args),
        api_key=os.environ.get("DOPPEL_API_KEY", ""),
        usage_observer=usage.observe,
    )
    budget = StructuredOutputCallBudget(provider, max_calls=args.max_calls_per_arm)
    cache = CachedStructuredOutputModel(budget, args.cache_dir)
    try:
        if arm == "v1":
            planner: Any = ReferencePersonalMemoryQueryPlanner(cache)
            report = await run_relation_planner_quality(
                dataset,
                planner,
                cache=cache,
                call_budget=budget,
                usage=usage,
                relation_type_definitions=definitions,
            )
            report = _augment_report(report, dataset, arm=arm)
            report["operation_suite"] = (
                await _run_operation_suite(operation_dataset, planner)
                if report["execution"]["complete"]
                else _unavailable_operation_suite(operation_dataset)
            )
        else:
            inner = ReferencePersonalMemoryQueryPlannerV2(cache)
            wrapper = _CapturingV2CompatibilityPlanner(inner)
            report = await run_relation_planner_quality(
                dataset,
                wrapper,
                cache=cache,
                call_budget=budget,
                usage=usage,
                relation_type_definitions=definitions,
            )
            report = _augment_report(
                report, dataset, arm=arm, drafts=wrapper.drafts
            )
            report["operation_suite"] = (
                await _run_operation_suite(operation_dataset, inner)
                if report["execution"]["complete"]
                else _unavailable_operation_suite(operation_dataset)
            )
        report["usage"] = usage.report()
        report["budget"] = {"max_calls": budget.max_calls, "calls": budget.calls}
        report["cache"].update(
            {
                "hits": cache.hits,
                "misses": cache.misses,
                "invalid_entries_ignored": cache.invalid_entries_ignored,
                "legacy_final_drafts_read": cache.legacy_final_drafts_read,
            }
        )
        return report
    finally:
        await provider.aclose()


def _promotion_gate(reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if set(reports) != set(ARMS):
        return {"passed": False, "failures": ["both arms are required"]}
    v1, v2 = reports["v1"], reports["v2"]
    checks = {
        "provider_complete": all(
            report["execution"]["complete"] for report in reports.values()
        ),
        "valid_case_count": (
            v2["metrics"]["valid_case_count"]
            >= v1["metrics"]["valid_case_count"]
        ),
        "operation_suite_complete": all(
            report.get("operation_suite", {})
            .get("execution", {})
            .get("complete", False)
            for report in reports.values()
        ),
    }
    for metric in (
        "operation_accuracy",
        "temporal_view_accuracy",
        "temporal_plan_accuracy",
        "subject_binding_accuracy",
        "entity_recall",
        "relation_recall",
        "relation_type_exact_accuracy",
        "relation_type_recall",
        "relation_type_precision",
    ):
        before = v1["metrics"][metric]
        after = v2["metrics"][metric]
        checks[metric] = (
            after >= before
            if isinstance(after, (int, float))
            and isinstance(before, (int, float))
            else after == before
        )
    for metric in (
        "operation_accuracy",
        "temporal_view_accuracy",
        "coordinate_accuracy",
        "count_memory_type_accuracy",
        "exact_semantics_accuracy",
    ):
        before = v1.get("operation_suite", {}).get("metrics", {}).get(metric)
        after = v2.get("operation_suite", {}).get("metrics", {}).get(metric)
        checks[f"operation_suite_{metric}"] = (
            after >= before
            if isinstance(after, (int, float))
            and isinstance(before, (int, float))
            else after == before and after is not None
        )
    failures = [name for name, passed in checks.items() if not passed]
    return {"passed": not failures, "checks": checks, "failures": failures}


def _comparison(reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if set(reports) != set(ARMS):
        return {"available": False}
    v1, v2 = reports["v1"], reports["v2"]
    metric_names = sorted(set(v1["metrics"]).intersection(v2["metrics"]))
    deltas = {
        name: round(v2["metrics"][name] - v1["metrics"][name], 4)
        for name in metric_names
        if isinstance(v1["metrics"][name], (int, float))
        and isinstance(v2["metrics"][name], (int, float))
    }
    v1_cases = {case["query_id"]: case for case in v1["cases"]}
    transitions = []
    for case in v2["cases"]:
        before = v1_cases[case["query_id"]]
        if before["orthogonal_semantics_ok"] != case["orthogonal_semantics_ok"]:
            transitions.append(
                {
                    "query_id": case["query_id"],
                    "v1_ok": before["orthogonal_semantics_ok"],
                    "v2_ok": case["orthogonal_semantics_ok"],
                    "expected_operation": case["expected_operation"],
                    "accepted_temporal_views": case["accepted_temporal_views"],
                    "v1_actual_operation": before["actual_operation"],
                    "v1_actual_temporal_view": before["actual_temporal_view"],
                    "v2_actual_operation": case["actual_operation"],
                    "v2_actual_temporal_view": case["actual_temporal_view"],
                }
            )
    return {
        "available": True,
        "metric_deltas_v2_minus_v1": deltas,
        "operation_suite_metric_deltas_v2_minus_v1": {
            name: round(
                v2["operation_suite"]["metrics"][name]
                - v1["operation_suite"]["metrics"][name],
                4,
            )
            for name in sorted(
                set(v1["operation_suite"]["metrics"]).intersection(
                    v2["operation_suite"]["metrics"]
                )
            )
            if isinstance(v1["operation_suite"]["metrics"][name], (int, float))
            and isinstance(v2["operation_suite"]["metrics"][name], (int, float))
        },
        "orthogonal_semantic_transitions": transitions,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(rendered, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n", encoding="utf-8", newline="\n"
    )


async def run_pair(args: argparse.Namespace) -> tuple[int, Path]:
    dataset = load_ablation_dataset(args.dataset)
    operation_dataset = _load_operation_dataset(args.operation_dataset)
    definitions = _load_relation_definitions(args.relation_catalog, dataset)
    plan = build_plan(args)
    run_dir = args.output_root / (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
    )
    run_dir.mkdir(parents=True)
    _write_json(run_dir / "plan.json", plan)
    reports: dict[str, dict[str, Any]] = {}
    stop_reason = ""
    failure_type = ""
    for arm in ARMS:
        if _input_identity(
            args.dataset, args.relation_catalog, args.operation_dataset
        ) != plan["input_identity"]:
            stop_reason = "inputs_changed"
            break
        print(f"Running {arm} Planner arm", flush=True)
        try:
            report = await _run_arm(
                arm, args, dataset, operation_dataset, definitions
            )
        except Exception as exc:  # noqa: BLE001 - sanitize provider failures
            stop_reason = f"{arm}_execution_error"
            failure_type = type(exc).__name__
            break
        reports[arm] = report
        _write_json(run_dir / f"{arm}.json", report)
        if report["execution"]["stop_reason"] == "authentication_error":
            stop_reason = "authentication_error"
            break
    gate = _promotion_gate(reports)
    summary = {
        "runner": plan["runner"],
        "completed": len(reports) == len(ARMS),
        "stop_reason": stop_reason,
        "failure_type": failure_type,
        "reports": {
            arm: {
                "path": f"{arm}.json",
                "sha256": hashlib.sha256(
                    (run_dir / f"{arm}.json").read_bytes()
                ).hexdigest(),
                "planner": report["planner"],
                "metrics": report["metrics"],
                "usage": report["usage"],
                "budget": report["budget"],
                "cache": report["cache"],
            }
            for arm, report in reports.items()
        },
        "promotion_gate": gate,
        "comparison": _comparison(reports),
    }
    _write_json(run_dir / "comparison.json", summary)
    print(f"Reports: {run_dir.resolve()}", flush=True)
    return (0 if gate["passed"] else 1), run_dir


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--relation-catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument(
        "--operation-dataset", type=Path, default=DEFAULT_OPERATION_DATASET
    )
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "data/doppel/query-plan-v2"
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=ROOT / "data/doppel/planner-cache"
    )
    parser.add_argument("--max-calls-per-arm", type=int, default=312)
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--base-url", default="https://api.deepseek.com")
    parser.add_argument(
        "--schema-mode", choices=("json_schema", "json_object"), default="json_object"
    )
    parser.add_argument("--max-completion-tokens", type=int, default=768)
    parser.add_argument(
        "--max-tokens-parameter",
        choices=("max_completion_tokens", "max_tokens"),
        default="max_tokens",
    )
    parser.add_argument("--thinking", choices=("enabled", "disabled"), default="disabled")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.max_calls_per_arm < 0:
        raise ValueError("--max-calls-per-arm must be non-negative")
    if not args.live:
        print(json.dumps(build_plan(args), ensure_ascii=False, indent=2))
        return 0
    previous_key = os.environ.get("DOPPEL_API_KEY")
    try:
        if not (previous_key or "").strip() and args.max_calls_per_arm > 0:
            if not sys.stdin.isatty():
                raise RuntimeError("DOPPEL_API_KEY is required for a live run")
            key = getpass.getpass("DeepSeek API key (hidden, process only): ").strip()
            if not key:
                raise RuntimeError("API key was empty; no calls made")
            os.environ["DOPPEL_API_KEY"] = key
        return asyncio.run(run_pair(args))[0]
    finally:
        if previous_key is None:
            os.environ.pop("DOPPEL_API_KEY", None)
        else:
            os.environ["DOPPEL_API_KEY"] = previous_key


if __name__ == "__main__":
    raise SystemExit(main())
