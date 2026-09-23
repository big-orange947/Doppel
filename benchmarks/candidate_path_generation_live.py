"""Budgeted candidate-path model probe; dry-run by default, never executes a graph."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
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
SEALED_THRESHOLDS = {
    "min_required_route_recall": 0.80,
    "min_one_hop_route_recall": 0.80,
    "min_two_hop_route_recall": 0.75,
    "max_no_path_false_candidate_rate": 0.25,
    "max_extra_routes_per_case": 0.50,
    "max_extra_types_per_generated_route": 1.00,
    "max_invalid_compilation_count": 0,
    "max_errors": 0,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit_hash() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def quality_gate(
    metrics: dict[str, Any], thresholds: dict[str, float | int]
) -> dict[str, Any]:
    checks = {
        "required_route_recall": metrics["required_route_recall"]
        >= thresholds["min_required_route_recall"],
        "one_hop_route_recall": metrics["one_hop_route_recall"]
        >= thresholds["min_one_hop_route_recall"],
        "two_hop_route_recall": metrics["two_hop_route_recall"]
        >= thresholds["min_two_hop_route_recall"],
        "no_path_false_candidate_rate": metrics["no_path_false_candidate_rate"]
        <= thresholds["max_no_path_false_candidate_rate"],
        "extra_routes_per_case": metrics["extra_routes_per_case"]
        <= thresholds["max_extra_routes_per_case"],
        "extra_types_per_generated_route": metrics["extra_types_per_generated_route"]
        <= thresholds["max_extra_types_per_generated_route"],
        "invalid_compilation_count": metrics["invalid_compilation_count"]
        <= thresholds["max_invalid_compilation_count"],
        "errors": metrics["errors"] <= thresholds["max_errors"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "thresholds": thresholds,
    }


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
        "quality_gate": SEALED_THRESHOLDS,
        "model": configuration.model,
        "schema_mode": configuration.schema_mode,
        "max_completion_tokens": configuration.max_completion_tokens,
        "graph_execution_enabled": False,
        "paid_calls_enabled": args.live,
        "implementation_commit": _git_commit_hash(),
    }
    if not args.live:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if args.sealed_first_run:
        if set(partitions) != set(PARTITIONS):
            raise ValueError("sealed run must include every dataset partition")
        if args.max_calls < len(dataset.cases):
            raise ValueError("sealed run call budget must cover every selected case")
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
            "quality_gate": quality_gate(report["metrics"], SEALED_THRESHOLDS),
        }
    )
    output = args.output or ROOT / "data/doppel/candidate-path-generation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"report: {output.resolve()}")
    print(f"sha256: {_sha256(output)}")
    print(json.dumps(report["metrics"], ensure_ascii=False, sort_keys=True))
    return 0 if report["quality_gate"]["passed"] else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
