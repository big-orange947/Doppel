"""Resumable, commit-bound topology acquisition for the frozen combined corpus."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.candidate_path_generation_quality import (
    CandidateGenerationCase,
    CandidateGenerationDataset,
    score_candidate_generation,
)
from benchmarks.combined_retrieval_quality import load_dataset
from benchmarks.relation_path_planner_quality import load_relation_catalog
from benchmarks.relation_planner_quality import (
    CachedStructuredOutputModel,
    PlannerCallBudgetExceeded,
    StructuredOutputCallBudget,
    UsageLedger,
)
from doppel_memory.openai_compatible import (
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
)
from doppel_memory.query_path_candidate import (
    CandidateRelationGenerationRequest,
    ReferenceCandidateRelationPathGeneratorV3,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "benchmarks/datasets/combined-retrieval-zh-v2.json"
DEFAULT_CATALOG = ROOT / "benchmarks/catalogs/personal-relations-v1.json"
DEFAULT_CACHE = ROOT / "data/doppel/combined-retrieval-v2-provider-cache"
DEFAULT_PROGRESS = ROOT / "data/doppel/combined-retrieval-v2-progress.json"
DEFAULT_OUTPUT = ROOT / "data/doppel/combined-retrieval-v2-topology.json"
MANIFEST_NAME = "acquisition-manifest.json"
STATE_NAME = "acquisition-state.json"
TOPOLOGY_THRESHOLDS = {
    "min_required_route_recall": 0.75,
    "min_one_hop_route_recall": 0.85,
    "min_two_hop_route_recall": 0.65,
    "max_no_path_false_candidate_rate": 0.20,
    "max_extra_routes_per_case": 0.50,
    "max_invalid_compilation_count": 0,
    "max_errors": 0,
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--live", action="store_true")
    result.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    result.add_argument("--relation-catalog", type=Path, default=DEFAULT_CATALOG)
    result.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    result.add_argument("--progress-output", type=Path, default=DEFAULT_PROGRESS)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--max-new-calls", type=int, default=20)
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
    if args.max_new_calls < 0:
        raise ValueError("max-new-calls must not be negative")
    combined = load_dataset(args.dataset)
    definitions = load_relation_catalog(args.relation_catalog)
    scoring_dataset = CandidateGenerationDataset(
        suite=combined.suite,
        version=combined.version,
        frozen=combined.frozen,
        publication_ready=combined.publication_ready,
        relation_catalog=combined.relation_catalog,
        cases=[
            CandidateGenerationCase(
                case_id=item.case_id,
                partition=(
                    "adversarial" if item.partition == "adversarial" else "heldout"
                ),
                query=item.query,
                anchor=item.anchor,
                required_routes=item.required_routes,
            )
            for item in combined.queries
        ],
    )
    config = OpenAICompatibleStructuredOutputConfig(
        model=args.model,
        base_url=args.base_url,
        schema_mode=args.schema_mode,
        max_completion_tokens=args.max_completion_tokens,
        max_tokens_parameter="max_tokens",
        temperature=0,
        thinking="disabled",
        timeout_seconds=args.timeout_seconds,
    )
    plan = {
        "runner": "doppel.combined-retrieval-acquire.v1",
        "mode": "live" if args.live else "dry_run",
        "dataset_fingerprint": combined.fingerprint,
        "dataset_sha256": _sha256(args.dataset),
        "catalog_sha256": _sha256(args.relation_catalog),
        "case_count": len(scoring_dataset.cases),
        "generator_protocol": "v3_two_pass_review",
        "provider_calls_per_uncached_case": 2,
        "maximum_total_uncached_calls": len(scoring_dataset.cases) * 2,
        "maximum_new_calls_this_invocation": args.max_new_calls,
        "model": config.model,
        "base_url": config.base_url,
        "schema_mode": config.schema_mode,
        "max_completion_tokens": config.max_completion_tokens,
        "temperature": config.temperature,
        "thinking": config.thinking,
        "quality_gate": TOPOLOGY_THRESHOLDS,
        "graph_execution_enabled": False,
        "implementation_commit": _git_commit_hash(),
    }
    if not args.live:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if args.output.exists():
        raise ValueError("completed first-run output already exists")
    key = os.environ.get("DOPPEL_API_KEY", "").strip()
    if not key and args.max_new_calls > 0:
        raise RuntimeError("DOPPEL_API_KEY is required for new provider calls")

    usage = UsageLedger()
    provider = OpenAICompatibleStructuredOutputModel(
        config,
        api_key=key or "cache-only-no-network",
        usage_observer=usage.observe,
    )
    budget = StructuredOutputCallBudget(provider, max_calls=args.max_new_calls)
    cached = CachedStructuredOutputModel(budget, args.cache_dir)
    generator = ReferenceCandidateRelationPathGeneratorV3(cached)
    binding_plan = dict(plan)
    binding_plan.pop("maximum_new_calls_this_invocation")
    binding = {
        **binding_plan,
        "mode": "sealed_acquisition",
        "generator": {"name": generator.name, "version": generator.version},
    }
    manifest_path = args.cache_dir / MANIFEST_NAME
    state_path = args.cache_dir / STATE_NAME
    _bind_manifest(manifest_path, binding)
    prior_state = _load_state(state_path)
    completed: list[str] = []
    stopped_reason = ""
    stopped_at = ""
    definitions_list = list(definitions)
    try:
        for case in scoring_dataset.cases:
            try:
                await generator.generate(
                    CandidateRelationGenerationRequest(
                        query=case.query,
                        anchor=case.anchor,
                        relation_type_definitions=definitions_list,
                    )
                )
            except PlannerCallBudgetExceeded:
                stopped_reason = "budget_exhausted"
                stopped_at = case.case_id
                break
            except Exception as exc:  # noqa: BLE001 - redact provider details
                stopped_reason = type(exc).__name__
                stopped_at = case.case_id
                break
            completed.append(case.case_id)
    finally:
        await provider.aclose()

    cumulative_usage = _merge_usage(prior_state.get("usage", {}), usage.report())
    cumulative_calls = int(prior_state.get("provider_calls", 0)) + budget.calls
    complete = len(completed) == len(scoring_dataset.cases) and not stopped_reason
    state = {
        "state_schema_version": 1,
        "binding_sha256": _fingerprint(binding),
        "updated_at": datetime.now(UTC).isoformat(),
        "complete": complete,
        "completed_case_count": len(completed),
        "case_count": len(scoring_dataset.cases),
        "provider_calls": cumulative_calls,
        "usage": cumulative_usage,
        "last_invocation": {
            "provider_calls": budget.calls,
            "cache_hits": cached.hits,
            "cache_misses": cached.misses,
            "invalid_cache_entries": cached.invalid_entries_ignored,
            "stopped_reason": stopped_reason,
            "stopped_at_case_id": stopped_at,
        },
    }
    _write_json(state_path, state)
    progress = {
        "runner": plan["runner"],
        "status": "complete" if complete else "incomplete",
        "dataset_fingerprint": combined.fingerprint,
        "implementation_commit": plan["implementation_commit"],
        "completed_case_count": len(completed),
        "case_count": len(scoring_dataset.cases),
        "provider_calls_cumulative": cumulative_calls,
        "usage_cumulative": cumulative_usage,
        "last_invocation": state["last_invocation"],
        "metrics_available": complete,
    }
    _write_json(args.progress_output, progress)
    if not complete:
        print(json.dumps(progress, ensure_ascii=False, indent=2))
        return 0

    # Every request is now cache-backed. A zero-call scorer validates the complete
    # acquisition again before any quality metric is exposed.
    replay_budget = StructuredOutputCallBudget(provider, max_calls=0)
    replay_cache = CachedStructuredOutputModel(replay_budget, args.cache_dir)
    replay_generator = ReferenceCandidateRelationPathGeneratorV3(replay_cache)
    report = await score_candidate_generation(
        scoring_dataset, replay_generator, definitions_list
    )
    report.update(
        {
            "corpus_role": "frozen_provider_unseen_first_run",
            "binding": binding,
            "acquisition": state,
            "quality_gate": topology_quality_gate(report["metrics"]),
            "generated_at": datetime.now(UTC).isoformat(),
        }
    )
    _write_json(args.output, report)
    print(f"report: {args.output.resolve()}")
    print(f"sha256: {_sha256(args.output)}")
    print(json.dumps(report["metrics"], ensure_ascii=False, sort_keys=True))
    print(json.dumps(report["quality_gate"], ensure_ascii=False, sort_keys=True))
    return 0 if report["quality_gate"]["passed"] else 1


def topology_quality_gate(metrics: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "required_route_recall": metrics["required_route_recall"]
        >= TOPOLOGY_THRESHOLDS["min_required_route_recall"],
        "one_hop_route_recall": metrics["one_hop_route_recall"]
        >= TOPOLOGY_THRESHOLDS["min_one_hop_route_recall"],
        "two_hop_route_recall": metrics["two_hop_route_recall"]
        >= TOPOLOGY_THRESHOLDS["min_two_hop_route_recall"],
        "no_path_false_candidate_rate": metrics["no_path_false_candidate_rate"]
        <= TOPOLOGY_THRESHOLDS["max_no_path_false_candidate_rate"],
        "extra_routes_per_case": metrics["extra_routes_per_case"]
        <= TOPOLOGY_THRESHOLDS["max_extra_routes_per_case"],
        "invalid_compilation_count": metrics["invalid_compilation_count"]
        <= TOPOLOGY_THRESHOLDS["max_invalid_compilation_count"],
        "errors": metrics["errors"] <= TOPOLOGY_THRESHOLDS["max_errors"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "thresholds": TOPOLOGY_THRESHOLDS,
    }


def _bind_manifest(path: Path, binding: dict[str, Any]) -> None:
    if path.exists():
        existing = json.loads(path.read_text("utf-8"))
        if existing != binding:
            raise ValueError("acquisition manifest does not match current binding")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    unexpected = [item for item in path.parent.iterdir() if item.name != path.name]
    if unexpected:
        raise ValueError("new sealed acquisition requires an empty cache directory")
    _write_json(path, binding)


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text("utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("acquisition state must be an object")
    return raw


def _merge_usage(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, int]:
    names = set(previous).union(current)
    return {
        name: int(previous.get(name, 0)) + int(current.get(name, 0))
        for name in sorted(names)
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    os.replace(temporary, path)


def _fingerprint(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
