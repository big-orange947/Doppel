"""One explicit, unchanged-request recovery observation; no automatic retries/QA."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.public_context_baseline import (
    execution_metadata,
    select_diagnostic_cases,
)
from benchmarks.public_longmemeval import RuntimeCase
from benchmarks.public_memory_expansion import local_diagnostic_dsn, save
from benchmarks.public_memory_ingestion import (
    _bind_json,
    build_ingestion_plan,
    run_live,
)
from benchmarks.public_memory_pilot import _hash
from doppel_memory.openai_compatible import OpenAICompatibleStructuredOutputConfig


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cache_inventory(path: Path) -> dict[str, str]:
    return {
        p.relative_to(path).as_posix(): file_sha(p)
        for p in sorted(path.rglob("*.json"))
    }


def build_plan(
    cases: Sequence[RuntimeCase],
    manifest: Mapping[str, Any],
    parent: Mapping[str, Any],
    *,
    parent_report_sha: str,
    journal_sha: str,
    cache: Mapping[str, str],
) -> dict[str, Any]:
    ingestion = parent["plan"]
    stop = parent.get("stopped", {})
    if (
        parent.get("status") != "failed"
        or parent.get("all_histories_ingested") is not False
        or stop.get("stage") != "extraction"
        or stop.get("code") != "stage-execution-failed"
    ):
        raise ValueError("failed extraction parent required")
    expected = build_ingestion_plan(
        cases,
        manifest,
        OpenAICompatibleStructuredOutputConfig.model_validate(
            ingestion["provider_config"]
        ),
        max_calls=ingestion["max_calls"],
        evidence_error_policy=ingestion["miner_config"].get(
            "evidence_error_policy", "fail_batch"
        ),
    )
    if dict(ingestion) != expected:
        raise ValueError("parent history/configuration binding differs")
    keys = [c["write_key"] for c in ingestion["chunks"]]
    chunks = parent["audit"]["chunks"]
    completed = [c["write_key"] for c in chunks if c["completed"]]
    if (
        len(chunks) != len(completed) + 1
        or completed != keys[: len(completed)]
        or chunks[-1]["write_key"] != keys[len(completed)]
        or chunks[-1]["write_key"] != stop["write_key"]
        or chunks[-1]["proposal_stage_persisted"]
        or chunks[-1]["analysis_diagnostics"] is not None
    ):
        raise ValueError("exact completed prefix and unanalysed pending chunk required")
    value = {
        "runner": "doppel.public-memory-recovery-observation.v1",
        "parent_report_sha256": parent_report_sha,
        "parent_journal_sha256": journal_sha,
        "parent_cache_inventory_sha256": _hash(dict(cache)),
        "parent_usage": parent["usage_cumulative"]["ledger"],
        "ingestion_plan": expected,
        "pending_write_key": stop["write_key"],
        "completed_prefix_chunks": len(completed),
        "max_new_calls": 1,
        "max_new_chunks": 1,
        "generation_settings_changed": False,
        "failure_policy": "one-explicit-attempt; stop; no-automatic-retry-or-downstream",
        "source_sha256": {
            str(
                p.relative_to(Path(__file__).resolve().parents[1]).as_posix()
            ): file_sha(p)
            for p in (
                Path(__file__),
                Path(__file__).with_name("public_memory_runtime.py"),
                Path(__file__).with_name("public_memory_ingestion.py"),
                Path(__file__).resolve().parents[1]
                / "doppel_memory/openai_compatible.py",
            )
        },
    }
    return {**value, "plan_fingerprint": _hash(value)}


def clone_journal(source: Path, destination: Path, expected_sha: str) -> None:
    """Snapshot a closed parent journal, never edit/reset it or copy its usage ledger."""
    if destination.exists() or source.resolve() == destination.resolve():
        raise ValueError("fresh recovery journal destination required")
    if file_sha(source) != expected_sha:
        raise ValueError("parent journal changed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    original = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    snapshot = sqlite3.connect(destination)
    try:
        original.backup(snapshot)
    finally:
        snapshot.close()
        original.close()
    if file_sha(source) != expected_sha:
        raise ValueError("parent journal changed during snapshot")


async def run(
    cases: Sequence[RuntimeCase],
    manifest: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    run_dir: Path,
    parent_dir: Path,
    dsn: str,
    api_key: str,
    embedding_cache_dir: Path | None,
) -> dict[str, Any]:
    _bind_json(run_dir / "recovery-plan.json", plan)
    history_dir = run_dir / "ingestion"
    journal = history_dir / "ingestion.sqlite3"
    if journal.exists() or (history_dir / "usage.sqlite3").exists():
        raise ValueError("recovery observation already attempted; do not rebill")
    clone_journal(
        parent_dir / "ingestion.sqlite3", journal, plan["parent_journal_sha256"]
    )
    result = await run_live(
        cases,
        manifest,
        plan["ingestion_plan"],
        run_dir=history_dir,
        dsn=dsn,
        api_key=api_key,
        max_new_chunks=1,
        embedding_cache_dir=embedding_cache_dir,
        read_only_cache_dirs=[parent_dir / "provider-cache"],
        recovery_budget=("recovery-observe-v1:" + plan["plan_fingerprint"], 1),
    )
    target = next(
        c
        for c in result["audit"]["chunks"]
        if c["write_key"] == plan["pending_write_key"]
    )
    old = plan["parent_usage"]
    new = result["usage_cumulative"]["ledger"]
    tokens_known = old["token_accounting_complete"] and new["token_accounting_complete"]
    success = (
        target["completed"]
        and result["status"] == "partial"
        and new["attempts_reserved"] == 1
    )
    return {
        "runner": plan["runner"],
        "status": "observed-success" if success else "failed",
        "plan": dict(plan),
        "execution_metadata": execution_metadata(),
        "ingestion": result,
        "pending_chunk_completed": target["completed"],
        "generation_settings_changed": False,
        "parent_artifacts_preserved": True,
        "aggregate_calls": old["attempts_reserved"] + new["attempts_reserved"],
        "aggregate_reported_tokens": (
            old["reported_tokens"]["total_tokens"]
            + (new["reported_tokens"] or {}).get("total_tokens", 0)
            if tokens_known
            else None
        ),
        "retrieval_executed": False,
        "answers_executed": False,
        "quality_metrics_available": False,
        "publication_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "dataset",
        "manifest",
        "parent-report",
        "parent-dir",
        "run-dir",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--parent-report-sha256", required=True)
    parser.add_argument("--embedding-cache-dir", type=Path)
    parser.add_argument("--local-pg-container", default="doppel-ablation-pgvector")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or args.run_dir.resolve() == args.parent_dir.resolve():
        parser.error("preserve old artifacts; use a fresh recovery directory/output")
    if file_sha(args.parent_report) != args.parent_report_sha256:
        parser.error("parent report hash mismatch")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    cases = [
        r
        for r, _ in select_diagnostic_cases(
            json.loads(args.dataset.read_text(encoding="utf-8")),
            manifest,
            source_sha256=file_sha(args.dataset),
        )
    ]
    parent = json.loads(args.parent_report.read_text(encoding="utf-8"))
    parent_journal = args.parent_dir / "ingestion.sqlite3"
    parent_cache = cache_inventory(args.parent_dir / "provider-cache")
    plan = build_plan(
        cases,
        manifest,
        parent,
        parent_report_sha=args.parent_report_sha256,
        journal_sha=file_sha(parent_journal),
        cache=parent_cache,
    )
    _bind_json(args.run_dir / "recovery-plan.json", plan)
    report = {
        "runner": plan["runner"],
        "status": "ready",
        "plan": plan,
        "llm_calls": 0,
        "quality_metrics_available": False,
    }
    if args.live:
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            parser.error(
                "DEEPSEEK_API_KEY unavailable; never put keys in command arguments"
            )
        try:
            report = asyncio.run(
                run(
                    cases,
                    manifest,
                    plan,
                    run_dir=args.run_dir,
                    parent_dir=args.parent_dir,
                    dsn=local_diagnostic_dsn(args.local_pg_container),
                    api_key=key,
                    embedding_cache_dir=args.embedding_cache_dir,
                )
            )
        except Exception as exc:  # noqa: BLE001 - no provider/DSN exception text
            report = {
                "runner": plan["runner"],
                "status": "failed",
                "plan": plan,
                "failure_type": type(exc).__name__,
                "quality_metrics_available": False,
                "usage": "consult recovery usage ledger; unknown is not zero",
            }
    if (
        file_sha(parent_journal) != plan["parent_journal_sha256"]
        or cache_inventory(args.parent_dir / "provider-cache") != parent_cache
    ):
        report["status"] = "failed"
        report["parent_artifacts_preserved"] = False
    save(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "pending_chunk_completed": report.get("pending_chunk_completed"),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] in {"ready", "observed-success"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
