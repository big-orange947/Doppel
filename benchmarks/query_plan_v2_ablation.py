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
from typing import Any, cast
from uuid import uuid4

from pydantic import TypeAdapter

from benchmarks.personal_retrieval_ablation import (
    AblationDataset,
    AblationQuery,
    _git_commit_hash,
    _source_tree_sha256,
    load_ablation_dataset,
)
from benchmarks.relation_planner_quality import (
    CachedStructuredOutputModel,
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
)
from doppel_memory.query import QueryIntent, QueryOperation, QueryTemporalView

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = (
    ROOT / "benchmarks/datasets/personal-relation-ablation-zh-v2.json"
)
DEFAULT_CATALOG = ROOT / "benchmarks/catalogs/personal-relations-v2.json"
ARMS = ("v1", "v2")


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
    operation = _operation_from_intent(query.intent)
    primary = _temporal_view_from_shape(
        query.intent,
        as_of=query.as_of,
        time_from=query.time_from,
        time_to=query.time_to,
    )
    accepted: set[QueryTemporalView] = {primary}
    if query.accept_interval_covering_as_of:
        accepted.add(cast(QueryTemporalView, PersonalMemoryQueryTemporalView.INTERVAL))
    if query.as_of is None and query.time_from is None and query.time_to is None:
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


def _input_identity(dataset: Path, catalog: Path) -> dict[str, str]:
    return {
        "commit": _git_commit_hash(),
        "source_sha256": _source_tree_sha256(),
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "catalog_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    dataset = load_ablation_dataset(args.dataset)
    query_count = sum(
        query.partition != "deferred_cross_subject" for query in dataset.queries
    )
    return {
        "runner": "doppel.query-plan-v2-ablation.v1",
        "mode": "live" if args.live else "dry_run",
        "publication_ready": False,
        "arms": list(ARMS),
        "query_count_per_arm": query_count,
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
        "input_identity": _input_identity(args.dataset, args.relation_catalog),
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


async def _run_arm(
    arm: str,
    args: argparse.Namespace,
    dataset: AblationDataset,
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
            return _augment_report(report, dataset, arm=arm)
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
        return _augment_report(
            report, dataset, arm=arm, drafts=wrapper.drafts
        )
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
        if _input_identity(args.dataset, args.relation_catalog) != plan["input_identity"]:
            stop_reason = "inputs_changed"
            break
        print(f"Running {arm} Planner arm", flush=True)
        try:
            report = await _run_arm(arm, args, dataset, definitions)
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
        "--output-root", type=Path, default=ROOT / "data/doppel/query-plan-v2"
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=ROOT / "data/doppel/planner-cache"
    )
    parser.add_argument("--max-calls-per-arm", type=int, default=240)
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
