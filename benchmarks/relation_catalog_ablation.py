"""Fresh, bounded labels-only vs definitions comparison; dry-run by default."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import TypeAdapter

from benchmarks.personal_retrieval_ablation import (
    _git_commit_hash,
    _source_tree_sha256,
    load_ablation_dataset,
)
from benchmarks.planner_semantic_review import PlannerSemanticReview
from benchmarks.relation_planner_quality import (
    DEFAULT_DATASET,
    _query_request,
)
from benchmarks.relation_planner_quality import (
    _async_main as _run_arm,
)
from benchmarks.relation_planner_quality import (
    _parser as _arm_parser,
)
from doppel_memory import RelationTypeDefinition

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "benchmarks/catalogs/personal-relations-v1.json"
REVIEW = ROOT / "benchmarks/datasets/relation-planner-semantic-review-zh-v1.json"
ARMS = ("labels_only", "definitions")


def _input_identity() -> dict[str, str]:
    return {
        "commit": _git_commit_hash(),
        "source_sha256": _source_tree_sha256(),
        **{
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in (
                ("dataset_sha256", DEFAULT_DATASET),
                ("catalog_sha256", CATALOG),
                ("review_sha256", REVIEW),
                (
                    "planner_runner_sha256",
                    Path(__file__).with_name("relation_planner_quality.py"),
                ),
                ("paired_runner_sha256", Path(__file__)),
            )
        },
    }


def _plan() -> dict[str, Any]:
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    definitions = TypeAdapter(list[RelationTypeDefinition]).validate_json(
        CATALOG.read_bytes()
    )
    _query_request(dataset, dataset.queries[0], definitions)
    PlannerSemanticReview.model_validate_json(REVIEW.read_bytes()).validate_dataset(
        dataset
    )
    count = sum(
        query.partition != "deferred_cross_subject" for query in dataset.queries
    )
    if count > 65:
        raise ValueError("dataset exceeds this experiment's 130-call total cap")
    return {
        "runner": "doppel.relation-catalog-ablation.v1",
        "publication_ready": False,
        "arms": list(ARMS),
        "query_count_per_arm": count,
        "max_calls_per_arm": count,
        "max_total_calls": count * 2,
        "cache_enabled": False,
        "provider_retries": 0,
        "settings": {
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
            "schema_mode": "json_object",
            "max_completion_tokens": 768,
            "max_tokens_parameter": "max_tokens",
            "thinking": "disabled",
            "temperature": 0,
        },
        "input_identity": _input_identity(),
        "notes": [
            "Existing questions and semantic review are exploratory, not unseen held-out evidence.",
            "No cached drafts or retries; preserve first-pass invalid responses.",
            "Sequential labels-only then definitions; not randomized or repeated trials.",
            "Quality failure exits do not prevent the other arm; authentication failure stops calls.",
        ],
    }


def _arm_args(plan: dict[str, Any], arm: str, output: Path) -> argparse.Namespace:
    argv = [
        "--dataset",
        str(DEFAULT_DATASET),
        "--planner",
        "reference",
        "--no-cache",
        "--semantic-review",
        str(REVIEW),
        "--output",
        str(output),
        "--max-calls",
        str(plan["max_calls_per_arm"]),
        "--max-structural-failures",
        "0",
        "--max-relation-type-failures",
        "0",
    ]
    for name, value in plan["settings"].items():
        if name != "temperature":  # Existing runner always fixes this to zero.
            argv.extend(["--" + name.replace("_", "-"), str(value)])
    if arm == "definitions":
        argv.extend(["--relation-catalog", str(CATALOG)])
    return _arm_parser().parse_args(argv)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as target:
        target.write(data)
    with path.with_suffix(path.suffix + ".sha256").open(
        "x", encoding="utf-8"
    ) as sidecar:
        sidecar.write(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")


def _comparison(reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if set(reports) != set(ARMS):
        return {"available": False, "reason": "both arms are required"}
    before, after = (reports[arm] for arm in ARMS)
    if before["dataset"]["fingerprint"] != after["dataset"]["fingerprint"]:
        raise ValueError("paired dataset mismatch")
    if (
        before["planner"] != after["planner"]
        or before["scoring_version"] != after["scoring_version"]
    ):
        raise ValueError("paired planner/scoring mismatch")
    before_cases = {case["query_id"]: case for case in before["cases"]}
    after_cases = {case["query_id"]: case for case in after["cases"]}
    if (
        len(before_cases) != len(before["cases"])
        or len(after_cases) != len(after["cases"])
        or before_cases.keys() != after_cases.keys()
    ):
        raise ValueError("paired case identity mismatch")
    transitions = []
    for query_id, first in before_cases.items():
        second = after_cases[query_id]
        if first["request_fingerprint"] == second["request_fingerprint"]:
            raise ValueError("definitions arm did not change planner input")
        if (
            first["relation_type_ok"] != second["relation_type_ok"]
            or first["status"] != second["status"]
        ):
            transitions.append(
                {
                    "query_id": query_id,
                    "before_status": first["status"],
                    "after_status": second["status"],
                    "before_type_exact": first["relation_type_ok"],
                    "after_type_exact": second["relation_type_ok"],
                }
            )
    return {
        "available": True,
        "provider_complete": all(
            report["execution"]["complete"] for report in reports.values()
        ),
        "metric_deltas_definitions_minus_labels": {
            key: round(after["metrics"][key] - value, 4)
            for key, value in before["metrics"].items()
            if isinstance(value, (int, float))
            and isinstance(after["metrics"].get(key), (int, float))
        },
        "case_transitions": transitions,
    }


async def run_pair(output_root: Path) -> tuple[int, Path]:
    if not os.environ.get("DOPPEL_API_KEY", "").strip():
        raise RuntimeError("DOPPEL_API_KEY is required for a live pair")
    plan = _plan()
    run_dir = output_root / (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    _write_json(run_dir / "plan.json", plan)
    reports: dict[str, dict[str, Any]] = {}
    summary: dict[str, Any] = {"runner": plan["runner"], "arms": {}, "stop_reason": ""}
    for arm in ARMS:
        if _input_identity() != plan["input_identity"]:
            summary["stop_reason"] = "inputs_changed"
            break
        output = run_dir / f"{arm}.json"
        print(
            f"Running {arm}: {plan['max_calls_per_arm']} calls maximum, no cached drafts",
            flush=True,
        )
        try:
            code = await _run_arm(_arm_args(plan, arm, output))
            report = json.loads(output.read_bytes())
            if _input_identity() != plan["input_identity"]:
                summary["stop_reason"] = "inputs_changed"
                break
            if report["cache"]["enabled"] or report["cache"]["hits"]:
                raise ValueError("fresh comparison cannot use cached drafts")
            if report["relation_catalog"]["mode"] != arm:
                raise ValueError("incorrect catalog arm")
            reports[arm] = report
            summary["arms"][arm] = {
                "exit_code": code,
                "report": output.name,
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "metrics": report["metrics"],
                "usage": report["usage"],
                "budget": report["budget"],
                "output_diagnostics": report["output_diagnostics"],
                "relation_assessment_counts": report["semantic_review"][
                    "relation_assessment_counts"
                ],
            }
            if report["execution"]["stop_reason"] == "authentication_error":
                summary["stop_reason"] = "authentication_error"
                break
            if report["metrics"]["valid_case_count"] == 0:
                summary["stop_reason"] = "no_valid_drafts"
                break
        except Exception:  # noqa: BLE001 - never dump provider text or credentials
            summary["stop_reason"] = "arm_execution_error"
            break
    try:
        summary["comparison"] = _comparison(reports)
    except ValueError:
        summary["stop_reason"] = "comparison_identity_mismatch"
        summary["comparison"] = {"available": False}
    summary["completed"] = len(reports) == 2 and not summary["stop_reason"]
    summary["quality_gate_passed"] = summary["completed"] and all(
        arm["exit_code"] == 0 for arm in summary["arms"].values()
    )
    _write_json(run_dir / "comparison.json", summary)
    print(f"Reports: {run_dir.resolve()}", flush=True)
    return (0 if summary["quality_gate_passed"] else 1), run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="enable up to 130 paid calls"
    )
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "data/doppel/catalog-ablation"
    )
    args = parser.parse_args(argv)
    if not args.live:
        print(json.dumps({"mode": "dry_run", **_plan()}, ensure_ascii=False, indent=2))
        return 0
    previous_key = os.environ.get("DOPPEL_API_KEY")
    try:
        if not (previous_key or "").strip():
            if not sys.stdin.isatty():
                raise RuntimeError(
                    "Set DOPPEL_API_KEY or run interactively for hidden key entry"
                )
            key = getpass.getpass("DeepSeek API key (hidden, process only): ").strip()
            if not key:
                raise RuntimeError("API key was empty; no calls made")
            os.environ["DOPPEL_API_KEY"] = key
            del key
        return asyncio.run(run_pair(args.output_root))[0]
    finally:
        if previous_key is None:
            os.environ.pop("DOPPEL_API_KEY", None)
        else:
            os.environ["DOPPEL_API_KEY"] = previous_key


if __name__ == "__main__":
    raise SystemExit(main())
