"""One bounded observation-review experiment; immutable V1 reference, no corpus access."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmarks import evidence_rich_blind_acquire as acquire
from benchmarks import surface_review_calibration as v1
from benchmarks.evidence_rich_blind_acquire_v5 import (
    ParentCacheIntegrityError,
    ReadOnlyParentCache,
)
from benchmarks.relation_planner_quality import (
    PlannerCallBudgetExceeded,
    StructuredOutputCallBudget,
    UsageLedger,
)
from benchmarks.surface_review_controls import (
    ReviewControl,
    build_baseline_request,
    fingerprint,
)
from benchmarks.surface_review_controls import build_controls as build_v1_controls
from benchmarks.surface_review_controls_v2 import GOLD_REVISION, build_controls
from benchmarks.surface_review_grounding import (
    build_grounded_request,
    validate_grounded_review,
)
from benchmarks.surface_review_observations import (
    PROTOCOL,
    build_observed_request,
    validate_observed_review,
)
from doppel_memory.openai_compatible import (
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
    StructuredOutputProviderError,
)

RUNNER = "doppel.surface-review-calibration.v2"
REFERENCE_SHA = "b3d5e63310757d34ca99d13e05e4e0bb9e41d573a983ab2a6a242f64960ec838"


@dataclass(frozen=True)
class CalibrationExperiment:
    """Internal extension hooks; the default frozen V2 protocol remains unchanged."""

    runner: str
    protocol: str
    gold_revision: str
    controls: Callable[[], list[ReviewControl]]
    reference: Callable[[Path, Path, str], dict[str, Any]]
    review: Callable[[v1.StrictReviewCache, ReviewControl], Awaitable[dict[str, Any]]]
    calls_per_control: int
    protected_paths: tuple[Path, ...] = ()


def summarize(controls: list[Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    expected = {c.case_id for c in controls}
    keys = [r["case_id"] for r in rows]
    if len(keys) != len(set(keys)) or not set(keys).issubset(expected):
        raise ValueError("candidate result identity mismatch")
    reviewed = [r for r in rows if r["status"] == "reviewed"]
    positives = sum(c.acceptable for c in controls)
    negatives = len(controls) - positives
    detected = sum(r["score"]["defect_detected"] for r in reviewed)
    fp = sum(r["score"]["false_positive"] for r in reviewed)
    complete = len(rows) == len(controls)
    return {
        "control_count": len(controls),
        "reviewed_count": len(reviewed),
        "error_count": len(rows) - len(reviewed),
        "not_run_count": len(controls) - len(rows),
        "acceptable_control_count": positives,
        "defective_control_count": negatives,
        "false_positive_count": fp,
        "false_positive_rate": fp / positives
        if sum(r["score"]["expected_acceptable"] for r in reviewed) == positives
        else None,
        "defects_detected": detected,
        "defects_not_demonstrated": negatives - detected,
        "defect_detection_rate": detected / negatives if negatives else None,
        "unexpected_issue_count": sum(
            r["score"]["unexpected_issue_count"] for r in reviewed
        ),
        "correct_count": sum(r["score"]["correct"] for r in reviewed),
        "gate": {
            "ok": complete
            and len(reviewed) == len(controls)
            and all(r["score"]["correct"] for r in reviewed),
            "complete": complete,
            "rule": f"all {len(controls)} development controls must have valid observations and correct judgments with no unexpected flags",
            "blind_corpus_acceptance_granted": False,
            "publication_ready": False,
        },
    }


def load_reference(path: Path, cache: Path, expected_sha: str) -> dict[str, Any]:
    """Replay every V1 raw response against its original scorer; never rewrite it."""
    if acquire._sha256(path) != expected_sha:
        raise ValueError("V1 reference report checksum mismatch")
    report = json.loads(path.read_text("utf-8"))
    manifest_path, state_path = (
        cache / "calibration-manifest.json",
        cache / "calibration-state.json",
    )
    binding = json.loads(manifest_path.read_text("utf-8"))
    state = json.loads(state_path.read_text("utf-8"))
    originals = build_v1_controls()
    if (
        report["runner"] != v1.RUNNER
        or report["controls_fingerprint"] != fingerprint(originals)
        or report["status"] != "complete"
        or report["blind_corpus_read"]
        or report["retrieval_enabled"]
    ):
        raise ValueError("V1 reference identity mismatch")
    if (
        report["binding_sha256"] != acquire._fingerprint(binding)
        or state["binding_sha256"] != report["binding_sha256"]
        or state["provider_calls"] != report["provider_calls_cumulative"]
        or state["usage"] != report["usage_cumulative"]
    ):
        raise ValueError("V1 reference state mismatch")
    for key, value in binding.items():
        if key == "profiles":
            if value != list(v1.PROFILES) or set(report["profiles"]) != set(value):
                raise ValueError("V1 reference profile mismatch")
        elif key != "provider" and report.get(key) != value:
            raise ValueError("V1 reference manifest mismatch")
    parent = ReadOnlyParentCache(cache, binding["provider"])
    rows = report["cases"]
    identities = {(r["profile"], r["case_id"]): r for r in rows}
    expected = {(p, c.case_id) for p in v1.PROFILES for c in originals}
    if len(rows) != len(identities) or set(identities) != expected:
        raise ValueError("V1 reference coverage mismatch")
    hashes = {}
    for profile in v1.PROFILES:
        for control in originals:
            request = build_baseline_request(control)
            if profile == "grounded_v1":
                request = build_grounded_request(request)
            raw = parent.get(request)
            if raw is None:
                raise ValueError("V1 reference raw response missing")
            review = (
                validate_grounded_review(request, raw)
                if profile == "grounded_v1"
                else v1.validate_baseline(control, raw)
            )
            row = identities[(profile, control.case_id)]
            if row["status"] != "reviewed" or row["review"] != review.model_dump(
                mode="json"
            ):
                raise ValueError("V1 reference normalized response mismatch")
            if row["score"] != v1.score_review(
                control, [i.model_dump(mode="json") for i in review.issues]
            ):
                raise ValueError("V1 reference original score mismatch")
            file = parent._path(request)
            hashes[str(file.relative_to(cache))] = acquire._sha256(file)
    summary = v1.summarize(originals, rows)
    if report["profiles"] != summary["profiles"] or report["gate"] != summary["gate"]:
        raise ValueError("V1 reference summary mismatch")
    # Explicitly re-score the SAME opened responses under V2 taxonomy, not a new run.
    revised = {c.case_id: c for c in build_controls()[:24]}
    rescored = []
    for row in rows:
        rescored.append(
            {
                **row,
                "score": v1.score_review(
                    revised[row["case_id"]], row["review"]["issues"]
                ),
            }
        )
    return {
        "report_sha256": expected_sha,
        "manifest_sha256": acquire._sha256(manifest_path),
        "state_sha256": acquire._sha256(state_path),
        "raw_responses_sha256": acquire._fingerprint(hashes),
        "raw_response_count": len(hashes),
        "configuration": binding,
        "original_v1_profiles": summary["profiles"],
        "original_v1_gate": summary["gate"],
        "opened_reference_rescored_v2_taxonomy": v1.summarize(
            list(revised.values()), rescored
        )["profiles"],
        "original_usage_not_charged_to_v2": report["usage_cumulative"],
        "reference_only": True,
    }


def parser() -> argparse.ArgumentParser:
    result = v1.parser()
    result.description = __doc__
    result.set_defaults(
        cache_dir=v1.DATA / "surface-review-calibration-v2-cache",
        progress_output=v1.DATA / "surface-review-calibration-v2-progress.json",
        output=v1.DATA / "surface-review-calibration-v2.json",
    )
    result.add_argument(
        "--reference-report",
        type=Path,
        default=v1.DATA / "surface-review-calibration-v1.json",
    )
    result.add_argument(
        "--reference-cache",
        type=Path,
        default=v1.DATA / "surface-review-calibration-v1-cache",
    )
    result.add_argument("--reference-sha256", default=REFERENCE_SHA)
    return result


async def run(
    args: argparse.Namespace, *, experiment: CalibrationExperiment | None = None
) -> int:
    if args.max_new_calls < 0:
        raise ValueError("max-new-calls must not be negative")
    controls = build_controls() if experiment is None else experiment.controls()
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
        "runner": RUNNER,
        "mode": "live" if args.live else "dry_run",
        "controls_fingerprint": fingerprint(controls),
        "gold_revision": GOLD_REVISION,
        "review_protocol": PROTOCOL,
        "control_count": len(controls),
        "opened_v1_control_count": 24,
        "additional_development_control_count": 12,
        "maximum_uncached_calls": len(controls),
        "maximum_new_calls_this_invocation": args.max_new_calls,
        "model": config.model,
        "base_url": config.base_url,
        "schema_mode": config.schema_mode,
        "max_completion_tokens": config.max_completion_tokens,
        "temperature": config.temperature,
        "thinking": config.thinking,
        "provider_retries": 0,
        "implementation_commit": acquire._git_commit_hash(),
        "reference_sha256": args.reference_sha256,
        "development_controls": True,
        "blind_corpus_read": False,
        "retrieval_enabled": False,
        "blind_corpus_acceptance_granted": False,
    }
    if experiment is not None:
        plan.update(
            runner=experiment.runner,
            review_protocol=experiment.protocol,
            gold_revision=experiment.gold_revision,
            maximum_uncached_calls=len(controls) * experiment.calls_per_control,
            opened_v2_control_count=len(controls),
            additional_development_control_count=0,
        )
        del plan["opened_v1_control_count"]
    if not args.live:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if args.output.exists():
        raise ValueError(
            "completed calibration output exists; preserve the first result"
        )
    # Reject aliasing before binding or writing any experiment files.
    protected = [args.reference_report.resolve(), args.reference_cache.resolve()]
    if experiment is not None:
        protected.extend(p.resolve() for p in experiment.protected_paths)
    for target in (args.output, args.progress_output, args.cache_dir):
        resolved = target.resolve()
        if any(
            resolved == p or resolved.is_relative_to(p) or p.is_relative_to(resolved)
            for p in protected
        ):
            raise ValueError("V2 paths overlap immutable V1 reference")
    if args.output.resolve() == args.progress_output.resolve() or any(
        p.resolve().is_relative_to(args.cache_dir.resolve())
        for p in (args.output, args.progress_output)
    ):
        raise ValueError("V2 result paths overlap cache/progress")
    reference_loader = load_reference if experiment is None else experiment.reference
    reference = reference_loader(
        args.reference_report, args.reference_cache, args.reference_sha256
    )
    for k in (
        "model",
        "base_url",
        "schema_mode",
        "max_completion_tokens",
        "temperature",
        "thinking",
    ):
        if plan[k] != reference["configuration"][k]:
            raise ValueError("V2 model configuration differs from V1 reference")
    key = os.environ.get("DOPPEL_API_KEY", "").strip()
    if not key and args.max_new_calls:
        raise RuntimeError("DOPPEL_API_KEY is required for new provider calls")
    usage = UsageLedger()
    provider = OpenAICompatibleStructuredOutputModel(
        config, api_key=key or "cache-only-no-network", usage_observer=usage.observe
    )
    budget = StructuredOutputCallBudget(provider, max_calls=args.max_new_calls)
    cached = v1.StrictReviewCache(budget, args.cache_dir)
    binding = {
        k: v
        for k, v in plan.items()
        if k not in ("mode", "maximum_new_calls_this_invocation")
    }
    binding.update(
        reference=reference, provider={"name": cached.name, "version": cached.version}
    )
    state_path = args.cache_dir / "calibration-state.json"
    rows: list[dict[str, Any]] = []
    stopped: dict[str, Any] = {}
    try:
        acquire._bind_manifest(args.cache_dir / "calibration-manifest.json", binding)
        prior = acquire._load_state(state_path)
        if prior and prior.get("binding_sha256") != acquire._fingerprint(binding):
            raise ValueError("calibration state binding mismatch")
        for control in controls:
            row: dict[str, Any] = {
                "case_id": control.case_id,
                "family": control.family,
                "pair_id": control.pair_id,
                "cohort": "opened_v2"
                if experiment is not None
                else "opened_v1"
                if control.case_id in {c.case_id for c in build_v1_controls()}
                else "additional_development",
            }
            try:
                if experiment is None:
                    request = build_observed_request(build_baseline_request(control))
                    raw = await cached.generate(request)
                    review, effective_issues = validate_observed_review(request, raw)
                    result = {
                        "review": review.model_dump(mode="json"),
                        "effective_issues": effective_issues,
                    }
                else:
                    result = await experiment.review(cached, control)
                    effective_issues = result["effective_issues"]
            except PlannerCallBudgetExceeded:
                stopped = {"reason": "budget_exhausted", "case_id": control.case_id}
                break
            except StructuredOutputProviderError as exc:
                stopped = {
                    "reason": "StructuredOutputProviderError",
                    "code": exc.code,
                    "http_status": exc.status_code,
                    "retryable": exc.retryable,
                    "case_id": control.case_id,
                }
                break
            except (ValueError, ParentCacheIntegrityError) as exc:
                row.update(status="error", error=type(exc).__name__)
            else:
                row.update(
                    status="reviewed",
                    **result,
                    score=v1.score_review(control, effective_issues),
                )
            rows.append(row)
            label = "observations_v2" if experiment is None else "separated_v3"
            print(f"{label} {control.case_id}: {row['status']}", flush=True)
    finally:
        await provider.aclose()
    summary = summarize(controls, rows)
    state = {
        "binding_sha256": acquire._fingerprint(binding),
        "provider_calls": int(prior.get("provider_calls", 0)) + budget.calls,
        "usage": acquire._merge_usage(prior.get("usage", {}), usage.report()),
    }
    acquire._write_json(state_path, state)
    cohorts = (
        {
            name: summarize(
                controls[start:end], [r for r in rows if r["cohort"] == name]
            )
            for name, start, end in (
                ("opened_v1", 0, 24),
                ("additional_development", 24, 36),
            )
        }
        if experiment is None
        else {"opened_v2": summarize(controls, rows)}
    )
    report = {
        **plan,
        "status": "complete" if summary["gate"]["complete"] else "incomplete",
        **summary,
        "cohorts": cohorts,
        "reference": reference,
        "cases": rows,
        "binding_sha256": state["binding_sha256"],
        "usage_cumulative": state["usage"],
        "provider_calls_cumulative": state["provider_calls"],
        "last_invocation": {
            "provider_calls": budget.calls,
            "cache_hits": cached.hits,
            "cache_misses": cached.misses,
            "invalid_cache_entries": cached.invalid_entries_ignored,
        },
        "stopped": stopped,
        "limitations": [
            "36 development controls, not independent heldout quality",
            "V1 baseline is an immutable opened reference; extensions have no new baseline",
            "quotes and host comparisons do not prove model role interpretations correct",
            "calibration does not accept a corpus or measure Doppel retrieval",
        ],
    }
    if experiment is not None:
        report["limitations"] = [
            "all 36 controls are opened development controls, not independent heldout quality",
            "first-pass literal interpretations remain fallible even without public-contract hints",
            "the reference is an immutable V2 run; taxonomy rescoring is not new evidence",
            "a calibration pass grants no corpus acceptance or Doppel retrieval quality claim",
        ]
        report["manual_review_queue"] = [
            {
                "case_id": r["case_id"],
                "status": r["status"],
                "reason": r.get("error", "incorrect_control_judgment"),
            }
            for r in rows
            if r["status"] != "reviewed" or not r["score"]["correct"]
        ]
    acquire._write_json(args.progress_output, report)
    if report["status"] == "complete":
        acquire._write_json(args.output, report)
        print(
            f"output: {args.output.resolve()}\nsha256: {acquire._sha256(args.output)}"
        )
    print(
        json.dumps(
            {"status": report["status"], **summary, "stopped": stopped},
            ensure_ascii=False,
        )
    )
    return 0 if summary["gate"]["ok"] else 1 if report["status"] == "complete" else 2


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
