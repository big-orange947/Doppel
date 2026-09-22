"""Budgeted live regression for the two-stage relation-path Planner V5."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.relation_path_decision_live import (
    _quality_gate,
)
from benchmarks.relation_path_decision_live import (
    build_plan as build_decision_plan,
)
from benchmarks.relation_path_decision_live import (
    execute_live as execute_decision_live,
)
from benchmarks.relation_path_planner_live import (
    DEFAULT_CATALOG,
    DEFAULT_DATASET,
    PARTITIONS,
    _sha256,
    _write_report,
)
from benchmarks.relation_path_planner_quality import (
    RelationPathPlannerDataset,
    load_dataset,
    load_relation_catalog,
)
from benchmarks.relation_planner_quality import UsageLedger
from doppel_memory import (
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
)
from doppel_memory.query_path import ReferencePersonalMemoryRelationPathPlannerV5
from doppel_memory.relation import RelationTypeDefinition

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / "data/doppel/relation-path-two-stage-cache"
DEFAULT_OUTPUT_ROOT = ROOT / "data/doppel/relation-path-two-stage"


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
    plan = build_decision_plan(
        dataset_path=dataset_path,
        catalog_path=catalog_path,
        partitions=partitions,
        model=model,
        base_url=base_url,
        schema_mode=schema_mode,
        max_completion_tokens=max_completion_tokens,
        max_tokens_parameter=max_tokens_parameter,
        thinking=thinking,
        max_calls=max_calls,
        cache_enabled=cache_enabled,
    )
    plan.update(
        {
            "runner": "doppel.relation-path-two-stage-live.v1",
            "planner_protocol": "v5_model_observation_host_decision",
            "notes": [
                "All V1 partitions are opened regression data after the V3 sealed run.",
                "Dry-run construction never reads DOPPEL_API_KEY or opens a network client.",
                "The model describes up to eight edges and has no execute/abstain field.",
                "Trusted host code alone applies the executable two-hop bound.",
                "No graph query is executed by this scorer.",
            ],
        }
    )
    return plan


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
    report = await execute_decision_live(
        dataset=dataset,
        definitions=definitions,
        model=model,
        partitions=partitions,
        cache_dir=cache_dir,
        max_calls=max_calls,
        provider_metadata=provider_metadata,
        planner_type=ReferencePersonalMemoryRelationPathPlannerV5,
    )
    report.update(
        {
            "runner": "doppel.relation-path-two-stage-quality.v1",
            "planner_protocol": "v5_model_observation_host_decision",
            "model_execution_authority": False,
            "host_executable_path_bound": 2,
        }
    )
    report["implementation"].update(
        {
            "runner_sha256": _sha256(Path(__file__)),
            "decision_runner_sha256": _sha256(
                Path(__file__).with_name("relation_path_decision_live.py")
            ),
        }
    )
    return report


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
    print(f"relation path two-stage report: {output.resolve()}")
    print(f"sha256: {digest}")
    return 0 if report["quality_gate"]["passed"] else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_async_main(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
