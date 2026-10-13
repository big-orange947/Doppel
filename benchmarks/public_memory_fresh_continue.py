"""Continue the frozen prospective source prefix; never open questions or gold.

The old prefix, journal and attempt ledger must reconcile before a new bounded
budget is created. A consumed stage cannot silently advance to another prefix.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
from pathlib import Path

from benchmarks.public_memory_expansion import local_diagnostic_dsn, save
from benchmarks.public_memory_fresh_ingest import prepare_stage
from benchmarks.public_memory_ingestion import run_live
from benchmarks.public_memory_oracle_diagnostic import balance
from benchmarks.public_memory_pilot import _hash

RUNNER = "doppel.public-memory-fresh-source-continuation.v1"


def completed_prefix(ingestion, plan):
    """A settled prefix is not a claim that the whole cohort has been ingested."""
    rows = ingestion["audit"]["chunks"]
    keys = [r["write_key"] for r in plan["chunks"]]
    if (
        ingestion["plan"] != plan
        or ingestion["status"] not in {"partial", "complete"}
        or ingestion["store_record_audit"]["provenance_failures"] != 0
        or not rows
        or any(not r["completed"] for r in rows)
        or [r["write_key"] for r in rows] != keys[: len(rows)]
        or ingestion["audit"]["completed_chunks"] != len(rows)
        or ingestion["audit"]["chunks_without_analysis_observation"] != 0
    ):
        raise ValueError("settled, source-bound, provenance-audited prefix required")
    return len(rows)


def checkpoint(run_dir, ingestion):
    """Read logical SQLite contents, including WAL, without creating any tables."""

    def read(name, sql):
        with sqlite3.connect(
            (run_dir / name).resolve().as_uri() + "?mode=ro", uri=True
        ) as db:
            return db.execute(sql).fetchall()

    writes = read("ingestion.sqlite3", "SELECT * FROM writes ORDER BY rowid")
    observations = read(
        "ingestion.sqlite3", "SELECT * FROM analysis_observations ORDER BY key"
    )
    profile = read("ingestion.sqlite3", "SELECT * FROM host_profile ORDER BY id")
    sources = read("ingestion.sqlite3", "SELECT * FROM sources ORDER BY scope,event")
    calls = read("usage.sqlite3", "SELECT * FROM pilot_calls ORDER BY call_id")
    statuses = read("usage.sqlite3", "SELECT status FROM pilot_calls ORDER BY call_id")
    if (
        [r[0] for r in writes] != [r["write_key"] for r in ingestion["audit"]["chunks"]]
        or any(r[-1] is None or not r[-2] for r in writes)
        or len(observations) != len(writes)
        or profile != [(1, ingestion["audit"]["profile_fingerprint"])]
        or any(r[0] != "succeeded" for r in statuses)
        or not calls
    ):
        raise ValueError("journal or provider attempts do not reconcile")
    return {
        "journal_sha256": _hash([writes, observations, profile, sources]),
        "ledger_sha256": _hash(calls),
        "durable_attempts": len(calls),
        "cache_sha256": _hash(
            {
                p.relative_to(run_dir / "provider-cache").as_posix(): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in sorted((run_dir / "provider-cache").rglob("*.json"))
            }
        ),
    }


def prepare(
    raw, manifest, cohort, parent, *, source_sha, parent_sha, run_dir, histories
):
    cases, target = prepare_stage(
        raw, manifest, cohort, source_sha=source_sha, histories=histories
    )
    ingestion = parent["ingestion"]
    done = completed_prefix(ingestion, cohort["ingestion_plan"])
    limit = target["max_new_chunks"] - done
    if limit < 1:
        raise ValueError("target prefix is already consumed")
    frozen = {
        "runner": RUNNER,
        "cohort_plan_fingerprint": cohort["plan_fingerprint"],
        "ingestion_plan_fingerprint": cohort["ingestion_plan"]["plan_fingerprint"],
        "parent_report_sha256": parent_sha,
        "parent_completed_chunks": done,
        "checkpoint": checkpoint(run_dir, ingestion),
        "prefix_history_count": histories,
        "target_completed_chunks": target["max_new_chunks"],
        "source_case_ids": target["source_case_ids"],
        "max_new_chunks": limit,
        "max_provider_attempts": limit,
        "implementation_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "model_retry_policy": "none; first failure stops and is preserved",
        "graph_calls": 0,
        "qa_calls": 0,
    }
    return cases, {**frozen, "plan_fingerprint": _hash(frozen)}


async def execute(args, cases, manifest, cohort, stage):
    if (
        not args.frozen_stage
        or json.loads(args.frozen_stage.read_bytes())["stage"] != stage
    ):
        raise ValueError("unchanged frozen continuation required")
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise ValueError("provider key missing")
    initial = await balance(key)
    if initial is not None and initial <= 0:
        raise ValueError("provider balance empty")
    ingestion = await run_live(
        cases,
        manifest,
        cohort["ingestion_plan"],
        run_dir=args.run_dir,
        dsn=local_diagnostic_dsn("doppel-ablation-pgvector"),
        api_key=key,
        max_new_chunks=stage["max_new_chunks"],
        embedding_cache_dir=None,
        continuation_budget=(
            "continuation-v1:" + stage["plan_fingerprint"],
            stage["max_new_chunks"],
        ),
    )
    try:
        final = await balance(key)
    except Exception:  # noqa: BLE001 - no credential/provider error text
        final = None
    return {
        "ingestion": ingestion,
        "balance_observation": {
            "initial_cny": initial,
            "final_cny": final,
            "exclusive_billing_attribution_proven": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "dataset",
        "manifest",
        "cohort-plan",
        "parent-report",
        "run-dir",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--histories", type=int, default=3)
    parser.add_argument("--frozen-stage", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve previous outputs")
    data = args.dataset.read_bytes()
    parent_data = args.parent_report.read_bytes()
    manifest = json.loads(args.manifest.read_bytes())
    cohort = json.loads(args.cohort_plan.read_bytes())
    cases, stage = prepare(
        json.loads(data),
        manifest,
        cohort,
        json.loads(parent_data),
        source_sha=hashlib.sha256(data).hexdigest(),
        parent_sha=hashlib.sha256(parent_data).hexdigest(),
        run_dir=args.run_dir,
        histories=args.histories,
    )
    result = {
        "runner": RUNNER,
        "stage": stage,
        "status": "ready",
        "quality_metrics_available": False,
    }
    if args.live:
        result.update(asyncio.run(execute(args, cases, manifest, cohort, stage)))
        result["status"] = result["ingestion"]["status"]
    save(args.output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "new_call_cap": stage["max_provider_attempts"],
                "target_completed_chunks": stage["target_completed_chunks"],
                "new_calls": result.get("ingestion", {}).get(
                    "llm_calls_this_invocation", 0
                ),
            }
        )
    )
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
