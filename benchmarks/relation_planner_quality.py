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
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from benchmarks.personal_retrieval_ablation import (
    AblationDataset,
    AblationQuery,
    load_ablation_dataset,
)
from doppel_memory import (
    Actor,
    DeterministicPersonalMemoryQueryPlanner,
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
    PersonalMemoryQueryDraft,
    PersonalMemoryQueryRequest,
    ReferencePersonalMemoryQueryPlanner,
    StructuredOutputProviderError,
    __version__,
)

DEFAULT_DATASET = (
    Path(__file__).parent / "datasets" / "personal-relation-ablation-zh-v1.json"
)
CACHE_FORMAT_VERSION = 1


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
        draft = PersonalMemoryQueryDraft.model_validate(
            await self._planner.plan(bound)
        )
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
            "request": request.model_dump(mode="json"),
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

    def __init__(self, report_path: Path) -> None:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
        planner = dict(raw.get("planner") or {})
        self.name = str(planner.get("name") or "doppel.replay-planner")
        self.version = str(planner.get("version") or "unknown")
        self._drafts = {
            str(item.get("query") or ""): item.get("actual")
            for item in list(raw.get("cases") or [])
            if not item.get("error") and item.get("actual") is not None
        }

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraft:
        raw = self._drafts.get(request.query)
        if raw is None:
            raise KeyError("prior report has no successful draft for this query")
        return PersonalMemoryQueryDraft.model_validate(raw)


async def run_relation_planner_quality(
    dataset: AblationDataset,
    planner: Any,
    *,
    cache: CachedPlanner | None = None,
    call_budget: PlannerCallBudget | None = None,
    usage: UsageLedger | None = None,
) -> dict[str, Any]:
    """Run one planner over relation gold without executing retrieval."""

    if not dataset.requirements.get("relation_benchmark", False):
        raise ValueError("relation planner quality requires a relation benchmark")
    runner = cache or planner
    cases: list[dict[str, Any]] = []
    for query in dataset.queries:
        if query.partition == "deferred_cross_subject":
            continue
        cases.append(await _evaluate_case(runner, dataset, query))

    valid = [case for case in cases if not case["error"]]
    structural_failures = sum(not case["structure_ok"] for case in valid)
    provider_errors = sum(bool(case["error"]) for case in cases)
    total_expected_entities = sum(case["expected_entity_count"] for case in valid)
    total_matched_entities = sum(case["matched_entity_count"] for case in valid)
    total_expected_relations = sum(case["expected_relation_count"] for case in valid)
    total_matched_relations = sum(case["matched_relation_count"] for case in valid)
    by_partition = _group_metrics(cases, "partition")
    by_category = _group_metrics(cases, "category")
    latencies = sorted(case["latency_ms"] for case in cases)
    return {
        "runner": "doppel.relation-planner-quality.v1",
        "doppel_version": __version__,
        "generated_at": datetime.now().astimezone().isoformat(),
        "dataset": {
            "name": dataset.suite,
            "version": dataset.suite_version,
            "fingerprint": dataset.fingerprint,
            "query_count": len(cases),
            "frozen": dataset.frozen,
            "publication_ready": dataset.publication_ready,
        },
        "planner": {
            "name": str(planner.name),
            "version": str(planner.version),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "metrics": {
            "case_count": len(cases),
            "valid_case_count": len(valid),
            "provider_error_count": provider_errors,
            "structural_failure_count": structural_failures,
            "exact_structure_accuracy": _ratio(
                len(valid) - structural_failures, len(cases)
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
            "entity_recall": _ratio(total_matched_entities, total_expected_entities),
            "relation_recall": _ratio(
                total_matched_relations, total_expected_relations
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


async def _evaluate_case(
    planner: Any,
    dataset: AblationDataset,
    query: AblationQuery,
) -> dict[str, Any]:
    scope = dataset.scopes[query.scopes[0]].to_scope()
    request = PersonalMemoryQueryRequest(
        query=query.query,
        now=query.now,
        default_subject=Actor.OWNER,
        default_subject_id=scope.user_id,
    )
    started = perf_counter()
    try:
        draft = PersonalMemoryQueryDraft.model_validate(await planner.plan(request))
    except Exception as exc:  # noqa: BLE001 - report sanitized provider failure only
        code = exc.code if isinstance(exc, StructuredOutputProviderError) else ""
        return {
            "query_id": query.query_id,
            "partition": query.partition,
            "category": query.category,
            "query": query.query,
            "error": type(exc).__name__,
            "error_code": code,
            "latency_ms": round((perf_counter() - started) * 1_000, 3),
            "structure_ok": False,
            "intent_ok": False,
            "intent_semantics_ok": False,
            "as_of_presence_ok": False,
            "as_of_date_ok": False,
            "temporal_plan_ok": False,
            "expected_entity_count": len(query.entity_mentions),
            "matched_entity_count": 0,
            "unexpected_entity_count": 0,
            "expected_relation_count": len(query.relation_hints),
            "matched_relation_count": 0,
            "unexpected_relation_count": 0,
            "unexpected_hard_filter_count": 0,
            "hard_filter_ok": False,
            "actual": None,
        }

    expected_as_of = query.as_of
    actual_as_of = draft.as_of
    intent_ok = draft.intent == query.intent
    accepted_intents = set(query.accepted_intents or [query.intent])
    intent_semantics_ok = draft.intent in accepted_intents
    as_of_presence_ok = (expected_as_of is None) == (actual_as_of is None)
    as_of_date_ok = as_of_presence_ok and (
        expected_as_of is None
        or (
            actual_as_of is not None
            and actual_as_of.date() == expected_as_of.date()
        )
    )
    interval_covers_as_of = bool(
        query.accept_interval_covering_as_of
        and expected_as_of is not None
        and draft.time_from is not None
        and draft.time_to is not None
        and draft.time_from <= expected_as_of <= draft.time_to
    )
    temporal_plan_ok = as_of_date_ok or interval_covers_as_of
    matched_entities, unexpected_entities = _term_matches(
        query.entity_mentions, draft.entity_mentions
    )
    matched_relations, unexpected_relations = _term_matches(
        query.relation_hints, draft.relation_hints
    )
    entity_ok = matched_entities == len(query.entity_mentions) and not unexpected_entities
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
    )
    return {
        "query_id": query.query_id,
        "partition": query.partition,
        "category": query.category,
        "query": query.query,
        "error": "",
        "error_code": "",
        "latency_ms": round((perf_counter() - started) * 1_000, 3),
        "structure_ok": structure_ok,
        "intent_ok": intent_ok,
        "intent_semantics_ok": intent_semantics_ok,
        "as_of_presence_ok": as_of_presence_ok,
        "as_of_date_ok": as_of_date_ok,
        "temporal_plan_ok": temporal_plan_ok,
        "interval_covers_as_of": interval_covers_as_of,
        "expected_entity_count": len(query.entity_mentions),
        "matched_entity_count": matched_entities,
        "unexpected_entity_count": len(unexpected_entities),
        "expected_relation_count": len(query.relation_hints),
        "matched_relation_count": matched_relations,
        "unexpected_relation_count": len(unexpected_relations),
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
            if expected_term and actual_term and (
                expected_term in actual_term or actual_term in expected_term
            ):
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
            "provider_error_count": sum(bool(item["error"]) for item in items),
            "structural_failure_count": sum(
                not item["structure_ok"] for item in items
            ),
            "exact_structure_accuracy": _ratio(
                sum(item["structure_ok"] for item in items), len(items)
            ),
        }
        for name, items in sorted(grouped.items())
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    index = max(0, min(len(values) - 1, int((len(values) - 1) * quantile)))
    return round(values[index], 3)


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--planner", choices=("deterministic", "reference"), default="deterministic"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--replay-report",
        type=Path,
        help="re-score successful drafts from a prior report with zero provider calls",
    )
    parser.add_argument("--cache-dir", type=Path, default=Path("data/doppel/planner-cache"))
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--max-calls", type=int, default=40)
    parser.add_argument("--max-structural-failures", type=int, default=0)
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
    parser.add_argument(
        "--thinking", choices=("enabled", "disabled"), default=None
    )
    return parser


async def _async_main(args: argparse.Namespace) -> int:
    dataset = load_ablation_dataset(args.dataset)
    usage = UsageLedger()
    provider: OpenAICompatibleStructuredOutputModel | None = None
    if args.replay_report is not None:
        base_planner: Any = ReplayPlanner(args.replay_report)
    elif args.planner == "reference":
        if not str(args.model or "").strip():
            raise RuntimeError("reference planner requires --model or DOPPEL_MODEL")
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
        None
        if args.replay_report is not None
        else PlannerCallBudget(base_planner, max_calls=args.max_calls)
    )
    cache = CachedPlanner(
        budget or base_planner,
        None
        if args.no_cache or args.replay_report is not None
        else args.cache_dir,
    )
    try:
        report = await run_relation_planner_quality(
            dataset,
            base_planner,
            cache=cache,
            call_budget=budget,
            usage=usage,
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

    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"relation planner quality result: {args.output}")
    else:
        sys.stdout.write(rendered)
    metrics = report["metrics"]
    return int(
        metrics["provider_error_count"] > 0
        or metrics["structural_failure_count"] > args.max_structural_failures
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.max_calls < 0:
        raise ValueError("--max-calls must be non-negative")
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
