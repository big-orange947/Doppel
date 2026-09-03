"""Evaluate natural-language planning for relation-aware personal retrieval."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import re
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, get_args

from pydantic import TypeAdapter, ValidationError
from pydantic_core.core_schema import ErrorType

from benchmarks.personal_retrieval_ablation import (
    AblationDataset,
    AblationQuery,
    _git_commit_hash,
    _git_tracked_dirty_paths,
    _source_tree_sha256,
    load_ablation_dataset,
)
from benchmarks.planner_semantic_review import (
    PlannerSemanticReview,
    review_planner_report,
)
from doppel_memory import (
    Actor,
    DeterministicPersonalMemoryQueryPlanner,
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
    PersonalMemoryQueryDraft,
    PersonalMemoryQueryRequest,
    ReferencePersonalMemoryQueryPlanner,
    RelationTypeDefinition,
    StructuredOutputProviderError,
    __version__,
)
from doppel_memory.query import QUERY_TEMPORAL_ERROR_CODES

DEFAULT_DATASET = (
    Path(__file__).parent / "datasets" / "personal-relation-ablation-zh-v1.json"
)
CACHE_FORMAT_VERSION = 1


def _safe_validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    """Never serialize model values, arbitrary extra-key names, messages or ctx."""
    return _safe_diagnostic_rows(
        [
            {"location": item["loc"], "type": item["type"]}
            for item in exc.errors(
                include_input=False, include_context=False, include_url=False
            )
        ]
    )


def _safe_diagnostic_rows(rows: Any) -> list[dict[str, Any]]:
    fields = set(PersonalMemoryQueryDraft.model_fields)
    error_types = set(get_args(ErrorType)) | QUERY_TEMPORAL_ERROR_CODES
    if not isinstance(rows, list):
        return []
    return [
        {
            "location": [
                part
                if isinstance(part, int) or isinstance(part, str) and part in fields
                else "<unknown-field>"
                for part in item["location"]
            ],
            "type": item["type"]
            if item["type"] in error_types
            else "custom_validation_error",
        }
        for item in rows
        if isinstance(item, dict)
        and isinstance(item.get("location"), (list, tuple))
        and isinstance(item.get("type"), str)
    ]


class ReplayedPlannerFailure(RuntimeError):
    """An original failure, not a newly attempted provider call."""

    def __init__(self, case: dict[str, Any]) -> None:
        super().__init__("source report contains no valid draft")
        self.source_error = (
            str(case.get("error"))
            if case.get("error")
            in {
                "ValidationError",
                "StructuredOutputProviderError",
                "PlannerCallBudgetExceeded",
                "PlannerNotRun",
            }
            else "SourceReportError"
        )
        self.source_code = (
            str(case.get("error_code"))
            if case.get("error_code")
            in {
                "authentication_error",
                "rate_limited",
                "http_error",
                "validation_error",
                "budget_exhausted",
                "truncated",
            }
            else ""
        )
        self.validation_errors = _safe_diagnostic_rows(case.get("validation_errors"))
        self.source_not_run = case.get("status") == "not_run"
        status = case.get("http_status")
        self.source_http_status = (
            status if type(status) is int and 100 <= status <= 599 else None
        )


class PlannerCallBudgetExceeded(RuntimeError):
    """A live planner call was blocked before reaching its provider."""


class PlannerCallBudget:
    """Sequential preflight call budget; cache hits do not consume it."""

    def __init__(self, planner: Any, *, max_calls: int) -> None:
        self._planner = planner
        self.max_calls = max_calls
        self.calls = 0
        self.name = str(planner.name)
        self.version = str(planner.version)

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraft:
        if self.max_calls >= 0 and self.calls >= self.max_calls:
            raise PlannerCallBudgetExceeded(
                f"planner call budget exhausted before call {self.calls + 1}"
            )
        self.calls += 1
        return PersonalMemoryQueryDraft.model_validate(
            await self._planner.plan(request)
        )


class CachedPlanner:
    """Content-addressed successful planner drafts with atomic disk writes."""

    def __init__(self, planner: Any, cache_dir: Path | None) -> None:
        self._planner = planner
        self._cache_dir = cache_dir
        self.name = str(planner.name)
        self.version = str(planner.version)
        self.hits = 0
        self.misses = 0

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraft:
        bound = PersonalMemoryQueryRequest.model_validate(request)
        cache_path = self._cache_path(bound)
        if cache_path is not None and cache_path.is_file():
            try:
                draft = PersonalMemoryQueryDraft.model_validate_json(
                    cache_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                pass
            else:
                self.hits += 1
                return draft
        self.misses += 1
        draft = PersonalMemoryQueryDraft.model_validate(await self._planner.plan(bound))
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(
                prefix=f".{cache_path.name}.", suffix=".tmp", dir=cache_path.parent
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as target:
                    target.write(draft.model_dump_json())
                    target.write("\n")
                os.replace(temporary, cache_path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return draft

    def _cache_path(self, request: PersonalMemoryQueryRequest) -> Path | None:
        if self._cache_dir is None:
            return None
        payload = {
            "format_version": CACHE_FORMAT_VERSION,
            "planner": self.name,
            "planner_version": self.version,
            "request": request.to_planner_input(),
        }
        digest = _fingerprint(payload)
        return self._cache_dir / digest[:2] / f"{digest}.json"


class UsageLedger:
    """Content-free aggregate of provider-reported token accounting."""

    def __init__(self) -> None:
        self.calls_with_usage = 0
        self.tokens: defaultdict[str, int] = defaultdict(int)

    def observe(self, usage: Any) -> None:
        if not isinstance(usage, dict):
            usage = dict(usage)
        self.calls_with_usage += 1
        for name, value in usage.items():
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                self.tokens[str(name)] += value

    def report(self) -> dict[str, Any]:
        return {
            "calls_with_usage": self.calls_with_usage,
            **dict(sorted(self.tokens.items())),
        }


class ReplayPlanner:
    """Re-score successful drafts from a prior report without provider calls."""

    def __init__(
        self,
        report_path: Path,
        *,
        dataset: AblationDataset | None = None,
        relation_type_definitions: Sequence[RelationTypeDefinition] = (),
    ) -> None:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
        catalog = _catalog_metadata(relation_type_definitions)
        source_catalog = raw.get("relation_catalog") or _catalog_metadata(())
        if source_catalog.get("fingerprint") != catalog["fingerprint"]:
            raise ValueError("replay relation catalog fingerprint mismatch")
        if dataset is not None and (
            (raw.get("dataset") or {}).get("fingerprint") != dataset.fingerprint
        ):
            raise ValueError("replay dataset fingerprint mismatch")
        planner = dict(raw.get("planner") or {})
        self.name = str(planner.get("name") or "doppel.replay-planner")
        self.version = str(planner.get("version") or "unknown")
        self._cases: dict[str, dict[str, Any]] = {}
        for item in list(raw.get("cases") or []):
            query_text = str(item.get("query") or "")
            if query_text in self._cases:
                raise ValueError("replay report contains duplicate query texts")
            self._cases[query_text] = item

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraft:
        case = self._cases.get(request.query)
        if case is None:
            raise KeyError("prior report has no successful draft for this query")
        fingerprint = case.get("request_fingerprint")
        if fingerprint and fingerprint != _fingerprint(request.to_planner_input()):
            raise ValueError("replay request fingerprint mismatch")
        if case.get("error") or case.get("actual") is None:
            raise ReplayedPlannerFailure(case)
        return PersonalMemoryQueryDraft.model_validate(case["actual"])


async def run_relation_planner_quality(
    dataset: AblationDataset,
    planner: Any,
    *,
    cache: CachedPlanner | None = None,
    call_budget: PlannerCallBudget | None = None,
    usage: UsageLedger | None = None,
    relation_type_definitions: Sequence[RelationTypeDefinition] = (),
) -> dict[str, Any]:
    """Run one planner over relation gold without executing retrieval."""

    if not dataset.requirements.get("relation_benchmark", False):
        raise ValueError("relation planner quality requires a relation benchmark")
    # Validate host definitions before any provider calls, not as per-case errors.
    _query_request(dataset, dataset.queries[0], relation_type_definitions)
    runner = cache or planner
    cases: list[dict[str, Any]] = []
    stop_reason = ""
    stopped_at = ""
    for query in dataset.queries:
        if query.partition == "deferred_cross_subject":
            continue
        if stop_reason:
            case = _failed_case(
                dataset,
                query,
                error="PlannerNotRun",
                error_code="previous_fatal_error",
                status="not_run",
                error_origin="not_run",
                relation_type_definitions=relation_type_definitions,
            )
        else:
            case = await _evaluate_case(
                runner,
                dataset,
                query,
                relation_type_definitions=relation_type_definitions,
            )
            if (
                case["error_code"] == "authentication_error"
                and case.get("error_origin") != "source_report"
            ):
                stop_reason = "authentication_error"
                stopped_at = query.query_id
        cases.append(case)

    valid = [case for case in cases if case["status"] == "valid"]
    structural_failures = sum(not case["structure_ok"] for case in valid)
    relation_type_failures = sum(not case["relation_type_ok"] for case in valid)
    provider_errors = sum(case["status"] == "error" for case in cases)
    not_run = sum(case["status"] == "not_run" for case in cases)
    total_expected_entities = sum(case["expected_entity_count"] for case in valid)
    total_matched_entities = sum(case["matched_entity_count"] for case in valid)
    total_expected_relations = sum(case["expected_relation_count"] for case in valid)
    total_matched_relations = sum(case["matched_relation_count"] for case in valid)
    total_expected_relation_types = sum(
        case["expected_relation_type_count"] for case in valid
    )
    total_actual_relation_types = sum(
        case["actual_relation_type_count"] for case in valid
    )
    total_matched_relation_types = sum(
        case["matched_relation_type_count"] for case in valid
    )
    by_partition = _group_metrics(cases, "partition")
    by_category = _group_metrics(cases, "category")
    latencies = sorted(case["latency_ms"] for case in cases)
    return {
        "runner": "doppel.relation-planner-quality.v1",
        "scoring_version": "2",
        "output_diagnostics": _output_diagnostics(cases),
        "relation_catalog": _catalog_metadata(relation_type_definitions),
        "doppel_version": __version__,
        "generated_at": datetime.now().astimezone().isoformat(),
        "dataset": {
            "name": dataset.suite,
            "version": dataset.suite_version,
            "fingerprint": dataset.fingerprint,
            "query_count": len(cases),
            "frozen": dataset.frozen,
            "publication_ready": dataset.publication_ready,
            "relation_type_count": len(dataset.relation_types),
        },
        "planner": {
            "name": str(planner.name),
            "version": str(planner.version),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "execution": {
            "complete": not not_run and not provider_errors,
            "stopped_early": bool(stop_reason),
            "stop_reason": stop_reason,
            "stopped_at_query_id": stopped_at,
            "evaluated_case_count": len(cases) - not_run,
            "not_run_case_count": not_run,
            "quality_measurement": "available" if valid else "unavailable",
        },
        "metrics": {
            "case_count": len(cases),
            "valid_case_count": len(valid),
            "provider_error_count": provider_errors,
            "not_run_case_count": not_run,
            "structural_failure_count": structural_failures,
            "exact_structure_accuracy": _ratio(
                len(valid) - structural_failures, len(cases)
            ),
            "typed_structure_accuracy": _ratio(
                sum(case["typed_structure_ok"] for case in valid), len(cases)
            ),
            "intent_accuracy": _ratio(
                sum(case["intent_ok"] for case in valid), len(cases)
            ),
            "intent_semantics_accuracy": _ratio(
                sum(case["intent_semantics_ok"] for case in valid), len(cases)
            ),
            "as_of_presence_accuracy": _ratio(
                sum(case["as_of_presence_ok"] for case in valid), len(cases)
            ),
            "as_of_date_accuracy": _ratio(
                sum(case["as_of_date_ok"] for case in valid), len(cases)
            ),
            "temporal_plan_accuracy": _ratio(
                sum(case["temporal_plan_ok"] for case in valid), len(cases)
            ),
            "subject_binding_accuracy": _ratio(
                sum(case["subject_binding_ok"] for case in valid), len(cases)
            ),
            "entity_recall": _ratio(total_matched_entities, total_expected_entities),
            "relation_recall": _ratio(
                total_matched_relations, total_expected_relations
            ),
            "relation_type_exact_accuracy": _ratio(
                len(valid) - relation_type_failures, len(cases)
            ),
            "relation_type_recall": _ratio(
                total_matched_relation_types, total_expected_relation_types
            ),
            "relation_type_precision": _ratio(
                total_matched_relation_types, total_actual_relation_types
            ),
            "relation_type_failure_count": relation_type_failures,
            "unexpected_relation_type_count": sum(
                case["unexpected_relation_type_count"] for case in valid
            ),
            "relation_type_ontology_violation_count": sum(
                case["relation_type_ontology_violation_count"] for case in valid
            ),
            "unexpected_entity_count": sum(
                case["unexpected_entity_count"] for case in valid
            ),
            "unexpected_relation_count": sum(
                case["unexpected_relation_count"] for case in valid
            ),
            "unexpected_hard_filter_count": sum(
                case["unexpected_hard_filter_count"] for case in valid
            ),
            "latency_ms": {
                "p50": _percentile(latencies, 0.50),
                "p95": _percentile(latencies, 0.95),
                "max": round(max(latencies, default=0.0), 3),
            },
        },
        "by_partition": by_partition,
        "by_category": by_category,
        "usage": usage.report() if usage is not None else {},
        "budget": {
            "max_calls": call_budget.max_calls if call_budget is not None else None,
            "calls": call_budget.calls if call_budget is not None else 0,
        },
        "cache": {
            "enabled": cache is not None and cache._cache_dir is not None,
            "hits": cache.hits if cache is not None else 0,
            "misses": cache.misses if cache is not None else 0,
        },
        "cases": cases,
    }


def _output_diagnostics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    lengths = sorted(
        len(str(case["actual"].get("explanation", "")))
        for case in cases
        if case["status"] == "valid"
    )
    return {
        "truncated_count": sum(case["error_code"] == "truncated" for case in cases),
        "invalid_draft_count": sum(
            case["error"] == "ValidationError" for case in cases
        ),
        "validation_code_counts": dict(
            sorted(
                Counter(
                    row["type"]
                    for case in cases
                    for row in _safe_diagnostic_rows(case.get("validation_errors"))
                ).items()
            )
        ),
        "explanation_chars": {
            "valid_case_count": len(lengths),
            "over_80_count": sum(length > 80 for length in lengths),
            "p50": _percentile(lengths, 0.50) if lengths else None,
            "p95": _percentile(lengths, 0.95) if lengths else None,
            "max": max(lengths) if lengths else None,
        },
    }


def _query_request(
    dataset: AblationDataset,
    query: AblationQuery,
    relation_type_definitions: Sequence[RelationTypeDefinition] = (),
) -> PersonalMemoryQueryRequest:
    scope = dataset.scopes[query.scopes[0]].to_scope()
    return PersonalMemoryQueryRequest(
        query=query.query,
        now=query.now,
        default_subject=Actor.OWNER,
        default_subject_id=scope.user_id,
        available_relation_types=dataset.relation_types,
        relation_type_definitions=list(relation_type_definitions),
    )


def _failed_case(
    dataset: AblationDataset,
    query: AblationQuery,
    *,
    error: str,
    error_code: str,
    status: str = "error",
    error_origin: str = "current_run",
    latency_ms: float = 0.0,
    http_status: int | None = None,
    validation_errors: list[dict[str, Any]] | None = None,
    relation_type_definitions: Sequence[RelationTypeDefinition] = (),
) -> dict[str, Any]:
    return {
        "query_id": query.query_id,
        "partition": query.partition,
        "category": query.category,
        "query": query.query,
        "request_fingerprint": _fingerprint(
            _query_request(dataset, query, relation_type_definitions).to_planner_input()
        ),
        "status": status,
        "error": error,
        "error_code": error_code,
        "error_origin": error_origin,
        "http_status": http_status,
        "validation_errors": validation_errors or [],
        "validation_diagnostics_available": bool(validation_errors),
        "latency_ms": latency_ms,
        "structure_ok": False,
        "intent_ok": False,
        "intent_semantics_ok": False,
        "as_of_presence_ok": False,
        "as_of_date_ok": False,
        "temporal_plan_ok": False,
        "subject_binding_ok": False,
        "expected_entity_count": len(query.entity_mentions),
        "matched_entity_count": 0,
        "unexpected_entity_count": 0,
        "expected_relation_count": len(query.relation_hints),
        "matched_relation_count": 0,
        "unexpected_relation_count": 0,
        "expected_relation_type_count": len(
            dataset.relation_type_labels.get(query.query_id, [])
        ),
        "actual_relation_type_count": 0,
        "matched_relation_type_count": 0,
        "unexpected_relation_type_count": 0,
        "relation_type_ontology_violation_count": 0,
        "relation_type_ok": False,
        "typed_structure_ok": False,
        "unexpected_hard_filter_count": 0,
        "hard_filter_ok": False,
        "actual": None,
    }


async def _evaluate_case(
    planner: Any,
    dataset: AblationDataset,
    query: AblationQuery,
    *,
    relation_type_definitions: Sequence[RelationTypeDefinition] = (),
) -> dict[str, Any]:
    request = _query_request(dataset, query, relation_type_definitions)
    started = perf_counter()
    try:
        draft = PersonalMemoryQueryDraft.model_validate(await planner.plan(request))
    except Exception as exc:  # noqa: BLE001 - report sanitized provider failure only
        is_provider = isinstance(exc, StructuredOutputProviderError)
        is_validation = isinstance(exc, ValidationError)
        is_budget = isinstance(exc, PlannerCallBudgetExceeded)
        is_replay = isinstance(exc, ReplayedPlannerFailure)
        code = (
            exc.code
            if is_provider
            else (
                "validation_error"
                if is_validation
                else "budget_exhausted"
                if is_budget
                else ""
            )
        )
        return _failed_case(
            dataset,
            query,
            error=exc.source_error if is_replay else type(exc).__name__,
            error_code=exc.source_code if is_replay else code,
            relation_type_definitions=relation_type_definitions,
            status="not_run"
            if is_budget or is_replay and exc.source_not_run
            else "error",
            error_origin="source_report" if is_replay else "current_run",
            latency_ms=round((perf_counter() - started) * 1_000, 3),
            http_status=exc.status_code
            if is_provider
            else exc.source_http_status
            if is_replay
            else None,
            validation_errors=(
                _safe_validation_errors(exc)
                if is_validation
                else exc.validation_errors
                if is_replay
                else []
            ),
        )

    expected_as_of = query.as_of
    actual_as_of = draft.as_of
    intent_ok = draft.intent == query.intent
    accepted_intents = set(query.accepted_intents or [query.intent])
    intent_semantics_ok = draft.intent in accepted_intents
    as_of_presence_ok = (expected_as_of is None) == (actual_as_of is None)
    as_of_date_ok = as_of_presence_ok and (
        expected_as_of is None
        or (actual_as_of is not None and actual_as_of.date() == expected_as_of.date())
    )
    interval_covers_as_of = bool(
        query.accept_interval_covering_as_of
        and expected_as_of is not None
        and draft.time_from is not None
        and draft.time_to is not None
        and draft.time_from <= expected_as_of <= draft.time_to
    )
    temporal_plan_ok = as_of_date_ok or interval_covers_as_of
    subject_binding_ok = (
        draft.subject == request.default_subject
        and draft.subject_id == request.default_subject_id
    )
    matched_entities, unexpected_entities = _term_matches(
        query.entity_mentions, draft.entity_mentions
    )
    matched_relations, unexpected_relations = _relation_term_matches(
        query.relation_hints, draft.relation_hints
    )
    expected_relation_types = dataset.relation_type_labels.get(query.query_id, [])
    expected_relation_type_set = set(expected_relation_types)
    actual_relation_type_set = set(draft.relation_types)
    matched_relation_types = expected_relation_type_set.intersection(
        actual_relation_type_set
    )
    unexpected_relation_types = sorted(
        actual_relation_type_set.difference(expected_relation_type_set)
    )
    ontology_violations = sorted(
        actual_relation_type_set.difference(dataset.relation_types)
    )
    relation_type_ok = (
        actual_relation_type_set == expected_relation_type_set
        and not ontology_violations
    )
    entity_ok = (
        matched_entities == len(query.entity_mentions) and not unexpected_entities
    )
    relation_ok = (
        matched_relations == len(query.relation_hints) and not unexpected_relations
    )
    unexpected_hard_filters = [
        *(f"memory_type:{item}" for item in draft.memory_types),
        *(f"topic_key:{item}" for item in draft.topic_keys),
    ]
    hard_filter_ok = not unexpected_hard_filters
    structure_ok = (
        intent_semantics_ok
        and temporal_plan_ok
        and entity_ok
        and relation_ok
        and hard_filter_ok
        and subject_binding_ok
    )
    typed_structure_ok = structure_ok and relation_type_ok
    return {
        "query_id": query.query_id,
        "partition": query.partition,
        "category": query.category,
        "query": query.query,
        "request_fingerprint": _fingerprint(request.to_planner_input()),
        "status": "valid",
        "error": "",
        "error_code": "",
        "error_origin": "",
        "latency_ms": round((perf_counter() - started) * 1_000, 3),
        "structure_ok": structure_ok,
        "intent_ok": intent_ok,
        "intent_semantics_ok": intent_semantics_ok,
        "as_of_presence_ok": as_of_presence_ok,
        "as_of_date_ok": as_of_date_ok,
        "temporal_plan_ok": temporal_plan_ok,
        "subject_binding_ok": subject_binding_ok,
        "interval_covers_as_of": interval_covers_as_of,
        "expected_entity_count": len(query.entity_mentions),
        "matched_entity_count": matched_entities,
        "unexpected_entity_count": len(unexpected_entities),
        "expected_relation_count": len(query.relation_hints),
        "matched_relation_count": matched_relations,
        "unexpected_relation_count": len(unexpected_relations),
        "expected_relation_type_count": len(expected_relation_type_set),
        "actual_relation_type_count": len(actual_relation_type_set),
        "matched_relation_type_count": len(matched_relation_types),
        "unexpected_relation_type_count": len(unexpected_relation_types),
        "relation_type_ontology_violation_count": len(ontology_violations),
        "expected_relation_types": sorted(expected_relation_type_set),
        "unexpected_relation_types": unexpected_relation_types,
        "relation_type_ontology_violations": ontology_violations,
        "relation_type_ok": relation_type_ok,
        "typed_structure_ok": typed_structure_ok,
        "unexpected_hard_filter_count": len(unexpected_hard_filters),
        "unexpected_hard_filters": unexpected_hard_filters,
        "hard_filter_ok": hard_filter_ok,
        "unexpected_entities": unexpected_entities,
        "unexpected_relations": unexpected_relations,
        "actual": draft.model_dump(mode="json"),
    }


def _term_matches(expected: list[str], actual: list[str]) -> tuple[int, list[str]]:
    expected_terms = [_normalize_term(item) for item in expected]
    actual_terms = [_normalize_term(item) for item in actual]
    matched_expected: set[int] = set()
    matched_actual: set[int] = set()
    for expected_index, expected_term in enumerate(expected_terms):
        for actual_index, actual_term in enumerate(actual_terms):
            if actual_index in matched_actual:
                continue
            if (
                expected_term
                and actual_term
                and (expected_term in actual_term or actual_term in expected_term)
            ):
                matched_expected.add(expected_index)
                matched_actual.add(actual_index)
                break
    unexpected = [
        actual[index] for index in range(len(actual)) if index not in matched_actual
    ]
    return len(matched_expected), unexpected


def _relation_term_matches(
    expected: list[str], actual: list[str]
) -> tuple[int, list[str]]:
    """Require the concise surface predicate promised by the planner contract."""

    expected_terms = [_normalize_term(item) for item in expected]
    actual_terms = [_normalize_term(item) for item in actual]
    matched_expected: set[int] = set()
    matched_actual: set[int] = set()
    for expected_index, expected_term in enumerate(expected_terms):
        for actual_index, actual_term in enumerate(actual_terms):
            if actual_index in matched_actual:
                continue
            if expected_term and actual_term == expected_term:
                matched_expected.add(expected_index)
                matched_actual.add(actual_index)
                break
    unexpected = [
        actual[index] for index in range(len(actual)) if index not in matched_actual
    ]
    return len(matched_expected), unexpected


def _normalize_term(value: str) -> str:
    normalized = str(value or "").casefold()
    return re.sub(r"[^\w\u3400-\u9fff]+", "", normalized, flags=re.UNICODE)


def _group_metrics(cases: list[dict[str, Any]], key: str) -> dict[str, Any]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        grouped[str(case[key])].append(case)
    return {
        name: {
            "case_count": len(items),
            "provider_error_count": sum(item["status"] == "error" for item in items),
            "not_run_case_count": sum(item["status"] == "not_run" for item in items),
            "structural_failure_count": sum(
                not item["structure_ok"] for item in items if item["status"] == "valid"
            ),
            "exact_structure_accuracy": _ratio(
                sum(item["structure_ok"] for item in items), len(items)
            ),
            "typed_structure_accuracy": _ratio(
                sum(item["typed_structure_ok"] for item in items), len(items)
            ),
            "relation_type_exact_accuracy": _ratio(
                sum(item["relation_type_ok"] for item in items), len(items)
            ),
        }
        for name, items in sorted(grouped.items())
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    index = max(0, min(len(values) - 1, int((len(values) - 1) * quantile)))
    return round(values[index], 3)


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _catalog_metadata(
    definitions: Sequence[RelationTypeDefinition],
) -> dict[str, Any]:
    payload = [item.model_dump(mode="json") for item in definitions]
    return {
        "mode": "definitions" if payload else "labels_only",
        "definition_count": len(payload),
        "fingerprint": _fingerprint(payload),
        "definitions": payload,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--planner", choices=("deterministic", "reference"), default="deterministic"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--relation-catalog",
        type=Path,
        help="optional host relation definitions (JSON array), never query answers",
    )
    parser.add_argument(
        "--semantic-review",
        type=Path,
        help="optional post-hoc diagnostic annotation file; never changes gold scores or drafts",
    )
    parser.add_argument(
        "--replay-report",
        type=Path,
        help="re-score successful drafts from a prior report with zero provider calls",
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=Path("data/doppel/planner-cache")
    )
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--max-calls", type=int, default=40)
    parser.add_argument(
        "--allow-unauthenticated",
        action="store_true",
        help="explicit opt-in for a local provider that does not require an API key",
    )
    parser.add_argument("--max-structural-failures", type=int, default=0)
    parser.add_argument(
        "--max-relation-type-failures",
        type=int,
        default=None,
        help=(
            "optional exact relation-type failure gate; omitted preserves the "
            "legacy structure-only exit policy"
        ),
    )
    parser.add_argument("--model", default=os.environ.get("DOPPEL_MODEL", ""))
    parser.add_argument(
        "--base-url",
        default=os.environ.get("DOPPEL_OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
    parser.add_argument(
        "--schema-mode",
        choices=("json_schema", "json_object"),
        default=os.environ.get("DOPPEL_SCHEMA_MODE", "json_schema"),
    )
    parser.add_argument("--max-completion-tokens", type=int, default=768)
    parser.add_argument(
        "--max-tokens-parameter",
        choices=("max_completion_tokens", "max_tokens"),
        default="max_completion_tokens",
    )
    parser.add_argument("--thinking", choices=("enabled", "disabled"), default=None)
    return parser


async def _async_main(args: argparse.Namespace) -> int:
    dataset = load_ablation_dataset(args.dataset)
    definitions = (
        TypeAdapter(list[RelationTypeDefinition]).validate_json(
            args.relation_catalog.read_bytes()
        )
        if args.relation_catalog is not None
        else []
    )
    _query_request(dataset, dataset.queries[0], definitions)
    if args.semantic_review is not None:
        PlannerSemanticReview.model_validate_json(
            args.semantic_review.read_bytes()
        ).validate_dataset(dataset)
    usage = UsageLedger()
    provider: OpenAICompatibleStructuredOutputModel | None = None
    if args.replay_report is not None:
        if (
            args.output is not None
            and args.output.resolve() == args.replay_report.resolve()
        ):
            raise ValueError("replay output must not overwrite its source report")
        base_planner: Any = ReplayPlanner(
            args.replay_report, dataset=dataset, relation_type_definitions=definitions
        )
    elif args.planner == "reference":
        if not str(args.model or "").strip():
            raise RuntimeError("reference planner requires --model or DOPPEL_MODEL")
        if (
            args.max_calls > 0
            and not args.allow_unauthenticated
            and not os.environ.get("DOPPEL_API_KEY", "").strip()
        ):
            raise RuntimeError(
                "DOPPEL_API_KEY is missing; set it in this shell before running. "
                "Use --max-calls 0 for cache-only evaluation, or explicitly opt in "
                "to --allow-unauthenticated for a provider without authentication."
            )
        provider = OpenAICompatibleStructuredOutputModel(
            OpenAICompatibleStructuredOutputConfig(
                model=args.model,
                base_url=args.base_url,
                schema_mode=args.schema_mode,
                max_completion_tokens=args.max_completion_tokens,
                max_tokens_parameter=args.max_tokens_parameter,
                temperature=0,
                thinking=args.thinking,
            ),
            api_key=os.environ.get("DOPPEL_API_KEY", ""),
            usage_observer=usage.observe,
        )
        base_planner = ReferencePersonalMemoryQueryPlanner(provider)
    else:
        base_planner = DeterministicPersonalMemoryQueryPlanner()

    budget = (
        PlannerCallBudget(base_planner, max_calls=args.max_calls)
        if args.replay_report is None and args.planner == "reference"
        else None
    )
    cache = CachedPlanner(
        budget or base_planner,
        None if args.no_cache or args.replay_report is not None else args.cache_dir,
    )
    try:
        report = await run_relation_planner_quality(
            dataset,
            base_planner,
            cache=cache,
            call_budget=budget,
            usage=usage,
            relation_type_definitions=definitions,
        )
        if args.replay_report is not None:
            replay_bytes = args.replay_report.read_bytes()
            source = json.loads(replay_bytes)
            report["replay"] = {
                "source_path": str(args.replay_report.resolve()),
                "source_sha256": hashlib.sha256(replay_bytes).hexdigest(),
                "source_dataset_fingerprint": str(
                    (source.get("dataset") or {}).get("fingerprint") or ""
                ),
                "provider_calls": 0,
            }
    finally:
        if provider is not None:
            await provider.aclose()

    if args.semantic_review is not None:
        report["semantic_review"] = review_planner_report(
            report, dataset, args.semantic_review
        )

    report["implementation"] = {
        "commit_hash": _git_commit_hash(),
        "tracked_dirty_paths": _git_tracked_dirty_paths(),
        "scoring_source_sha256": _fingerprint(
            {
                "retrieval_source_sha256": _source_tree_sha256(),
                "planner_quality": hashlib.sha256(
                    Path(__file__).read_bytes()
                ).hexdigest(),
                "semantic_review": hashlib.sha256(
                    Path(__file__).with_name("planner_semantic_review.py").read_bytes()
                ).hexdigest(),
            }
        ),
        "latency_kind": "local_replay"
        if args.replay_report is not None
        else "planner_with_cache",
    }

    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        file_hash = hashlib.sha256(args.output.read_bytes()).hexdigest()
        args.output.with_suffix(args.output.suffix + ".sha256").write_text(
            f"{file_hash}  {args.output.name}\n", encoding="utf-8"
        )
        print(f"relation planner quality result: {args.output}")
    else:
        sys.stdout.write(rendered)
    metrics = report["metrics"]
    return int(
        metrics["provider_error_count"] > 0
        or metrics["not_run_case_count"] > 0
        or metrics["structural_failure_count"] > args.max_structural_failures
        or (
            args.max_relation_type_failures is not None
            and metrics["relation_type_failure_count"] > args.max_relation_type_failures
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.max_calls < 0:
        raise ValueError("--max-calls must be non-negative")
    if (
        args.max_relation_type_failures is not None
        and args.max_relation_type_failures < 0
    ):
        raise ValueError("--max-relation-type-failures must be non-negative")
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
