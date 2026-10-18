"""Remaining two opened cases: up-to-20 contract, at most eight new calls."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_memory_expansion import local_diagnostic_dsn, save
from benchmarks.public_memory_high_config_first import (
    ReadOnlyStore,
    ReadOnlyVectorIndex,
)
from benchmarks.public_memory_listwise_diagnostic import load_inputs
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_topk_diagnostic import execute, make_plan, prepared_pool
from doppel_memory.bounded_selection import BoundedTopKSelector

CASES = ("gpt4_ec93e27f", "gpt4_2f8be40d")
RUNNER = "doppel.bounded-topk-opened-two.v1"
FAILED_EXACT = Path("data/doppel/topk-diagnostic-live-v1.json")


def bounded_plan(hashes, certificates, schema):
    plan = make_plan(hashes, certificates, schema)
    plan.pop("plan_fingerprint")
    failed = json.loads(FAILED_EXACT.read_bytes())
    if (
        failed["status"] != "failed"
        or failed["stopped_stage"] != "source-selection"
        or failed["usage"]["selector"]["attempts_reserved"] != 1
    ):
        raise ValueError("retain the exact-k failure, no rescore or imported cache")
    plan.update(
        runner=RUNNER,
        cases=list(CASES),
        profile="metadata_up_to20_selected_unranked",
        selection_cardinality="upper-bound-not-quota",
        failed_exact_report_sha256=hashlib.sha256(
            FAILED_EXACT.read_bytes()
        ).hexdigest(),
        failed_exact_spend={
            "calls": 1,
            "tokens": failed["usage"]["selector"]["reported_tokens"]["total_tokens"],
        },
    )
    plan["stages"]["selector"]["max_calls"] = 4
    plan["stages"]["reader"]["max_calls"] = 2
    plan["stages"]["judge"]["max_calls"] = 2
    for path in (
        __file__,
        "doppel_memory/bounded_selection.py",
        "doppel_memory/reference_selection.py",
    ):
        plan["source_sha256"][path] = hashlib.sha256(
            Path(path).read_bytes()
        ).hexdigest()
    return {**plan, "plan_fingerprint": _hash(plan)}


async def run(args):
    data, hashes, manifest, all_selected, all_baselines = load_inputs()
    selected = [row for row in all_selected if row[1].case_id in CASES]
    baselines = [row for row in all_baselines if row["case_id"] in CASES]
    if tuple(row[1].case_id for row in selected) != CASES or len(baselines) != 2:
        raise ValueError("exactly the two preregistered opened cases required")
    schema = data["parent"]["plan"]["schema"]
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"), schema=schema
    )
    index = ReadOnlyVectorIndex(store, _LocalEmbeddingProvider(cache_dir=None))
    try:
        certificates = []
        for runtime, scoring in selected:
            *_, certificate = await prepared_pool(
                store, index, runtime, scoring, manifest, data, BoundedTopKSelector
            )
            certificates.append(certificate)
        plan = bounded_plan(hashes, certificates, schema)
        if not args.execute:
            return {"runner": RUNNER, "status": "ready", "plan": plan, "new_calls": 0}
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            raise ValueError("matching frozen preflight required")
        result = await execute(
            args,
            data,
            manifest,
            selected,
            baselines,
            plan,
            store,
            index,
            BoundedTopKSelector,
        )
        return {**result, "runner": RUNNER}
    finally:
        await store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("fresh output required")
    result = asyncio.run(run(args))
    save(args.output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "new_attempts": sum(
                    v["attempts_reserved"] for v in result.get("usage", {}).values()
                ),
            }
        )
    )
    raise SystemExit(0 if result["status"] in {"ready", "complete"} else 1)


if __name__ == "__main__":
    main()
