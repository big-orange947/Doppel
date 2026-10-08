"""Frozen zero-provider paired packing diagnostic on completed public histories."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from benchmarks.public_context_baseline import select_diagnostic_cases
from benchmarks.public_context_rerank import (
    LocalContextCrossEncoder,
    StrictContextReranker,
)
from benchmarks.public_memory_comparison import run_comparison
from benchmarks.public_memory_expansion import local_diagnostic_dsn, save
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_recovery import file_sha

RUNNER = "doppel.public-memory-packing.v1"
PROFILES = ("raw_vector_reranked", "memory_vector_reranked", "combined_vector_reranked")


def build_plan(
    parent: Mapping[str, Any], *, input_sha256: Mapping[str, str]
) -> dict[str, Any]:
    if (
        parent.get("status") != "complete"
        or parent.get("parent_artifacts_preserved") is not True
        or parent["ingestion"].get("all_histories_ingested") is not True
        or len(parent["retrieval"]["rows"]) != 30
        or parent["retrieval"].get("status") != "complete"
        or parent["retrieval"]["budget"]
        != {
            "candidate_items": 80,
            "final_items": 20,
            "serialized_context_utf8_bytes": 24_000,
            "reader_tokens_matched": False,
        }
    ):
        raise ValueError("complete ten-history parent required")
    identities = {(r["case_id"], r["profile"]) for r in parent["retrieval"]["rows"]}
    case_ids = {case for case, _ in identities}
    if len(case_ids) != 10 or identities != {
        (case, profile) for case in case_ids for profile in PROFILES
    }:
        raise ValueError("exact ten-question three-channel row set required")
    value = {
        "runner": RUNNER,
        "input_sha256": dict(input_sha256),
        "source_sha256": {
            name: file_sha(Path(__file__).with_name(name))
            for name in (
                "public_memory_packing.py",
                "public_memory_comparison.py",
                "public_context_rerank.py",
            )
        },
        "parent_plan_fingerprint": parent["plan"]["plan_fingerprint"],
        "ingestion_plan_fingerprint": parent["ingestion"]["plan"]["plan_fingerprint"],
        "policies": ["rank_prefix", "ranked_fit"],
        "ranking": "one-shared-full-80-candidate-order-per-question-and-channel",
        "budget": parent["retrieval"]["budget"],
        "reranker_identity": {
            key: parent["retrieval"]["reranker"][key]
            for key in (
                "name",
                "version",
                "model_artifact_sha256",
                "max_length",
                "batch_size",
            )
        },
        "expected_questions": 10,
        "expected_rows": 60,
        "max_provider_calls": 0,
        "core_default_changed": False,
        "source_expansion_executed": False,
        "score_scope": "opened-public-development-provenance-not-answer-quality",
    }
    return {**value, "plan_fingerprint": _hash(value)}


def compare_packing(old: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, Any]:
    if old.get("status") != "complete" or new.get("status") != "complete":
        raise ValueError("complete comparisons required")
    baseline = {(r["case_id"], r["profile"]): r for r in old["rows"]}
    rows = {(r["case_id"], r["profile"]): r for r in new["rows"]}
    if len(baseline) != 30 or len(rows) != 60 or len(rows) != len(new["rows"]):
        raise ValueError("exact thirty paired rows required")
    expected = set(baseline) | {
        (case, profile + "_ranked_fit") for case, profile in baseline
    }
    if set(rows) != expected:
        raise ValueError("paired row identities differ")
    mismatches, dropped, changes = [], [], []
    for key, previous in baseline.items():
        prefix = {
            k: v
            for k, v in rows[key].items()
            if k not in {"packing_policy", "packing_trace"}
        }
        if prefix != previous:
            mismatches.append({"case_id": key[0], "profile": key[1]})
        fitted = rows[(key[0], key[1] + "_ranked_fit")]
        old_items = {i["memory_id"]: i for i in previous["context"]}
        new_items = {i["memory_id"]: i for i in fitted["context"]}
        before, after = set(old_items), set(new_items)
        if before - after or any(new_items.get(k) != v for k, v in old_items.items()):
            dropped.append({"case_id": key[0], "profile": key[1]})
        changes.append(
            {
                "case_id": key[0],
                "profile": key[1],
                "added_items": len(after - before),
                "before_bytes": previous["packed_context_bytes"],
                "after_bytes": fitted["packed_context_bytes"],
                "before_coverage": previous["packed_provenance_coverage"][
                    "annotated_turn_recall"
                ],
                "after_coverage": fitted["packed_provenance_coverage"][
                    "annotated_turn_recall"
                ],
            }
        )
    summary = {}
    for profile in PROFILES:
        for suffix in ("", "_ranked_fit"):
            selected = [r for r in new["rows"] if r["profile"] == profile + suffix]
            summary[profile + suffix] = {
                "questions": len(selected),
                "packed_turn_provenance_coverage": sum(
                    r["packed_provenance_coverage"]["annotated_turn_recall"]
                    for r in selected
                )
                / len(selected),
                "all_turns_covered": sum(
                    r["packed_provenance_coverage"]["annotated_turn_recall"] == 1
                    for r in selected
                ),
                "mean_packed_items": sum(r["packed_item_count"] for r in selected)
                / len(selected),
            }
    return {
        "baseline_reproduced": not mismatches,
        "baseline_mismatches": mismatches,
        "baseline_contexts_preserved": not dropped,
        "baseline_context_drop_rows": dropped,
        "paired_changes": changes,
        "summary": summary,
        "qa_metrics_available": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "manifest", "parent-report", "ingestion-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--reranker-model-path", type=Path, required=True)
    parser.add_argument("--embedding-cache-dir", type=Path)
    parser.add_argument("--frozen-plan", type=Path)
    parser.add_argument(
        "--live", action="store_true", help="local GPU/DB only; never LLM"
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("fresh output required; preserve previous reports")
    parent = json.loads(args.parent_report.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    hashes = {
        name: file_sha(path)
        for name, path in (
            ("dataset", args.dataset),
            ("manifest", args.manifest),
            ("parent_report", args.parent_report),
            ("journal", args.ingestion_dir / "ingestion.sqlite3"),
            ("ingestion_plan", args.ingestion_dir / "plan.json"),
        )
    }
    if hashes["dataset"] != manifest["source_sha256"] or (
        parent["plan"]["manifest_fingerprint"] != manifest["manifest_fingerprint"]
    ):
        parser.error("parent/dataset/manifest binding differs")
    plan = build_plan(parent, input_sha256=hashes)
    cases = select_diagnostic_cases(
        json.loads(args.dataset.read_text(encoding="utf-8")),
        manifest,
        source_sha256=hashes["dataset"],
    )
    report: dict[str, Any] = {
        "runner": RUNNER,
        "status": "preflight",
        "plan": plan,
        "provider_calls": 0,
        "provider_tokens": 0,
        "qa_metrics_available": False,
        "publication_ready": False,
    }
    if args.live:
        if args.frozen_plan is None or (
            json.loads(args.frozen_plan.read_text(encoding="utf-8"))["plan"] != plan
        ):
            parser.error("matching frozen preflight required before local execution")
        provider = LocalContextCrossEncoder(args.reranker_model_path, device="cuda")
        if any(provider.report()[k] != v for k, v in plan["reranker_identity"].items()):
            parser.error("reranker differs from frozen parent")
        try:
            comparison = asyncio.run(
                run_comparison(
                    cases,
                    manifest,
                    parent["ingestion"],
                    run_dir=args.ingestion_dir,
                    dsn=local_diagnostic_dsn("doppel-ablation-pgvector"),
                    embedding_cache_dir=args.embedding_cache_dir,
                    reranker=StrictContextReranker(provider),
                    profile_mode="reranked_only",
                    packing_experiment=True,
                )
            )
            paired = compare_packing(parent["retrieval"], comparison)
            report.update(comparison=comparison, paired=paired)
            report["status"] = (
                "complete"
                if (
                    paired["baseline_reproduced"]
                    and paired["baseline_contexts_preserved"]
                )
                else "invalid-paired-comparison"
            )
        except Exception as error:  # noqa: BLE001 - redact DB/provider details
            report.update(status="failed", failure_type=type(error).__name__)
    if file_sha(args.ingestion_dir / "ingestion.sqlite3") != hashes["journal"]:
        report["status"] = "source-journal-changed"
    report["inputs_preserved"] = all(
        file_sha(path) == hashes[name]
        for name, path in (
            ("dataset", args.dataset),
            ("manifest", args.manifest),
            ("parent_report", args.parent_report),
            ("journal", args.ingestion_dir / "ingestion.sqlite3"),
            ("ingestion_plan", args.ingestion_dir / "plan.json"),
        )
    )
    if not report["inputs_preserved"]:
        report["status"] = "input-artifact-changed"
    save(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "plan_fingerprint": plan["plan_fingerprint"],
                "output": str(args.output),
                "summary": report.get("paired", {}).get("summary"),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if report["status"] in {"preflight", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
