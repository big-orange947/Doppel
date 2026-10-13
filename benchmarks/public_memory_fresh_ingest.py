"""Bounded source-only ingestion supplement for the frozen prospective cohort.

Does not execute queries, read original question/gold fields, or author a graph.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_expansion import local_diagnostic_dsn, save
from benchmarks.public_memory_fresh_cohort import (
    NAMESPACE,
    sampling_projection,
    validate_fingerprint,
)
from benchmarks.public_memory_ingestion import build_ingestion_plan, run_live
from benchmarks.public_memory_oracle_diagnostic import balance
from benchmarks.public_memory_pilot import _hash
from doppel_memory.openai_compatible import OpenAICompatibleStructuredOutputConfig

RUNNER = "doppel.public-memory-fresh-ingestion-stage.v1"


def prepare_stage(raw, manifest, cohort, *, source_sha, histories=1):
    validate_fingerprint(manifest, "manifest_fingerprint")
    if (
        source_sha != manifest["source_sha256"]
        or cohort["manifest_fingerprint"] != manifest["manifest_fingerprint"]
        or cohort["ingestion_plan"]["manifest_fingerprint"]
        != manifest["manifest_fingerprint"]
    ):
        raise ValueError("frozen source/cohort binding mismatch")
    identity = {
        k: v for k, v in cohort.items() if k not in {"runtime", "plan_fingerprint"}
    }
    identity["runtime_source_sha256"] = cohort["runtime"]["runtime_source_sha256"]
    if (
        _hash(identity) != cohort["plan_fingerprint"]
        or execution_metadata()["runtime_source_sha256"]
        != identity["runtime_source_sha256"]
    ):
        raise ValueError("frozen core snapshot changed")
    root = Path(__file__).resolve().parents[1]
    if any(
        hashlib.sha256((root / p).read_bytes()).hexdigest() != digest
        for p, digest in cohort["source_sha256"].items()
    ):
        raise ValueError("frozen configuration/prompt source changed")
    selected = [c for c in manifest["cases"] if c["partition"] == "diagnostic"]
    if type(histories) is not int or not 1 <= histories <= len(selected):
        raise ValueError("invalid fixed history prefix")
    by_id = {item["question_id"]: item for item in raw}
    if len(by_id) != len(raw):
        raise ValueError("duplicate source IDs")
    cases = [
        prepare_case(
            sampling_projection(by_id[c["case_id"]]), dataset_namespace=NAMESPACE
        ).runtime
        for c in selected
    ]
    ingestion = cohort["ingestion_plan"]
    rebuilt = build_ingestion_plan(
        cases,
        manifest,
        OpenAICompatibleStructuredOutputConfig.model_validate(
            ingestion["provider_config"]
        ),
        max_calls=ingestion["max_calls"],
        evidence_error_policy="quarantine",
    )
    if rebuilt != ingestion:
        raise ValueError("source-only ingestion plan changed")
    limit = sum(c["chunk_count"] for c in selected[:histories])
    stage = {
        "runner": RUNNER,
        "cohort_plan_fingerprint": cohort["plan_fingerprint"],
        "ingestion_plan_fingerprint": ingestion["plan_fingerprint"],
        "prefix_history_count": histories,
        "max_new_chunks": limit,
        "max_provider_attempts": limit,
        "initial_completed_chunks_required": 0,
        "source_case_ids": [c["case_id"] for c in selected[:histories]],
        "implementation_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "model_retry_policy": "none; preserve failures",
        "graph_calls": 0,
        "qa_calls": 0,
    }
    stage["plan_fingerprint"] = _hash(stage)
    return cases, stage


async def execute(args, cases, manifest, cohort, stage):
    if (
        not args.frozen_stage
        or json.loads(args.frozen_stage.read_bytes())["stage"] != stage
    ):
        raise ValueError("committed frozen ingestion stage required")
    # This first prefix must never accidentally advance to a second invocation's
    # next prefix under the same attempt ceiling. Cache-only replay is separate.
    if (args.run_dir / "ingestion.sqlite3").exists() and not args.cache_only:
        raise ValueError(
            "existing journal requires cache-only replay or a separately frozen continuation"
        )
    key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key and not args.cache_only:
        raise ValueError("provider key missing")
    initial = None if args.cache_only else await balance(key)
    if initial is not None and initial <= 0:
        raise ValueError("provider balance empty")
    result = await run_live(
        cases,
        manifest,
        cohort["ingestion_plan"],
        run_dir=args.run_dir,
        dsn=local_diagnostic_dsn("doppel-ablation-pgvector"),
        api_key=key,
        max_new_chunks=0 if args.cache_only else stage["max_new_chunks"],
        embedding_cache_dir=None,
        cache_only=args.cache_only,
        continuation_budget=None
        if args.cache_only
        else ("continuation-v1:" + stage["plan_fingerprint"], stage["max_new_chunks"]),
    )
    final = None
    if not args.cache_only:
        try:
            final = await balance(key)
        except Exception:  # noqa: BLE001 - do not expose provider/credential errors
            final = None
    return {
        "ingestion": result,
        "balance_observation": {
            "initial_cny": initial,
            "final_cny": final,
            "exclusive_billing_attribution_proven": False,
        },
        "quality_metrics_available": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "manifest", "cohort-plan", "run-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frozen-stage", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("preserve outputs; cache-only requires live")
    raw = args.dataset.read_bytes()
    manifest = json.loads(args.manifest.read_bytes())
    cohort = json.loads(args.cohort_plan.read_bytes())
    cases, stage = prepare_stage(
        json.loads(raw), manifest, cohort, source_sha=hashlib.sha256(raw).hexdigest()
    )
    result = {
        "runner": RUNNER,
        "stage": stage,
        "status": "ready",
        "provider_calls": 0,
        "quality_metrics_available": False,
    }
    if args.live:
        result.update(asyncio.run(execute(args, cases, manifest, cohort, stage)))
        result["status"] = result["ingestion"]["status"]
        result["provider_calls"] = result["ingestion"]["llm_calls_this_invocation"]
    result["execution_metadata"] = execution_metadata()
    save(args.output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "provider_calls": result["provider_calls"],
                "completed_chunks": result.get("ingestion", {}).get(
                    "new_chunks_completed", 0
                ),
            }
        )
    )
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
