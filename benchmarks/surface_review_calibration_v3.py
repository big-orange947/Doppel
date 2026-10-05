"""Bounded two-stage reviewer calibration; no blind corpus or retrieval access."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from benchmarks import surface_review_calibration as v1
from benchmarks import surface_review_calibration_v2 as v2
from benchmarks.evidence_rich_blind_acquire_v5 import ReadOnlyParentCache
from benchmarks.surface_review_controls import build_baseline_request, fingerprint
from benchmarks.surface_review_controls_v2 import build_controls as build_v2_controls
from benchmarks.surface_review_controls_v3 import GOLD_REVISION, build_controls
from benchmarks.surface_review_observations import (
    build_observed_request,
    validate_observed_review,
)
from benchmarks.surface_review_separated import PROTOCOL, review_control

RUNNER = "doppel.surface-review-calibration.v3"
REFERENCE_SHA = "bd85b93a76208f1ff865b30b9ada75078f52dea73009c5c4f35070a0e0788130"


def load_reference(path: Path, cache: Path, expected_sha: str) -> dict[str, Any]:
    if v2.acquire._sha256(path) != expected_sha:
        raise ValueError("V2 reference report checksum mismatch")
    report = json.loads(path.read_text("utf-8"))
    manifest_path, state_path = (
        cache / "calibration-manifest.json",
        cache / "calibration-state.json",
    )
    binding = json.loads(manifest_path.read_text("utf-8"))
    state = json.loads(state_path.read_text("utf-8"))
    controls = build_v2_controls()
    if (
        report["runner"] != v2.RUNNER
        or report["controls_fingerprint"] != fingerprint(controls)
        or report["status"] != "complete"
        or report["blind_corpus_read"]
        or report["retrieval_enabled"]
    ):
        raise ValueError("V2 reference identity mismatch")
    if (
        report["binding_sha256"] != state["binding_sha256"]
        or report["binding_sha256"] != v2.acquire._fingerprint(binding)
        or state["provider_calls"] != report["provider_calls_cumulative"]
        or state["usage"] != report["usage_cumulative"]
    ):
        raise ValueError("V2 reference state mismatch")
    for key, value in binding.items():
        if key != "provider" and report.get(key) != value:
            raise ValueError("V2 reference manifest mismatch")
    rows = report["cases"]
    identities = {r["case_id"]: r for r in rows}
    if len(rows) != len(identities) or set(identities) != {c.case_id for c in controls}:
        raise ValueError("V2 reference coverage mismatch")
    parent = ReadOnlyParentCache(cache, binding["provider"])
    hashes = {}
    for control in controls:
        request = build_observed_request(build_baseline_request(control))
        raw = parent.get(request)
        if raw is None:
            raise ValueError("V2 reference raw response missing")
        review, effective = validate_observed_review(request, raw)
        row = identities[control.case_id]
        if (
            row["status"] != "reviewed"
            or row["review"] != review.model_dump(mode="json")
            or row["effective_issues"] != effective
            or row["score"] != v1.score_review(control, effective)
        ):
            raise ValueError("V2 reference original response/score mismatch")
        file = parent._path(request)
        hashes[str(file.relative_to(cache))] = v2.acquire._sha256(file)
    summary = v2.summarize(controls, rows)
    if any(report[key] != value for key, value in summary.items()):
        raise ValueError("V2 reference summary mismatch")
    revised = {c.case_id: c for c in build_controls()}
    rescored = [
        {**r, "score": v1.score_review(revised[r["case_id"]], r["effective_issues"])}
        for r in rows
    ]
    return {
        "report_sha256": expected_sha,
        "manifest_sha256": v2.acquire._sha256(manifest_path),
        "state_sha256": v2.acquire._sha256(state_path),
        "raw_responses_sha256": v2.acquire._fingerprint(hashes),
        "raw_response_count": len(hashes),
        "configuration": binding,
        "original_v2_summary": summary,
        "opened_reference_rescored_v3_taxonomy": v2.summarize(
            build_controls(), rescored
        ),
        "original_usage_not_charged_to_v3": report["usage_cumulative"],
        "reference_only": True,
    }


def parser() -> argparse.ArgumentParser:
    result = v2.parser()
    result.description = __doc__
    result.set_defaults(
        cache_dir=v1.DATA / "surface-review-calibration-v3-cache",
        progress_output=v1.DATA / "surface-review-calibration-v3-progress.json",
        output=v1.DATA / "surface-review-calibration-v3.json",
        reference_report=v1.DATA / "surface-review-calibration-v2.json",
        reference_cache=v1.DATA / "surface-review-calibration-v2-cache",
        reference_sha256=REFERENCE_SHA,
    )
    return result


async def run(args: argparse.Namespace) -> int:
    experiment = v2.CalibrationExperiment(
        runner=RUNNER,
        protocol=PROTOCOL,
        gold_revision=GOLD_REVISION,
        controls=build_controls,
        reference=load_reference,
        review=review_control,
        calls_per_control=2,
        protected_paths=(
            v1.DATA / "surface-review-calibration-v1.json",
            v1.DATA / "surface-review-calibration-v1-cache",
        ),
    )
    return await v2.run(args, experiment=experiment)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
