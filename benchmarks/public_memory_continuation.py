"""Same-sample remaining ingestion followed immediately by fixed three-channel QA."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.public_context_baseline import (
    execution_metadata,
    select_diagnostic_cases,
)
from benchmarks.public_context_rerank import (
    LocalContextCrossEncoder,
    StrictContextReranker,
)
from benchmarks.public_longmemeval import RuntimeCase, ScoringCase
from benchmarks.public_memory_comparison import run_comparison
from benchmarks.public_memory_expansion import (
    answer_rows,
    local_diagnostic_dsn,
    run_answers,
    save,
)
from benchmarks.public_memory_expansion import (
    build_plan as expansion_plan,
)
from benchmarks.public_memory_ingestion import (
    _bind_json,
    build_ingestion_plan,
    run_live,
)
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_recovery import cache_inventory, clone_journal, file_sha
from doppel_memory.openai_compatible import OpenAICompatibleStructuredOutputConfig


def build_plan(
    cases: Sequence[tuple[RuntimeCase, ScoringCase]],
    manifest: Mapping[str, Any],
    parent: Mapping[str, Any],
    *,
    parent_report_sha: str,
    journal_sha: str,
    cache_inventories: Sequence[Mapping[str, str]],
    reranker_identity: Mapping[str, Any],
) -> dict[str, Any]:
    if parent.get("status") != "observed-success" or not parent.get(
        "parent_artifacts_preserved"
    ):
        raise ValueError("successful preserved recovery parent required")
    ingested = parent["ingestion"]
    old_plan = ingested["plan"]
    rebuilt = build_ingestion_plan(
        [r for r, _ in cases],
        manifest,
        OpenAICompatibleStructuredOutputConfig.model_validate(
            old_plan["provider_config"]
        ),
        max_calls=old_plan["max_calls"],
        evidence_error_policy=old_plan["miner_config"].get(
            "evidence_error_policy", "fail_batch"
        ),
    )
    chunks = ingested["audit"]["chunks"]
    keys = [c["write_key"] for c in old_plan["chunks"]]
    if (
        rebuilt != old_plan
        or any(not c["completed"] for c in chunks)
        or [c["write_key"] for c in chunks] != keys[: len(chunks)]
        or not 0 < len(chunks) < len(keys)
        or ingested["store_record_audit"]["provenance_failures"] != 0
    ):
        raise ValueError("exact completed source-bound prefix required")
    value = dict(expansion_plan(cases, manifest, reranker_identity=reranker_identity))
    value.pop("plan_fingerprint")
    remaining = len(keys) - len(chunks)
    value.update(
        {
            "runner": "doppel.public-memory-continuation.v1",
            "parent_report_sha256": parent_report_sha,
            "parent_journal_sha256": journal_sha,
            "parent_cache_inventory_sha256": [
                _hash(dict(c)) for c in cache_inventories
            ],
            "parent_calls": parent["aggregate_calls"],
            "parent_reported_tokens": parent["aggregate_reported_tokens"],
            "completed_prefix_chunks": len(chunks),
            "remaining_chunks": remaining,
            "max_extraction_calls": remaining,
            "max_total_calls": remaining + 60,
            "generation_settings_changed": False,
            "replay_policy": "validate-every-completed-source; reconcile-once-per-scope",
            "continuation_source_sha256": file_sha(Path(__file__)),
            "host_source_sha256": file_sha(
                Path(__file__).resolve().parents[1] / "integrations/aml/ingestion.py"
            ),
        }
    )
    if value["ingestion_plan"] != old_plan:
        raise ValueError("generation or ingestion policy changed")
    return {**value, "plan_fingerprint": _hash(value)}


def aggregate_usage(plan, ingestion, answers=None):
    ledgers = [ingestion["usage_cumulative"]["ledger"]]
    if answers is not None:
        ledgers.extend(v["ledger"] for v in answers["usage"].values())
    known = plan["parent_reported_tokens"] is not None and all(
        l["token_accounting_complete"] for l in ledgers
    )
    return {
        "calls_including_parents": plan["parent_calls"]
        + sum(l["attempts_reserved"] for l in ledgers),
        "reported_tokens_including_parents": (
            plan["parent_reported_tokens"]
            + sum((l["reported_tokens"] or {}).get("total_tokens", 0) for l in ledgers)
            if known
            else None
        ),
    }


async def run(
    cases,
    manifest,
    plan,
    *,
    run_dir,
    parent_dir,
    cache_dirs,
    dsn,
    api_key,
    embedding_cache_dir,
    reranker,
    cache_only=False,
):
    _bind_json(run_dir / "plan.json", plan)
    history_dir = run_dir / "ingestion"
    journal = history_dir / "ingestion.sqlite3"
    if not cache_only:
        if journal.exists() or (history_dir / "usage.sqlite3").exists():
            raise ValueError("attempted continuation may only replay cache-only")
        clone_journal(
            parent_dir / "ingestion.sqlite3", journal, plan["parent_journal_sha256"]
        )
    elif not journal.exists():
        raise ValueError("cache-only requires an existing continuation checkpoint")
    name = "replay" if cache_only else "live"
    ingested = await run_live(
        [r for r, _ in cases],
        manifest,
        plan["ingestion_plan"],
        run_dir=history_dir,
        dsn=dsn,
        api_key=api_key,
        max_new_chunks=plan["remaining_chunks"],
        embedding_cache_dir=embedding_cache_dir,
        cache_only=cache_only,
        read_only_cache_dirs=cache_dirs,
        continuation_budget=(
            "continuation-v1:" + plan["plan_fingerprint"],
            plan["remaining_chunks"],
        ),
    )
    save(run_dir / f"ingestion-{name}.json", ingested)
    result = {
        "status": "stopped",
        "stage": "ingestion",
        "ingestion": ingested,
        "answers_executed": False,
        "usage": aggregate_usage(plan, ingested),
    }
    if ingested["status"] != "complete" or not ingested["all_histories_ingested"]:
        return result
    print("all histories ingested; starting three-channel retrieval", flush=True)
    comparison = await run_comparison(
        cases,
        manifest,
        ingested,
        run_dir=history_dir,
        dsn=dsn,
        embedding_cache_dir=embedding_cache_dir,
        reranker=StrictContextReranker(reranker),
        profile_mode="reranked_only",
    )
    save(run_dir / f"retrieval-{name}.json", comparison)
    print("retrieval complete; starting 30 Reader/Judge rows", flush=True)
    answers = await run_answers(
        answer_rows(comparison, cases),
        plan,
        run_dir=run_dir / "answers",
        api_key=api_key,
        cache_only=cache_only,
    )
    save(run_dir / f"answers-{name}.json", answers)
    return {
        "status": answers["status"],
        "stage": "answers",
        "ingestion": ingested,
        "retrieval": comparison,
        "answers": answers,
        "answers_executed": True,
        "usage": aggregate_usage(plan, ingested, answers),
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
        "reranker-model-path",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--parent-report-sha256", required=True)
    parser.add_argument("--parent-cache-dir", type=Path, action="append", required=True)
    parser.add_argument("--embedding-cache-dir", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or args.run_dir.resolve() == args.parent_dir.resolve():
        parser.error("fresh output/child directory required")
    if args.cache_only and not args.live:
        parser.error("cache-only requires live")
    if file_sha(args.parent_report) != args.parent_report_sha256:
        parser.error("parent report hash mismatch")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    cases = select_diagnostic_cases(
        json.loads(args.dataset.read_text(encoding="utf-8")),
        manifest,
        source_sha256=file_sha(args.dataset),
    )
    parent = json.loads(args.parent_report.read_text(encoding="utf-8"))
    inventories = [cache_inventory(p) for p in args.parent_cache_dir]
    if not all(inventories):
        parser.error("declared read-only parent cache unavailable")
    reranker = LocalContextCrossEncoder(args.reranker_model_path, device="cuda")
    identity = {
        k: reranker.report()[k]
        for k in (
            "name",
            "version",
            "model_artifact_sha256",
            "max_length",
            "batch_size",
            "device_requested",
        )
    }
    plan = build_plan(
        cases,
        manifest,
        parent,
        parent_report_sha=args.parent_report_sha256,
        journal_sha=file_sha(args.parent_dir / "ingestion.sqlite3"),
        cache_inventories=inventories,
        reranker_identity=identity,
    )
    _bind_json(args.run_dir / "plan.json", plan)
    report = {
        "runner": plan["runner"],
        "status": "ready",
        "plan": plan,
        "publication_ready": False,
        "independent_blind_evaluation": False,
        "aml_academic_model_compliant": False,
        "production_query_engine_executed": False,
        "graph_executed": False,
    }
    if args.live:
        key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "")
        if not args.cache_only and not key:
            parser.error("DEEPSEEK_API_KEY unavailable")
        try:
            report.update(
                asyncio.run(
                    run(
                        cases,
                        manifest,
                        plan,
                        run_dir=args.run_dir,
                        parent_dir=args.parent_dir,
                        cache_dirs=args.parent_cache_dir,
                        dsn=local_diagnostic_dsn("doppel-ablation-pgvector"),
                        api_key=key,
                        embedding_cache_dir=args.embedding_cache_dir,
                        reranker=reranker,
                        cache_only=args.cache_only,
                    )
                )
            )
        except Exception as exc:  # noqa: BLE001 - never serialize provider/DSN text
            report.update(
                {
                    "status": "failed",
                    "failure_type": type(exc).__name__,
                    "usage": "consult stage ledgers; unknown is not zero",
                }
            )
    report["execution_metadata"] = execution_metadata()
    preserved = file_sha(args.parent_dir / "ingestion.sqlite3") == plan[
        "parent_journal_sha256"
    ] and all(
        cache_inventory(p) == expected
        for p, expected in zip(args.parent_cache_dir, inventories, strict=True)
    )
    report["parent_artifacts_preserved"] = preserved
    if not preserved:
        report["status"] = "failed"
    save(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "summary": report.get("answers", {}).get("summary"),
                "output": str(args.output),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if report["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
