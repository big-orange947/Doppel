"""Budgeted candidate-path model probe; dry-run by default, never executes a graph."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.candidate_path_generation_quality import (
    CandidateGenerationDataset,
    load_dataset,
    score_candidate_generation,
)
from benchmarks.relation_path_planner_quality import load_relation_catalog
from benchmarks.relation_planner_quality import (
    CachedStructuredOutputModel,
    StructuredOutputCallBudget,
    UsageLedger,
)
from doppel_memory.openai_compatible import (
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
)
from doppel_memory.query_path_candidate import ReferenceCandidateRelationPathGenerator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "benchmarks/datasets/candidate-path-generation-zh-v1.json"
DEFAULT_CATALOG = ROOT / "benchmarks/catalogs/personal-relations-v1.json"
PARTITIONS = ("dev", "heldout", "adversarial")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _selected(
    dataset: CandidateGenerationDataset, partitions: Sequence[str]
) -> CandidateGenerationDataset:
    cases = [case for case in dataset.cases if case.partition in partitions]
    if not cases:
        raise ValueError("selected partitions contain no cases")
    return dataset.model_copy(update={"cases": cases})


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--live", action="store_true")
    result.add_argument("--sealed-first-run", action="store_true")
    result.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    result.add_argument("--relation-catalog", type=Path, default=DEFAULT_CATALOG)
    result.add_argument("--partition", action="append", choices=PARTITIONS)
    result.add_argument(
        "--cache-dir",
        type=Path,
        default=ROOT / "data/doppel/candidate-path-generation-cache",
    )
    result.add_argument("--output", type=Path)
    result.add_argument("--max-calls", type=int, default=18)
    result.add_argument(
        "--model", default=os.environ.get("DOPPEL_MODEL", "deepseek-v4-flash")
    )
    result.add_argument(
        "--base-url",
        default=os.environ.get("DOPPEL_OPENAI_BASE_URL", "https://api.deepseek.com"),
    )
    result.add_argument(
        "--schema-mode",
        choices=("json_object", "json_schema"),
        default=os.environ.get("DOPPEL_SCHEMA_MODE", "json_object"),
    )
    result.add_argument("--max-completion-tokens", type=int, default=1024)
    result.add_argument("--timeout-seconds", type=float, default=60.0)
    return result


async def run(args: argparse.Namespace) -> int:
    if args.max_calls < 0:
        raise ValueError("max-calls must be non-negative")
    partitions = list(dict.fromkeys(args.partition or list(PARTITIONS)))
    dataset = _selected(load_dataset(args.dataset), partitions)
    definitions = load_relation_catalog(args.relation_catalog)
    configuration = OpenAICompatibleStructuredOutputConfig(
        model=args.model,
        base_url=args.base_url,
        schema_mode=args.schema_mode,
        max_completion_tokens=args.max_completion_tokens,
        max_tokens_parameter="max_tokens",
        temperature=0,
        thinking="disabled",
        timeout_seconds=args.timeout_seconds,
    )
    plan: dict[str, Any] = {
        "runner": "doppel.candidate-path-generation-live.v1",
        "mode": "live" if args.live else "dry_run",
        "partitions": partitions,
        "case_count": len(dataset.cases),
        "dataset_sha256": _sha256(args.dataset),
        "catalog_sha256": _sha256(args.relation_catalog),
        "maximum_provider_calls": args.max_calls,
        "model": configuration.model,
        "schema_mode": configuration.schema_mode,
        "max_completion_tokens": configuration.max_completion_tokens,
        "graph_execution_enabled": False,
        "paid_calls_enabled": args.live,
    }
    if not args.live:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if args.sealed_first_run:
        if not dataset.frozen or args.output is None or args.output.exists():
            raise ValueError("sealed run needs frozen data and a new explicit output")
        if args.cache_dir.exists() and any(args.cache_dir.rglob("*.json")):
            raise ValueError("sealed run needs an empty provider-output cache")
    key = os.environ.get("DOPPEL_API_KEY", "").strip()
    if not key:
        raise RuntimeError("DOPPEL_API_KEY is required for --live")
    usage = UsageLedger()
    provider = OpenAICompatibleStructuredOutputModel(
        configuration, api_key=key, usage_observer=usage.observe
    )
    budget = StructuredOutputCallBudget(provider, max_calls=args.max_calls)
    cached = CachedStructuredOutputModel(budget, args.cache_dir)
    try:
        report = await score_candidate_generation(
            dataset, ReferenceCandidateRelationPathGenerator(cached), definitions
        )
    finally:
        await provider.aclose()
    report.update(
        {
            "plan": plan,
            "generated_at": datetime.now(UTC).isoformat(),
            "corpus_role": "sealed_first_run"
            if args.sealed_first_run
            else "opened_regression",
            "usage": usage.report(),
            "budget": {"provider_calls": budget.calls, "maximum": args.max_calls},
            "cache": {"hits": cached.hits, "misses": cached.misses},
        }
    )
    output = args.output or ROOT / "data/doppel/candidate-path-generation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"report: {output.resolve()}")
    print(f"sha256: {_sha256(output)}")
    print(json.dumps(report["metrics"], ensure_ascii=False, sort_keys=True))
    return 0 if not report["metrics"]["errors"] else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
