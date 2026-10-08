"""Continue a frozen public-memory ingestion prefix with a separate call budget."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from benchmarks.public_context_baseline import select_diagnostic_cases
from benchmarks.public_memory_expansion import local_diagnostic_dsn
from benchmarks.public_memory_ingestion import build_ingestion_plan, run_live
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_recovery import file_sha
from doppel_memory.openai_compatible import OpenAICompatibleStructuredOutputConfig


def _ingestion_report(parent: dict[str, Any]) -> dict[str, Any]:
    if parent.get("runner") == "doppel.public-memory-recovery-observation.v1":
        nested = parent.get("ingestion")
        if isinstance(nested, dict):
            return nested
        raise ValueError("recovery parent does not contain an ingestion report")
    return parent


def build_plan(
    dataset_path: Path,
    manifest_path: Path,
    parent_report_path: Path,
    run_dir: Path,
    *,
    max_new_chunks: int,
) -> dict[str, Any]:
    dataset_bytes = dataset_path.read_bytes()
    dataset_sha = hashlib.sha256(dataset_bytes).hexdigest()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parent = json.loads(parent_report_path.read_text(encoding="utf-8"))
    if parent.get("runner") == "doppel.public-memory-recovery-observation.v1":
        if (
            parent.get("status") != "observed-success"
            or parent.get("parent_artifacts_preserved") is not True
            or not isinstance(parent.get("plan"), dict)
        ):
            raise ValueError("successful, preserved recovery observation required")
        inherited_chunks = parent["plan"].get("completed_prefix_chunks")
        parent_ingestion = _ingestion_report(parent)
    elif parent.get("runner") == "doppel.public-memory-ingestion.v1":
        inherited_chunks = parent.get("continuation", {}).get(
            "parent_completed_chunks", 0
        ) - parent.get("continuation", {}).get("prior_durable_attempts", 0)
        parent_ingestion = _ingestion_report(parent)
    else:
        raise ValueError("known ingestion or recovery report required")
    source_plan = (
        parent_ingestion.get("plan") if isinstance(parent_ingestion, dict) else None
    )
    if (
        not isinstance(parent_ingestion, dict)
        or parent_ingestion.get("status") != "partial"
        or parent_ingestion.get("runner") != "doppel.public-memory-ingestion.v1"
        or not isinstance(source_plan, dict)
        or parent_ingestion.get("store_record_audit", {}).get("provenance_failures")
        != 0
        or type(inherited_chunks) is not int
        or inherited_chunks < 0
    ):
        raise ValueError("a partial, provenance-audited ingestion report is required")
    selected = select_diagnostic_cases(
        json.loads(dataset_bytes), manifest, source_sha256=dataset_sha
    )
    cases = [runtime for runtime, _scoring in selected]
    ingestion_plan = source_plan
    config = OpenAICompatibleStructuredOutputConfig.model_validate(
        ingestion_plan["provider_config"]
    )
    rebuilt = build_ingestion_plan(
        cases,
        manifest,
        config,
        max_calls=ingestion_plan["max_calls"],
        evidence_error_policy=ingestion_plan["miner_config"].get(
            "evidence_error_policy", "fail_batch"
        ),
    )
    rows = parent_ingestion["audit"]["chunks"]
    keys = [row["write_key"] for row in ingestion_plan["chunks"]]
    completed = [row["write_key"] for row in rows if row["completed"]]
    if (
        dataset_sha != manifest["source_sha256"]
        or dataset_sha != ingestion_plan["source_sha256"]
        or rebuilt != ingestion_plan
        or len(rows) != len(completed)
        or not completed
        or completed != keys[: len(completed)]
        or parent_ingestion.get("store_record_audit", {}).get("provenance_failures")
        != 0
        or not 1 <= max_new_chunks <= len(keys) - len(completed)
    ):
        raise ValueError("source, completed prefix, audit or bounded call cap is invalid")
    ledger = parent_ingestion.get("usage_cumulative", {}).get("ledger", {})
    usage = run_dir / "ingestion" / "usage.sqlite3"
    cache_dir = run_dir / "ingestion" / "provider-cache"
    connection = sqlite3.connect(f"file:{usage.resolve().as_posix()}?mode=ro", uri=True)
    try:
        attempts = connection.execute(
            "SELECT status, usage FROM pilot_calls ORDER BY call_id"
        ).fetchall()
    finally:
        connection.close()
    statuses = [row[0] for row in attempts]
    continuation = parent_ingestion.get("continuation", {})
    prior_local_attempts = continuation.get("prior_durable_attempts", 0)
    current_attempts = parent_ingestion.get("llm_calls_this_invocation")
    if (
        type(prior_local_attempts) is not int
        or type(current_attempts) is not int
        or prior_local_attempts < 0
        or current_attempts < 0
    ):
        raise ValueError("parent report has invalid attempt counts")
    expected_attempts = prior_local_attempts + current_attempts
    if (
        len(attempts) != expected_attempts
        or any(status != "succeeded" for status in statuses)
        or len(completed) - len(attempts) != inherited_chunks
        or ledger.get("failed_calls_without_diagnostics") != 0
        or ledger.get("token_accounting_complete") is not True
    ):
        raise ValueError("durable call ledger does not reconcile with completed prefix")
    checkpoint_inventory = _checkpoint_inventory(run_dir / "ingestion")
    value = {
        "runner": "doppel.public-memory-ingestion-continuation.v1",
        "dataset_sha256": dataset_sha,
        "manifest_sha256": file_sha(manifest_path),
        "parent_report_sha256": file_sha(parent_report_path),
        "parent_plan_fingerprint": ingestion_plan["plan_fingerprint"],
        "parent_completed_chunks": len(completed),
        "inherited_completed_chunks": inherited_chunks,
        "parent_checkpoint_inventory_sha256": checkpoint_inventory,
        "parent_cache_inventory_sha256": _hash(
            {
                str(p.relative_to(cache_dir).as_posix()): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in sorted(cache_dir.rglob("*"))
                if p.is_file()
            }
        ),
        "next_chunk_keys_sha256": _hash(keys[len(completed) : len(completed) + max_new_chunks]),
        "remaining_before_block": len(keys) - len(completed),
        "max_new_chunks": max_new_chunks,
        "max_new_calls": max_new_chunks,
        "prior_durable_attempts": len(attempts),
        "prior_all_attempts_succeeded": True,
        "continuation_runner_sha256": file_sha(Path(__file__)),
        "ingestion_runner_sha256": file_sha(
            Path(__file__).with_name("public_memory_ingestion.py")
        ),
        "provider_config": ingestion_plan["provider_config"],
        "miner_config": ingestion_plan["miner_config"],
        "runtime_sources": parent_ingestion.get("execution_metadata", {}).get(
            "composition_source_sha256", {}
        ),
        "qa_calls": 0,
        "retrieval_executed": False,
        "plan_fingerprint": "",
    }
    value.pop("plan_fingerprint")
    return {**value, "plan_fingerprint": _hash(value)}


def _checkpoint_inventory(ingestion_dir: Path) -> str:
    return _hash(
        {
            str(path.relative_to(ingestion_dir).as_posix()): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(ingestion_dir.rglob("*"))
            if path.is_file()
            and (
                "sqlite3" in path.name
                or path.name == "plan.json"
                or path.name == "recovery-budget.json"
                or path.name.startswith("continuation-budget-")
            )
        }
    )


async def execute(
    dataset_path: Path,
    manifest_path: Path,
    parent_report_path: Path,
    run_dir: Path,
    output_path: Path,
    *,
    max_new_chunks: int,
) -> dict[str, Any]:
    plan = build_plan(
        dataset_path,
        manifest_path,
        parent_report_path,
        run_dir,
        max_new_chunks=max_new_chunks,
    )
    plan_path = run_dir / f"continuation-plan-{plan['plan_fingerprint'][:12]}.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with plan_path.open("x", encoding="utf-8") as handle:
            json.dump(plan, handle, ensure_ascii=False, sort_keys=True, indent=2)
    except FileExistsError:
        if json.loads(plan_path.read_text(encoding="utf-8")) != plan:
            raise ValueError("continuation directory is bound to another plan") from None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected = select_diagnostic_cases(
        json.loads(dataset_path.read_bytes()),
        manifest,
        source_sha256=plan["dataset_sha256"],
    )
    cases = [runtime for runtime, _scoring in selected]
    original = json.loads(parent_report_path.read_text(encoding="utf-8"))
    cache_dir = run_dir / "ingestion" / "provider-cache"
    if (
        _checkpoint_inventory(run_dir / "ingestion")
        != plan["parent_checkpoint_inventory_sha256"]
        or _hash(
            {
                str(p.relative_to(cache_dir).as_posix()): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in sorted(cache_dir.rglob("*"))
                if p.is_file()
            }
        )
        != plan["parent_cache_inventory_sha256"]
    ):
        raise ValueError("checkpoint changed after continuation was planned")
    parent_plan = _ingestion_report(original)["plan"]
    report = await run_live(
        cases,
        manifest,
        parent_plan,
        run_dir=run_dir / "ingestion",
        dsn=local_diagnostic_dsn("doppel-ablation-pgvector"),
        api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        max_new_chunks=max_new_chunks,
        embedding_cache_dir=Path("C:/Users/freeze/AppData/Local/Temp/fastembed_cache"),
        continuation_budget=(
            "continuation-v1:" + plan["plan_fingerprint"],
            max_new_chunks,
        ),
    )
    report["continuation"] = plan
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for item in ("dataset", "manifest", "parent-report", "run-dir", "output"):
        parser.add_argument("--" + item, type=Path, required=True)
    parser.add_argument("--max-new-chunks", type=int, default=200)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("choose a new continuation report path")
    if not args.live:
        plan = build_plan(
            args.dataset,
            args.manifest,
            args.parent_report,
            args.run_dir,
            max_new_chunks=args.max_new_chunks,
        )
        plan_path = args.run_dir / f"continuation-plan-{plan['plan_fingerprint'][:12]}.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with plan_path.open("x", encoding="utf-8") as handle:
                json.dump(plan, handle, ensure_ascii=False, sort_keys=True, indent=2)
        except FileExistsError:
            if json.loads(plan_path.read_text(encoding="utf-8")) != plan:
                raise ValueError("frozen plan path already contains different inputs") from None
        print(f"frozen_plan: {plan_path.resolve()}")
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return
    report = asyncio.run(
        execute(
            args.dataset,
            args.manifest,
            args.parent_report,
            args.run_dir,
            args.output,
            max_new_chunks=args.max_new_chunks,
        )
    )
    print(f"output: {args.output.resolve()}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "completed_chunks": report["audit"]["completed_chunks"],
                "new_calls": report["llm_calls_this_invocation"],
                "reported_tokens": report["provider_tokens_this_invocation"],
                "provenance_failures": report["store_record_audit"]["provenance_failures"],
                "quality_metrics_available": False,
            }
        )
    )
    if report["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
