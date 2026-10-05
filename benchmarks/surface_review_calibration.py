"""Bounded baseline/grounded reviewer calibration, not blind-corpus acceptance."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from benchmarks import evidence_rich_blind_acquire as acquire
from benchmarks.evidence_rich_blind_acquire_v5 import (
    ParentCacheIntegrityError,
    ReadOnlyParentCache,
)
from benchmarks.evidence_rich_blind_authoring import OwnerSurfaceReview
from benchmarks.relation_planner_quality import (
    CachedStructuredOutputModel,
    PlannerCallBudgetExceeded,
    StructuredOutputCallBudget,
    UsageLedger,
)
from benchmarks.surface_review_controls import (
    ReviewControl,
    build_baseline_request,
    build_controls,
    fingerprint,
)
from benchmarks.surface_review_grounding import (
    build_grounded_request,
    validate_grounded_review,
)
from doppel_memory.openai_compatible import (
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
    StructuredOutputProviderError,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/doppel"
RUNNER = "doppel.surface-review-calibration.v1"
PROFILES = ("baseline_v3", "grounded_v1")


class StrictReviewCache(CachedStructuredOutputModel):
    """A corrupt existing response is an error, never an implicit paid replacement."""

    async def generate(self, request: Any) -> Any:
        path = self._cache_path(request)
        if path is not None and path.is_file():
            assert self._cache_dir is not None
            parent = ReadOnlyParentCache(
                self._cache_dir, {"name": self.name, "version": self.version}
            )
            try:
                raw = parent.get(request)
            except ParentCacheIntegrityError:
                self.invalid_entries_ignored += 1
                raise
            self.hits += 1
            return raw
        return await super().generate(request)


def validate_baseline(control: ReviewControl, raw: Any) -> OwnerSurfaceReview:
    review = OwnerSurfaceReview.model_validate(raw)
    expected = {
        x["surface_key"]
        for k in ("entities", "memories", "queries")
        for x in control.reviewer_input[k]
    }
    if set(review.reviewed_surface_keys) != expected:
        raise ValueError("baseline review coverage mismatch")
    identities = [(i.surface_key, i.issue_code) for i in review.issues]
    if len(identities) != len(set(identities)):
        raise ValueError("baseline review duplicate issue")
    if not {i.surface_key for i in review.issues}.issubset(expected):
        raise ValueError("baseline review unknown issue surface")
    return review


def score_review(
    control: ReviewControl, issues: list[dict[str, Any]]
) -> dict[str, Any]:
    matched = [
        i
        for i in issues
        if i["surface_key"] in control.allowed_issue_keys
        and i["issue_code"] in control.allowed_issue_codes
    ]
    extra = len(issues) - len(matched)
    return {
        "expected_acceptable": control.acceptable,
        "false_positive": control.acceptable and bool(issues),
        "defect_detected": not control.acceptable and bool(matched),
        "missed_defect": not control.acceptable and not matched,
        "unexpected_issue_count": len(issues) if control.acceptable else extra,
        "correct": not issues if control.acceptable else bool(matched) and not extra,
    }


def summarize(
    controls: list[ReviewControl], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    expected = {(p, c.case_id) for p in PROFILES for c in controls}
    identities = [(r["profile"], r["case_id"]) for r in rows]
    if len(set(identities)) != len(identities) or not set(identities).issubset(
        expected
    ):
        raise ValueError("calibration result identity mismatch")
    positives = sum(c.acceptable for c in controls)
    negatives = len(controls) - positives
    summaries = {}
    for profile in PROFILES:
        selected = [r for r in rows if r["profile"] == profile]
        ok = [r for r in selected if r["status"] == "reviewed"]
        fp = sum(r["score"]["false_positive"] for r in ok)
        detected = sum(r["score"]["defect_detected"] for r in ok)
        reviewed_positives = sum(r["score"]["expected_acceptable"] for r in ok)
        summaries[profile] = {
            "control_count": len(controls),
            "reviewed_count": len(ok),
            "error_count": sum(r["status"] == "error" for r in selected),
            "not_run_count": len(controls) - len(selected),
            "acceptable_control_count": positives,
            "defective_control_count": negatives,
            "false_positive_count": fp,
            "acceptable_controls_reviewed": reviewed_positives,
            "false_positive_rate": fp / positives
            if positives and reviewed_positives == positives
            else None,
            "defects_detected": detected,
            # Errors/unrun controls are never counted as successful defect detection.
            "defects_not_demonstrated": negatives - detected,
            "defect_detection_rate": detected / negatives if negatives else None,
            "unexpected_issue_count": sum(
                r["score"]["unexpected_issue_count"] for r in ok
            ),
            "correct_count": sum(r["score"]["correct"] for r in ok),
        }
    candidate = summaries["grounded_v1"]
    complete = all(s["not_run_count"] == 0 for s in summaries.values())
    passed = (
        complete
        and all(s["reviewed_count"] == len(controls) for s in summaries.values())
        and candidate["reviewed_count"] == len(controls)
        and candidate["correct_count"] == len(controls)
    )
    return {
        "profiles": summaries,
        "gate": {
            "ok": passed,
            "complete": complete,
            "rule": "both profiles must return valid reviews; candidate must correctly review every control with zero unexpected flags",
            "blind_corpus_acceptance_granted": False,
            "publication_ready": False,
        },
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--live", action="store_true")
    result.add_argument("--max-new-calls", type=int, default=0)
    result.add_argument(
        "--cache-dir", type=Path, default=DATA / "surface-review-calibration-v1-cache"
    )
    result.add_argument(
        "--progress-output",
        type=Path,
        default=DATA / "surface-review-calibration-v1-progress.json",
    )
    result.add_argument(
        "--output", type=Path, default=DATA / "surface-review-calibration-v1.json"
    )
    result.add_argument(
        "--model", default=os.environ.get("DOPPEL_MODEL", "deepseek-v4-flash")
    )
    result.add_argument(
        "--base-url",
        default=os.environ.get("DOPPEL_OPENAI_BASE_URL", "https://api.deepseek.com"),
    )
    result.add_argument(
        "--schema-mode", choices=("json_object", "json_schema"), default="json_object"
    )
    result.add_argument("--max-completion-tokens", type=int, default=1536)
    result.add_argument("--timeout-seconds", type=float, default=120)
    return result


async def run(args: argparse.Namespace) -> int:
    if args.max_new_calls < 0:
        raise ValueError("max-new-calls must not be negative")
    controls = build_controls()
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
        "control_count": len(controls),
        "profiles": list(PROFILES),
        "maximum_uncached_calls": len(controls) * len(PROFILES),
        "maximum_new_calls_this_invocation": args.max_new_calls,
        "model": config.model,
        "base_url": config.base_url,
        "schema_mode": config.schema_mode,
        "max_completion_tokens": config.max_completion_tokens,
        "temperature": config.temperature,
        "thinking": config.thinking,
        "provider_retries": 0,
        "implementation_commit": acquire._git_commit_hash(),
        "development_controls": True,
        "blind_corpus_read": False,
        "retrieval_enabled": False,
        "blind_corpus_acceptance_granted": False,
    }
    if not args.live:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if args.output.exists():
        raise ValueError(
            "completed calibration output exists; preserve the first result"
        )
    key = os.environ.get("DOPPEL_API_KEY", "").strip()
    if not key and args.max_new_calls:
        raise RuntimeError("DOPPEL_API_KEY is required for new provider calls")
    usage = UsageLedger()
    provider = OpenAICompatibleStructuredOutputModel(
        config, api_key=key or "cache-only-no-network", usage_observer=usage.observe
    )
    budget = StructuredOutputCallBudget(provider, max_calls=args.max_new_calls)
    cached = StrictReviewCache(budget, args.cache_dir)
    binding = {
        k: v
        for k, v in plan.items()
        if k not in ("mode", "maximum_new_calls_this_invocation")
    }
    binding["provider"] = {"name": cached.name, "version": cached.version}
    state_path = args.cache_dir / "calibration-state.json"
    try:
        acquire._bind_manifest(args.cache_dir / "calibration-manifest.json", binding)
        prior = acquire._load_state(state_path)
        if prior and prior.get("binding_sha256") != acquire._fingerprint(binding):
            raise ValueError("calibration state binding mismatch")
        rows = []
        stopped: dict[str, Any] = {}
        for profile in PROFILES:
            for control in controls:
                request = build_baseline_request(control)
                if profile == "grounded_v1":
                    request = build_grounded_request(request)
                row: dict[str, Any] = {
                    "profile": profile,
                    "case_id": control.case_id,
                    "family": control.family,
                    "pair_id": control.pair_id,
                }
                try:
                    raw = await cached.generate(request)
                    review = (
                        validate_grounded_review(request, raw)
                        if profile == "grounded_v1"
                        else validate_baseline(control, raw)
                    )
                except PlannerCallBudgetExceeded:
                    stopped = {
                        "reason": "budget_exhausted",
                        "profile": profile,
                        "case_id": control.case_id,
                    }
                    break
                except StructuredOutputProviderError as exc:
                    stopped = {
                        "reason": "StructuredOutputProviderError",
                        "code": exc.code,
                        "http_status": exc.status_code,
                        "retryable": exc.retryable,
                        "profile": profile,
                        "case_id": control.case_id,
                    }
                    break
                except (ValueError, ParentCacheIntegrityError) as exc:
                    row.update(status="error", error=type(exc).__name__)
                else:
                    issues = [i.model_dump(mode="json") for i in review.issues]
                    row.update(
                        status="reviewed",
                        review=review.model_dump(mode="json"),
                        score=score_review(control, issues),
                    )
                rows.append(row)
                print(f"{profile} {control.case_id}: {row['status']}", flush=True)
            if stopped:
                break
    finally:
        await provider.aclose()
    summary = summarize(controls, rows)
    state = {
        "binding_sha256": acquire._fingerprint(binding),
        "provider_calls": int(prior.get("provider_calls", 0)) + budget.calls,
        "usage": acquire._merge_usage(prior.get("usage", {}), usage.report()),
    }
    acquire._write_json(state_path, state)
    report = {
        **plan,
        "status": "complete" if summary["gate"]["complete"] else "incomplete",
        "binding_sha256": state["binding_sha256"],
        **summary,
        "usage_cumulative": state["usage"],
        "provider_calls_cumulative": state["provider_calls"],
        "last_invocation": {
            "provider_calls": budget.calls,
            "cache_hits": cached.hits,
            "cache_misses": cached.misses,
            "invalid_cache_entries": cached.invalid_entries_ignored,
        },
        "stopped": stopped,
        "cases": rows,
        "limitations": [
            "24 hand-authored development controls, not a heldout quality test",
            "grounded citations prove source location, not semantic correctness",
            "a calibration pass grants no acceptance to any blind corpus",
        ],
    }
    acquire._write_json(args.progress_output, report)
    if report["status"] == "complete":
        acquire._write_json(args.output, report)
        print(f"output: {args.output.resolve()}")
        print(f"sha256: {acquire._sha256(args.output)}")
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
