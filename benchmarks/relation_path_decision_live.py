"""Budgeted live regression for explicit relation-path Planner V4 decisions."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.personal_retrieval_ablation import (
    _git_commit_hash,
    _git_tracked_dirty_paths,
)
from benchmarks.relation_path_decision_quality import (
    run_relation_path_decision_quality,
)
from benchmarks.relation_path_planner_live import (
    DEFAULT_CATALOG,
    DEFAULT_DATASET,
    PARTITIONS,
    _selection_fingerprint,
    _sha256,
    _write_report,
    select_dataset,
)
from benchmarks.relation_path_planner_quality import (
    RelationPathPlannerDataset,
    load_dataset,
    load_relation_catalog,
)
from benchmarks.relation_planner_quality import (
    CachedStructuredOutputModel,
    StructuredOutputCallBudget,
    UsageLedger,
)
from doppel_memory import (
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
    __version__,
)
from doppel_memory.query_path import ReferencePersonalMemoryRelationPathPlannerV4
from doppel_memory.relation import RelationTypeDefinition

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / "data/doppel/relation-path-decision-cache"
DEFAULT_OUTPUT_ROOT = ROOT / "data/doppel/relation-path-decision"


def build_plan(
    *,
    dataset_path: Path,
    catalog_path: Path,
    partitions: Sequence[str],
    model: str,
    base_url: str,
    schema_mode: str,
    max_completion_tokens: int,
    max_tokens_parameter: str,
    thinking: str | None,
    max_calls: int,
    cache_enabled: bool,
) -> dict[str, Any]:
    dataset = select_dataset(load_dataset(dataset_path), partitions)
    definitions = load_relation_catalog(catalog_path)
    config = OpenAICompatibleStructuredOutputConfig(
        model=model,
        base_url=base_url,
        schema_mode=schema_mode,  # type: ignore[arg-type]
        max_completion_tokens=max_completion_tokens,
        max_tokens_parameter=max_tokens_parameter,  # type: ignore[arg-type]
        temperature=0,
        thinking=thinking,  # type: ignore[arg-type]
    )
    return {
        "runner": "doppel.relation-path-decision-live.v1",
        "mode": "dry_run",
        "paid_calls_enabled": False,
        "corpus_role": "opened_regression",
        "eligible_as_unseen_evidence": False,
        "selected_partitions": list(dict.fromkeys(partitions)),
        "case_counts": {
            partition: sum(case.partition == partition for case in dataset.cases)
            for partition in PARTITIONS
        },
        "selected_case_count": len(dataset.cases),
        "maximum_provider_calls": max_calls,
        "one_provider_call_per_case": True,
        "cache": {
            "enabled": cache_enabled,
            "kind": "content_addressed_raw_provider_output"
            if cache_enabled
            else "none",
            "hits_do_not_consume_call_budget": True,
        },
        "provider": {
            "name": "openai-compatible-chat-completions",
            "model": config.model,
            "base_url": config.base_url,
            "schema_mode": config.schema_mode,
            "max_completion_tokens": config.max_completion_tokens,
            "max_tokens_parameter": config.max_tokens_parameter,
            "temperature": config.temperature,
            "thinking": config.thinking,
            "retries": 0,
        },
        "inputs": {
            "dataset": str(dataset_path.resolve()),
            "dataset_sha256": _sha256(dataset_path),
            "dataset_fingerprint": dataset.fingerprint,
            "catalog": str(catalog_path.resolve()),
            "catalog_sha256": _sha256(catalog_path),
            "relation_type_count": len(definitions),
            "selection_fingerprint": _selection_fingerprint(dataset, partitions),
        },
        "notes": [
            "All V1 partitions are opened regression data after the V3 sealed run.",
            "Dry-run construction never reads DOPPEL_API_KEY or opens a network client.",
            "The Planner is scored only and receives no graph execution authority.",
        ],
    }


async def execute_live(
    *,
    dataset: RelationPathPlannerDataset,
    definitions: list[RelationTypeDefinition],
    model: Any,
    partitions: Sequence[str],
    cache_dir: Path | None,
    max_calls: int,
    provider_metadata: dict[str, Any],
    planner_type: Any = ReferencePersonalMemoryRelationPathPlannerV4,
) -> dict[str, Any]:
    selected = select_dataset(dataset, partitions)
    budget = StructuredOutputCallBudget(model, max_calls=max_calls)
    cache = CachedStructuredOutputModel(budget, cache_dir)
    planner = planner_type(cache)
    report = await run_relation_path_decision_quality(selected, planner, definitions)
    metrics = report["metrics"]
    report.update(
        {
            "generated_at": datetime.now().astimezone().isoformat(),
            "doppel_version": __version__,
            "selection": {
                "partitions": list(dict.fromkeys(partitions)),
                "fingerprint": _selection_fingerprint(selected, partitions),
            },
            "provider": provider_metadata,
            "cache": {
                "enabled": cache_dir is not None,
                "kind": "content_addressed_raw_provider_output"
                if cache_dir is not None
                else "none",
                "hits": cache.hits,
                "misses": cache.misses,
                "invalid_entries_ignored": cache.invalid_entries_ignored,
                "legacy_final_drafts_read": cache.legacy_final_drafts_read,
            },
            "budget": {
                "maximum_provider_calls": max_calls,
                "provider_calls": budget.calls,
                "remaining_provider_calls": max(0, max_calls - budget.calls),
                "within_budget": budget.calls <= max_calls,
            },
            "execution": {
                **report.get("execution", {}),
                "complete": metrics["valid_case_count"] == metrics["case_count"],
                "failed_case_count": metrics["error_count"],
                "graph_execution_enabled": False,
            },
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "implementation": {
                "commit_hash": _git_commit_hash(),
                "tracked_dirty_paths": _git_tracked_dirty_paths(),
                "runner_sha256": _sha256(Path(__file__)),
                "scorer_sha256": _sha256(
                    Path(__file__).with_name("relation_path_decision_quality.py")
                ),
            },
        }
    )
    return report


def _quality_gate(
    report: dict[str, Any],
    *,
    min_exact_path_accuracy: float,
    min_decision_accuracy: float,
    min_reason_accuracy: float,
    min_over_bound_reason_accuracy: float,
    max_wrong_execute_count: int,
) -> dict[str, Any]:
    path = report["metrics"]
    decision = report["decision_metrics"]
    failures: list[str] = []
    if not report["execution"]["complete"]:
        failures.append("provider evaluation was incomplete")
    for metric, threshold in (
        ("exact_path_accuracy", min_exact_path_accuracy),
        ("decision_accuracy", min_decision_accuracy),
        ("reason_accuracy", min_reason_accuracy),
        ("over_bound_reason_accuracy", min_over_bound_reason_accuracy),
    ):
        source = path if metric == "exact_path_accuracy" else decision
        if source[metric] < threshold:
            failures.append(f"{metric} below threshold")
    if decision["wrong_execute_count"] > max_wrong_execute_count:
        failures.append("wrong execute count exceeds threshold")
    return {
        "passed": not failures,
        "thresholds": {
            "min_exact_path_accuracy": min_exact_path_accuracy,
            "min_decision_accuracy": min_decision_accuracy,
            "min_reason_accuracy": min_reason_accuracy,
            "min_over_bound_reason_accuracy": min_over_bound_reason_accuracy,
            "max_wrong_execute_count": max_wrong_execute_count,
        },
        "failures": failures,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--relation-catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument(
        "--partition", action="append", choices=PARTITIONS, dest="partitions"
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-calls", type=int, default=32)
    parser.add_argument(
        "--model", default=os.environ.get("DOPPEL_MODEL", "deepseek-v4-flash")
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("DOPPEL_OPENAI_BASE_URL", "https://api.deepseek.com"),
    )
    parser.add_argument(
        "--schema-mode",
        choices=("json_schema", "json_object"),
        default=os.environ.get("DOPPEL_SCHEMA_MODE", "json_object"),
    )
    parser.add_argument("--max-completion-tokens", type=int, default=1024)
    parser.add_argument(
        "--max-tokens-parameter",
        choices=("max_completion_tokens", "max_tokens"),
        default="max_tokens",
    )
    parser.add_argument(
        "--thinking", choices=("enabled", "disabled"), default="disabled"
    )
    parser.add_argument("--min-exact-path-accuracy", type=float, default=0.0)
    parser.add_argument("--min-decision-accuracy", type=float, default=0.0)
    parser.add_argument("--min-reason-accuracy", type=float, default=0.0)
    parser.add_argument("--min-over-bound-reason-accuracy", type=float, default=0.0)
    parser.add_argument("--max-wrong-execute-count", type=int, default=0)
    return parser


async def _async_main(args: argparse.Namespace) -> int:
    if args.max_calls < 0:
        raise ValueError("--max-calls must be non-negative")
    for name in (
        "min_exact_path_accuracy",
        "min_decision_accuracy",
        "min_reason_accuracy",
        "min_over_bound_reason_accuracy",
    ):
        value = getattr(args, name)
        if not 0 <= value <= 1:
            raise ValueError(f"--{name.replace('_', '-')} must be between 0 and 1")
    if args.max_wrong_execute_count < 0:
        raise ValueError("--max-wrong-execute-count must be non-negative")
    partitions = args.partitions or list(PARTITIONS)
    plan = build_plan(
        dataset_path=args.dataset,
        catalog_path=args.relation_catalog,
        partitions=partitions,
        model=args.model,
        base_url=args.base_url,
        schema_mode=args.schema_mode,
        max_completion_tokens=args.max_completion_tokens,
        max_tokens_parameter=args.max_tokens_parameter,
        thinking=args.thinking,
        max_calls=args.max_calls,
        cache_enabled=not args.no_cache,
    )
    if not args.live:
        sys.stdout.write(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
        return 0
    api_key = os.environ.get("DOPPEL_API_KEY", "").strip()
    if args.max_calls > 0 and not api_key:
        raise RuntimeError(
            "DOPPEL_API_KEY is missing; set it before --live, or use --max-calls 0 "
            "for a cache-only run"
        )
    usage = UsageLedger()
    config = OpenAICompatibleStructuredOutputConfig(
        model=args.model,
        base_url=args.base_url,
        schema_mode=args.schema_mode,
        max_completion_tokens=args.max_completion_tokens,
        max_tokens_parameter=args.max_tokens_parameter,
        temperature=0,
        thinking=args.thinking,
    )
    provider = OpenAICompatibleStructuredOutputModel(
        config, api_key=api_key, usage_observer=usage.observe
    )
    try:
        report = await execute_live(
            dataset=load_dataset(args.dataset),
            definitions=load_relation_catalog(args.relation_catalog),
            model=provider,
            partitions=partitions,
            cache_dir=None if args.no_cache else args.cache_dir,
            max_calls=args.max_calls,
            provider_metadata={**plan["provider"], "version": provider.version},
        )
    finally:
        await provider.aclose()
    report["usage"] = usage.report()
    report["quality_gate"] = _quality_gate(
        report,
        min_exact_path_accuracy=args.min_exact_path_accuracy,
        min_decision_accuracy=args.min_decision_accuracy,
        min_reason_accuracy=args.min_reason_accuracy,
        min_over_bound_reason_accuracy=args.min_over_bound_reason_accuracy,
        max_wrong_execute_count=args.max_wrong_execute_count,
    )
    output = args.output or (
        DEFAULT_OUTPUT_ROOT
        / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-regression.json"
    )
    digest = _write_report(output, report)
    print(f"relation path decision report: {output.resolve()}")
    print(f"sha256: {digest}")
    return 0 if report["quality_gate"]["passed"] else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_async_main(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
