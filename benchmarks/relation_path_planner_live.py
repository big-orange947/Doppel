"""Budgeted live evaluation for the experimental relation-path Planner v3.

The command is a dry run unless ``--live`` is supplied. Provider outputs are
cached before planner validation, so a successful HTTP response can be re-scored
after local planner/scoring changes without another paid call.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
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
from benchmarks.relation_path_planner_quality import (
    RelationPathPlannerDataset,
    load_dataset,
    load_relation_catalog,
    run_relation_path_planner_quality,
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
from doppel_memory.query_path import ReferencePersonalMemoryRelationPathPlannerV3
from doppel_memory.relation import RelationTypeDefinition

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = (
    ROOT / "benchmarks/datasets/relation-path-planner-quality-zh-v1.json"
)
DEFAULT_CATALOG = ROOT / "benchmarks/catalogs/personal-relations-v1.json"
DEFAULT_CACHE = ROOT / "data/doppel/relation-path-planner-cache"
DEFAULT_OUTPUT_ROOT = ROOT / "data/doppel/relation-path-planner"
PARTITIONS = ("dev", "heldout", "adversarial")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _selection_fingerprint(
    dataset: RelationPathPlannerDataset, partitions: Sequence[str]
) -> str:
    payload = {
        "dataset_fingerprint": dataset.fingerprint,
        "partitions": list(partitions),
        "case_ids": [case.case_id for case in dataset.cases],
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def select_dataset(
    dataset: RelationPathPlannerDataset, partitions: Sequence[str]
) -> RelationPathPlannerDataset:
    selected = tuple(dict.fromkeys(partitions))
    unknown = sorted(set(selected).difference(PARTITIONS))
    if unknown:
        raise ValueError(f"unknown partitions: {unknown}")
    if not selected:
        raise ValueError("at least one partition is required")
    cases = [case for case in dataset.cases if case.partition in selected]
    if not cases:
        raise ValueError("partition selection contains no cases")
    return dataset.model_copy(update={"cases": cases})


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
    counts = {
        partition: sum(case.partition == partition for case in dataset.cases)
        for partition in PARTITIONS
    }
    return {
        "runner": "doppel.relation-path-planner-live.v1",
        "mode": "dry_run",
        "paid_calls_enabled": False,
        "selected_partitions": list(dict.fromkeys(partitions)),
        "case_counts": counts,
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
            "Dry-run construction never reads DOPPEL_API_KEY or opens a network client.",
            "Use dev while changing prompts; evaluate heldout/adversarial only after freezing the implementation.",
            "Planner output is scored only; it is not granted graph execution authority.",
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
) -> dict[str, Any]:
    selected = select_dataset(dataset, partitions)
    budget = StructuredOutputCallBudget(model, max_calls=max_calls)
    cache = CachedStructuredOutputModel(budget, cache_dir)
    planner = ReferencePersonalMemoryRelationPathPlannerV3(cache)
    report = await run_relation_path_planner_quality(selected, planner, definitions)
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
                    Path(__file__).with_name("relation_path_planner_quality.py")
                ),
            },
        }
    )
    return report


def _quality_gate(
    report: dict[str, Any],
    *,
    min_exact_path_accuracy: float,
    min_path_recall: float,
    min_relation_type_accuracy: float,
    min_direction_accuracy: float,
    min_no_path_accuracy: float,
    max_false_path_count: int,
    max_forbidden_relation_type_hits: int,
) -> dict[str, Any]:
    metrics = report["metrics"]
    failures: list[str] = []
    if not report["execution"]["complete"]:
        failures.append("provider evaluation was incomplete")
    if metrics["exact_path_accuracy"] < min_exact_path_accuracy:
        failures.append("exact_path_accuracy below threshold")
    if metrics["path_recall"] < min_path_recall:
        failures.append("path_recall below threshold")
    if metrics["relation_type_accuracy"] < min_relation_type_accuracy:
        failures.append("relation_type_accuracy below threshold")
    if metrics["direction_accuracy"] < min_direction_accuracy:
        failures.append("direction_accuracy below threshold")
    if metrics["no_path_accuracy"] < min_no_path_accuracy:
        failures.append("no_path_accuracy below threshold")
    if metrics["false_path_count"] > max_false_path_count:
        failures.append("false path count exceeds threshold")
    if (
        metrics["forbidden_relation_type_hits"]
        > max_forbidden_relation_type_hits
    ):
        failures.append("forbidden relation-type hits exceed threshold")
    return {
        "passed": not failures,
        "thresholds": {
            "min_exact_path_accuracy": min_exact_path_accuracy,
            "min_path_recall": min_path_recall,
            "min_relation_type_accuracy": min_relation_type_accuracy,
            "min_direction_accuracy": min_direction_accuracy,
            "min_no_path_accuracy": min_no_path_accuracy,
            "max_false_path_count": max_false_path_count,
            "max_forbidden_relation_type_hits": max_forbidden_relation_type_hits,
        },
        "failures": failures,
    }


def _write_report(path: Path, report: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as target:
        target.write(rendered)
    digest = _sha256(path)
    with path.with_suffix(path.suffix + ".sha256").open(
        "x", encoding="utf-8", newline="\n"
    ) as sidecar:
        sidecar.write(f"{digest}  {path.name}\n")
    return digest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--relation-catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument(
        "--partition",
        action="append",
        choices=PARTITIONS,
        dest="partitions",
        help="repeat to select multiple partitions; default: dev",
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
    parser.add_argument("--min-path-recall", type=float, default=0.0)
    parser.add_argument("--min-relation-type-accuracy", type=float, default=0.0)
    parser.add_argument("--min-direction-accuracy", type=float, default=0.0)
    parser.add_argument("--min-no-path-accuracy", type=float, default=0.0)
    parser.add_argument("--max-false-path-count", type=int, default=0)
    parser.add_argument("--max-forbidden-relation-type-hits", type=int, default=0)
    return parser


async def _async_main(args: argparse.Namespace) -> int:
    if args.max_calls < 0:
        raise ValueError("--max-calls must be non-negative")
    for name in (
        "min_exact_path_accuracy",
        "min_path_recall",
        "min_relation_type_accuracy",
        "min_direction_accuracy",
        "min_no_path_accuracy",
    ):
        value = getattr(args, name)
        if not 0 <= value <= 1:
            raise ValueError(f"--{name.replace('_', '-')} must be between 0 and 1")
    for name in ("max_false_path_count", "max_forbidden_relation_type_hits"):
        if getattr(args, name) < 0:
            raise ValueError(f"--{name.replace('_', '-')} must be non-negative")
    partitions = args.partitions or ["dev"]
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
            "DOPPEL_API_KEY is missing; set it in this shell before --live, or "
            "use --max-calls 0 for a cache-only run"
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
        min_path_recall=args.min_path_recall,
        min_relation_type_accuracy=args.min_relation_type_accuracy,
        min_direction_accuracy=args.min_direction_accuracy,
        min_no_path_accuracy=args.min_no_path_accuracy,
        max_false_path_count=args.max_false_path_count,
        max_forbidden_relation_type_hits=args.max_forbidden_relation_type_hits,
    )
    output = args.output or (
        DEFAULT_OUTPUT_ROOT
        / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{'-'.join(partitions)}.json"
    )
    digest = _write_report(output, report)
    print(f"relation path planner report: {output.resolve()}")
    print(f"sha256: {digest}")
    return 0 if report["quality_gate"]["passed"] else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_async_main(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
