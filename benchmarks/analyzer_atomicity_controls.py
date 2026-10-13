"""Prospective V9/V10 property-atomic controls; not a rescoring of V9 controls."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from benchmarks import analyzer_preservation_controls as runtime
from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_memory_expansion import save
from benchmarks.public_memory_pilot import _hash
from doppel_memory.intelligence import (
    ReferencePersonalMemoryAnalyzerV9,
    ReferencePersonalMemoryAnalyzerV10,
)

RUNNER = "doppel.analyzer-atomicity-controls.v1"
PROFILES = {
    "v9": ReferencePersonalMemoryAnalyzerV9,
    "v10": ReferencePersonalMemoryAnalyzerV10,
}
DEFAULT_CONTROLS = (
    Path(__file__).parent / "datasets/analyzer-atomicity-controls-v1.json"
)
CONTRACT = Path(__file__).resolve().parents[1] / "docs/memory-atomicity.md"


async def prepare(dataset_bytes):
    bound, requests, plan = await runtime.prepare(
        dataset_bytes,
        runner=RUNNER,
        profiles=PROFILES,
        source_files=(Path(__file__), CONTRACT),
    )
    plan.pop("plan_fingerprint")
    plan.update(
        contrast="same evidence/schema/model/gates; property-atomic/source-explicit revision instructions and identity",
        prior_preservation_gate_passed=False,
        old_task_followup_allowed=False,
        default_promotion_allowed=False,
        review="manual prospective atomicity rubrics; source/output anchors verify provenance not semantics",
    )
    plan["plan_fingerprint"] = _hash(plan)
    return bound, requests, plan


async def run(args):
    bound, _requests, plan = await prepare(args.controls.read_bytes())
    result = {
        "runner": RUNNER,
        "status": "ready",
        "plan": plan,
        "record_or_index_writes": 0,
        "publication_ready": False,
    }
    if args.live:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            raise ValueError("unchanged frozen preflight required")
        result.update(await runtime.execute(args, bound, plan, profiles=PROFILES))
    result["execution_metadata"] = execution_metadata()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controls", type=Path, default=DEFAULT_CONTROLS)
    for name in ("run-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("preserve outputs; cache-only requires live")
    result = asyncio.run(run(args))
    save(args.output, result)
    print(json.dumps({"status": result["status"], "rows": len(result.get("rows", []))}))
    return 0 if result["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
