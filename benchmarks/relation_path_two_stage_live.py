"""Budgeted live regression for staged relation-path Planner protocols."""

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
from doppel_memory.query_path import (
    ReferencePersonalMemoryRelationPathPlannerV5,
    ReferencePersonalMemoryRelationPathPlannerV6,
    ReferencePersonalMemoryRelationPathPlannerV7,
)
from doppel_memory.relation import RelationTypeDefinition

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / "data/doppel/relation-path-two-stage-cache"
DEFAULT_OUTPUT_ROOT = ROOT / "data/doppel/relation-path-two-stage"
SEALED_THRESHOLDS = {
    "min_exact_path_accuracy": 0.90,
    "min_decision_accuracy": 0.95,
    "min_reason_accuracy": 0.90,
    "min_over_bound_reason_accuracy": 1.0,
    "max_wrong_execute_count": 0,
    "min_relation_type_accuracy": 0.98,
    "min_direction_accuracy": 0.95,
    "min_path_recall": 0.95,
    "min_one_hop_exact_path_accuracy": 0.90,
    "min_two_hop_exact_path_accuracy": 0.85,
    "min_no_path_accuracy": 1.0,
    "max_forbidden_relation_type_hits": 0,
    "max_error_count": 0,
}


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
    sealed_first_run: bool = False,
    atom_protocol: bool = False,
    review_protocol: bool = False,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    if atom_protocol and review_protocol:
        raise ValueError("atom_protocol and review_protocol are mutually exclusive")
    if not 0 < timeout_seconds <= 600:
        raise ValueError("timeout_seconds must be greater than 0 and at most 600")
    dataset = load_dataset(dataset_path)
    if sealed_first_run and not dataset.frozen:
        raise ValueError("a sealed first run requires a frozen dataset")
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
            "planner_protocol": (
                "v7_two_pass_atom_review_host_compilation"
                if review_protocol
                else (
                    "v6_relation_atoms_host_compilation"
                    if atom_protocol
                    else "v5_model_observation_host_decision"
                )
            ),
            "provider_calls_per_case": 2 if review_protocol else 1,
            "one_provider_call_per_case": not review_protocol,
            "corpus_role": (
                "sealed_first_run" if sealed_first_run else "opened_regression"
            ),
            "eligible_as_unseen_evidence": sealed_first_run,
            "notes": [
                (
                    "The frozen corpus is eligible as unseen evidence only for this "
                    "first cache-empty run."
                    if sealed_first_run
                    else "The selected corpus is treated as opened regression data."
                ),
                "Dry-run construction never reads DOPPEL_API_KEY or opens a network client.",
                "The model describes up to eight edges and has no execute/abstain field.",
                (
                    "A second non-authoritative model pass reviews the first atom "
                    "observation before unchanged host compilation."
                    if review_protocol
                    else (
                        "Trusted host code orders relation atoms, derives directions, "
                        "and applies the executable bound."
                        if atom_protocol
                        else "Trusted host code alone applies the executable two-hop bound."
                    )
                ),
                "No graph query is executed by this scorer.",
            ],
        }
    )
    plan["provider"]["timeout_seconds"] = timeout_seconds
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
    sealed_first_run: bool = False,
    atom_protocol: bool = False,
    review_protocol: bool = False,
) -> dict[str, Any]:
    if atom_protocol and review_protocol:
        raise ValueError("atom_protocol and review_protocol are mutually exclusive")
    report = await execute_decision_live(
        dataset=dataset,
        definitions=definitions,
        model=model,
        partitions=partitions,
        cache_dir=cache_dir,
        max_calls=max_calls,
        provider_metadata=provider_metadata,
        planner_type=(
            ReferencePersonalMemoryRelationPathPlannerV7
            if review_protocol
            else (
                ReferencePersonalMemoryRelationPathPlannerV6
                if atom_protocol
                else ReferencePersonalMemoryRelationPathPlannerV5
            )
        ),
    )
    report.update(
        {
            "runner": "doppel.relation-path-two-stage-quality.v1",
            "planner_protocol": (
                "v7_two_pass_atom_review_host_compilation"
                if review_protocol
                else (
                    "v6_relation_atoms_host_compilation"
                    if atom_protocol
                    else "v5_model_observation_host_decision"
                )
            ),
            "provider_calls_per_case": 2 if review_protocol else 1,
            "model_execution_authority": False,
            "host_executable_path_bound": 2,
            "corpus_status": {
                "role": (
                    "sealed_first_run" if sealed_first_run else "opened_regression"
                ),
                "eligible_as_unseen_evidence": sealed_first_run,
                "opened_by_this_run": sealed_first_run,
                "notes": (
                    "The frozen corpus and fresh cache were opened by this run. Any "
                    "later run is regression evidence only."
                    if sealed_first_run
                    else "The selected corpus was already open before this run."
                ),
            },
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
    parser.add_argument(
        "--sealed-first-run",
        action="store_true",
        help="Require a frozen dataset, empty cache, and new output path.",
    )
    parser.add_argument(
        "--atom-protocol",
        action="store_true",
        help="Use experimental V6 declarative relation atoms and host compilation.",
    )
    parser.add_argument(
        "--review-protocol",
        action="store_true",
        help="Use experimental V7 two-pass atom extraction and review.",
    )
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
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="Per-provider-call HTTP timeout; does not change the generation budget.",
    )
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
    if not 0 < args.timeout_seconds <= 600:
        raise ValueError("--timeout-seconds must be greater than 0 and at most 600")
    if args.atom_protocol and args.review_protocol:
        raise ValueError("--atom-protocol and --review-protocol are mutually exclusive")
    if args.sealed_first_run and (args.atom_protocol or args.review_protocol):
        raise ValueError(
            "experimental protocols have no pre-registered sealed corpus; "
            "run them as opened regression"
        )
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
        sealed_first_run=args.sealed_first_run,
        atom_protocol=args.atom_protocol,
        review_protocol=args.review_protocol,
        timeout_seconds=args.timeout_seconds,
    )
    if not args.live:
        sys.stdout.write(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
        return 0
    if args.sealed_first_run:
        _validate_sealed_first_run(
            dataset_path=args.dataset,
            cache_dir=args.cache_dir,
            cache_disabled=args.no_cache,
            output=args.output,
        )
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
        timeout_seconds=args.timeout_seconds,
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
            sealed_first_run=args.sealed_first_run,
            atom_protocol=args.atom_protocol,
            review_protocol=args.review_protocol,
        )
    finally:
        await provider.aclose()
    report["usage"] = usage.report()
    base_thresholds = {
        "min_exact_path_accuracy": args.min_exact_path_accuracy,
        "min_decision_accuracy": args.min_decision_accuracy,
        "min_reason_accuracy": args.min_reason_accuracy,
        "min_over_bound_reason_accuracy": args.min_over_bound_reason_accuracy,
        "max_wrong_execute_count": args.max_wrong_execute_count,
    }
    if args.sealed_first_run:
        for name in tuple(base_thresholds):
            registered = SEALED_THRESHOLDS[name]
            if name.startswith("min_"):
                base_thresholds[name] = max(base_thresholds[name], registered)
            else:
                base_thresholds[name] = min(base_thresholds[name], registered)
    report["quality_gate"] = _quality_gate(
        report,
        **base_thresholds,
    )
    if args.sealed_first_run:
        report["quality_gate"] = _apply_sealed_quality_gates(
            report, report["quality_gate"]
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


def _validate_sealed_first_run(
    *,
    dataset_path: Path,
    cache_dir: Path,
    cache_disabled: bool,
    output: Path | None,
) -> None:
    dataset = load_dataset(dataset_path)
    if not dataset.frozen:
        raise RuntimeError("sealed first run requires dataset.frozen=true")
    if cache_disabled:
        raise RuntimeError("sealed first run requires raw-output caching")
    if output is None:
        raise RuntimeError("sealed first run requires an explicit --output path")
    if output.exists() or Path(f"{output}.sha256").exists():
        raise RuntimeError("sealed first-run output or sidecar already exists")
    cache_entries = (
        list(cache_dir.rglob("*.json")) if cache_dir.exists() else []
    )
    if cache_entries:
        raise RuntimeError("sealed first run requires an empty dedicated cache directory")


def _apply_sealed_quality_gates(
    report: dict[str, Any], gate: dict[str, Any]
) -> dict[str, Any]:
    """Add pre-registered path-shape gates to the generic decision gates."""

    metrics = report["metrics"]
    by_category = report["by_category"]
    checks = {
        "relation_type_accuracy": (
            metrics["relation_type_accuracy"],
            SEALED_THRESHOLDS["min_relation_type_accuracy"],
        ),
        "direction_accuracy": (
            metrics["direction_accuracy"],
            SEALED_THRESHOLDS["min_direction_accuracy"],
        ),
        "path_recall": (
            metrics["path_recall"],
            SEALED_THRESHOLDS["min_path_recall"],
        ),
        "one_hop_exact_path_accuracy": (
            by_category["one_hop"]["exact_path_accuracy"],
            SEALED_THRESHOLDS["min_one_hop_exact_path_accuracy"],
        ),
        "two_hop_exact_path_accuracy": (
            by_category["two_hop"]["exact_path_accuracy"],
            SEALED_THRESHOLDS["min_two_hop_exact_path_accuracy"],
        ),
        "no_path_accuracy": (
            by_category["no_path"]["no_path_accuracy"],
            SEALED_THRESHOLDS["min_no_path_accuracy"],
        ),
    }
    failures = list(gate["failures"])
    for name, (value, threshold) in checks.items():
        if value < threshold:
            failures.append(f"{name} below sealed threshold")
    if (
        metrics["forbidden_relation_type_hits"]
        > SEALED_THRESHOLDS["max_forbidden_relation_type_hits"]
    ):
        failures.append("forbidden relation type hits exceed sealed threshold")
    if metrics["error_count"] > SEALED_THRESHOLDS["max_error_count"]:
        failures.append("error count exceeds sealed threshold")
    return {
        **gate,
        "passed": not failures,
        "thresholds": {**gate["thresholds"], **SEALED_THRESHOLDS},
        "failures": failures,
        "pre_registered": True,
    }


if __name__ == "__main__":
    raise SystemExit(main())
