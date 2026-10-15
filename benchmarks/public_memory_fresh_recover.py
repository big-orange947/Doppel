"""Explicit one-attempt recovery and bounded continuation of a frozen source run.

Keep the failed ledger row and original receipt. No model/core/prompt changes,
question access, graph authoring, QA, or automatic second recovery.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path

from benchmarks.public_memory_expansion import save
from benchmarks.public_memory_fresh_continue import completed_prefix, execute
from benchmarks.public_memory_fresh_ingest import prepare_stage
from benchmarks.public_memory_pilot import _hash

RUNNER = "doppel.public-memory-fresh-source-recovery.v1"


def state(run_dir, ingestion):
    """Snapshot logical WAL-visible state; never erase or relabel failed attempts."""

    def read(name, sql):
        with sqlite3.connect(
            (run_dir / name).resolve().as_uri() + "?mode=ro", uri=True
        ) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(sql)]

    writes = read("ingestion.sqlite3", "SELECT * FROM writes ORDER BY rowid")
    observations = read(
        "ingestion.sqlite3", "SELECT * FROM analysis_observations ORDER BY key"
    )
    profile = read("ingestion.sqlite3", "SELECT * FROM host_profile ORDER BY id")
    sources = read("ingestion.sqlite3", "SELECT * FROM sources ORDER BY scope,event")
    calls = read("usage.sqlite3", "SELECT * FROM pilot_calls ORDER BY call_id")
    failures = read("usage.sqlite3", "SELECT * FROM pilot_failures ORDER BY call_id")
    audits = ingestion["audit"]["chunks"]
    complete = [row for row in audits if row["completed"]]
    if (
        [r["key"] for r in writes] != [r["write_key"] for r in audits]
        or [bool(r["completion"]) for r in writes] != [r["completed"] for r in audits]
        or any(r["completion"] and not r["consolidation_done"] for r in writes)
        or sorted(r["key"] for r in observations)
        != sorted(r["write_key"] for r in complete)
        or profile
        != [{"id": 1, "fingerprint": ingestion["audit"]["profile_fingerprint"]}]
        or not calls
        or any(r["status"] not in {"succeeded", "failed"} for r in calls)
    ):
        raise ValueError("source journal or settled provider attempts do not reconcile")
    failed = [r for r in calls if r["status"] == "failed"]
    if (
        len(failed) != 1
        or len(failures) != 1
        or failures[0]["call_id"] != failed[0]["call_id"]
        or json.loads(failures[0]["metadata"])["code"] != "transport_error"
    ):
        raise ValueError("exactly one preserved transport failure required")
    snapshot = {
        "journal_sha256": _hash([writes, observations, profile, sources]),
        "ledger_sha256": _hash([calls, failures]),
        "durable_attempts": len(calls),
        "calls_sha256": _hash(calls),
        "failed_attempt": {
            **failed[0],
            "diagnostics": json.loads(failures[0]["metadata"]),
        },
        "known_reported_tokens": sum(
            json.loads(r["usage"]).get("total_tokens", 0) for r in calls if r["usage"]
        ),
        "calls_without_usage": sum(r["usage"] is None for r in calls),
        "cache_sha256": _hash(
            {
                p.relative_to(run_dir / "provider-cache").as_posix(): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in sorted((run_dir / "provider-cache").rglob("*.json"))
            }
        ),
    }
    return snapshot, calls


def prepare(raw, manifest, cohort, parent, *, source_sha, parent_sha, run_dir, mode):
    cases, target = prepare_stage(
        raw, manifest, cohort, source_sha=source_sha, histories=10
    )
    ingestion = parent["ingestion"]
    audit = ingestion["audit"]
    rows = audit["chunks"]
    keys = [r["write_key"] for r in cohort["ingestion_plan"]["chunks"]]
    snapshot, calls = state(run_dir, ingestion)
    if ingestion["plan"] != cohort["ingestion_plan"]:
        raise ValueError("frozen ingestion configuration changed")
    if mode == "recover":
        stop = ingestion.get("stopped", {})
        pending = rows[-1]
        done = len(rows) - 1
        diagnostics = ingestion["usage_cumulative"]["ledger"]["failure_diagnostics"]
        failed = snapshot["failed_attempt"]
        if (
            parent["status"] != "failed"
            or ingestion["status"] != "failed"
            or ingestion["store_record_audit"]["provenance_failures"] != 0
            or [r["write_key"] for r in rows] != keys[: len(rows)]
            or not all(r["completed"] for r in rows[:-1])
            or audit["completed_chunks"] != done
            or audit["chunks_without_analysis_observation"] != 1
            or pending["completed"]
            or not pending["raw_stage_persisted"]
            or pending["proposal_stage_persisted"]
            or pending["analysis_diagnostics"] is not None
            or pending["consolidation_plan_persisted"]
            or pending["consolidation_done"]
            or stop.get("stage") != "extraction"
            or stop.get("code") != "stage-execution-failed"
            or stop.get("write_key") != pending["write_key"]
            or failed != {**calls[-1], "diagnostics": failed["diagnostics"]}
            or diagnostics
            != [
                {
                    "call_id": failed["call_id"],
                    "request_sha256": failed["request_sha256"],
                    **failed["diagnostics"],
                }
            ]
        ):
            raise ValueError("one exact unanalysed pending source chunk required")
        limit = 1
        failed_receipt = parent_sha
    elif mode == "resume":
        if (
            parent.get("runner") != RUNNER
            or parent["stage"]["mode"] != "recover"
            or parent.get("recovery_verified") is not True
            or parent.get("post_checkpoint") != snapshot
        ):
            raise ValueError("successful single recovery receipt required")
        done = completed_prefix(ingestion, cohort["ingestion_plan"])
        limit = target["max_new_chunks"] - done
        failed_receipt = parent["stage"]["failed_report_sha256"]
    else:
        raise ValueError("invalid recovery stage")
    if limit < 1 or done + limit > target["max_new_chunks"]:
        raise ValueError("fixed first-ten prefix already consumed")
    stage = {
        "runner": RUNNER,
        "mode": mode,
        "cohort_plan_fingerprint": cohort["plan_fingerprint"],
        "ingestion_plan_fingerprint": cohort["ingestion_plan"]["plan_fingerprint"],
        "parent_report_sha256": parent_sha,
        "failed_report_sha256": failed_receipt,
        "checkpoint": snapshot,
        "parent_completed_chunks": done,
        "target_completed_chunks": done + limit,
        "first_ten_target_chunks": target["max_new_chunks"],
        "max_new_chunks": limit,
        "max_provider_attempts": limit,
        "extra_recovery_attempts_authorized": 1,
        "historical_failure_preserved": True,
        "generation_settings_changed": False,
        "retry_policy": "one explicit recovery only; any further failure stops",
        "ledger_budget_mechanism": "continuation-v1; per-scope source revalidation",
        "implementation_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "graph_calls": 0,
        "qa_calls": 0,
    }
    return cases, {**stage, "plan_fingerprint": _hash(stage)}


async def run(args, cases, manifest, cohort, stage):
    result = await execute(args, cases, manifest, cohort, stage)
    if result["ingestion"]["status"] == "failed":
        # The ingestion receipt and durable ledger already retain diagnostics.
        # A second failure is never admissible as a new recovery parent.
        return {
            **result,
            "stage_verified": False,
            "recovery_verified": False,
            "post_checkpoint": None,
        }
    snapshot, calls = state(args.run_dir, result["ingestion"])
    prior = stage["checkpoint"]
    added = calls[prior["durable_attempts"] :]
    preserved = (
        _hash(calls[: prior["durable_attempts"]]) == prior["calls_sha256"]
        and snapshot["failed_attempt"] == prior["failed_attempt"]
    )
    verified = (
        preserved
        and result["ingestion"]["status"] in {"partial", "complete"}
        and completed_prefix(result["ingestion"], cohort["ingestion_plan"])
        == stage["target_completed_chunks"]
        and len(added) == stage["max_provider_attempts"]
        and all(r["status"] == "succeeded" for r in added)
        and (
            stage["mode"] != "recover"
            or added[0]["request_sha256"] == prior["failed_attempt"]["request_sha256"]
        )
    )
    return {
        **result,
        "post_checkpoint": snapshot,
        "historical_attempts_preserved": preserved,
        "recovery_verified": verified if stage["mode"] == "recover" else None,
        "stage_verified": verified,
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
    parser.add_argument("--mode", choices=("recover", "resume"), required=True)
    parser.add_argument("--frozen-stage", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve existing output")
    data, parent_data = args.dataset.read_bytes(), args.parent_report.read_bytes()
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
        mode=args.mode,
    )
    result = {
        "runner": RUNNER,
        "stage": stage,
        "status": "ready",
        "quality_metrics_available": False,
    }
    if args.live:
        result.update(asyncio.run(run(args, cases, manifest, cohort, stage)))
        result["status"] = (
            result["ingestion"]["status"] if result["stage_verified"] else "failed"
        )
    save(args.output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "cap": stage["max_provider_attempts"],
                "target": stage["target_completed_chunks"],
                "verified": result.get("stage_verified"),
            }
        )
    )
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
