"""Execution/coverage observations, independent of answer correctness.

V2 is a new reporting contract, not a replacement score or permission to rewrite
V1 receipts. Unknown warnings require review rather than silently becoming green.
No question text, reference answer or evidence label enters classification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from benchmarks.public_memory_expansion import save
from benchmarks.public_memory_pilot import _hash

CONTRACT = "doppel.high-config-execution-contract.v2"
BOUNDED_WARNING = (
    "used bounded index-first lexical and semantic candidates; "
    "result is not an exhaustive scope snapshot"
)
INFORMATION = {
    BOUNDED_WARNING,
    "planner search_text was empty; used the raw query only for independent union candidate discovery",
    "explicit relation constraints produced no qualified relation evidence",
    "future as_of returns present evidence only; future actual state is unknown",
    "source_backing_limit_reached",
}
FAILURE_WARNINGS = {
    "memory_reranker_degraded",
    "path_reranker_degraded",
    "raw_reranker_degraded",
    "source_backing_incomplete",
}


def assess_execution(result: dict) -> dict:
    base = result["base"]
    warnings = list(
        dict.fromkeys([*base.get("warnings", []), *result.get("warnings", [])])
    )
    failures, informational, unknown = [], [], []
    count = base["count"]
    for warning in warnings:
        if warning in INFORMATION or (
            count["status"] == "indeterminate" and warning == count.get("reason")
        ):
            informational.append(warning)
        elif warning in FAILURE_WARNINGS or warning.startswith(
            (
                "memory_reranking_unavailable",
                "memory_reranking_limit_exceeded",
                "evidence_verification_unavailable",
                "evidence_verification_limit_exceeded",
                "semantic index unavailable; used lexical fallback:",
            )
        ):
            failures.append(warning)
        else:
            unknown.append(warning)
    memory = base.get("memory_reranking")
    if memory and memory["status"] not in {"completed", "not_run"}:
        failures.append("memory_reranker_status:" + memory["status"])
    if memory and memory["status"] == "not_run" and memory.get("offered_candidates", 0):
        failures.append("memory_reranker_not_run_with_offered_candidates")
    hybrid = result.get("hybrid")
    path = hybrid["path_reranking"] if hybrid else None
    if path and path["status"] == "fallback":
        failures.append("path_reranker_fallback")
    if result.get("source_failures", 0):
        failures.append("source_resolution_failures")
    if count["status"] == "exact" and not base["complete"]:
        failures.append("exact_count_without_complete_scope_read")
    # Nonexhaustive is not a failure, but neither is it proof of recall quality.
    coverage = (
        "exhaustive_scope_read"
        if base["complete"]
        else (
            "bounded_index_candidates"
            if BOUNDED_WARNING in warnings
            else "nonexhaustive_unspecified"
        )
    )
    return {
        "contract": CONTRACT,
        "execution_status": "degraded"
        if failures
        else "review_required"
        if unknown
        else "completed_within_contract",
        "execution_failures": list(dict.fromkeys(failures)),
        "information": informational,
        "unclassified_warnings": unknown,
        "retrieval_coverage": coverage,
        "source_coverage": "incomplete"
        if result.get("source_failures", 0)
        else "bounded"
        if "source_backing_limit_reached" in warnings
        else "resolved_for_returned_candidates",
        "aggregation_status": count["status"],
        "memory_reranker_status": memory["status"] if memory else "not_reported",
        "path_reranker_status": path["status"] if path else "not_applicable",
        "path_reranker_branch": "empty_candidate_set"
        if path and path["status"] == "not_run"
        else "count_branch"
        if not hybrid
        else "offered_paths",
        "graph_path_searches": result.get("graph_path_searches", 0),
        "graph_exploration_searches": result.get("graph_exploration_searches", 0),
        "promoted_path_count": len(hybrid.get("promoted_path_hits", []))
        if hybrid
        else 0,
        "answer_quality_assessed": False,
        "publication_acceptance_granted": False,
    }


def derive_receipt(parent: dict, sha: str) -> dict:
    payload = dict(parent["plan"])
    fingerprint = payload.pop("plan_fingerprint")
    if parent.get("status") != "complete" or _hash(payload) != fingerprint:
        raise ValueError("complete immutable bound receipt required")
    result = assess_execution(parent["retrieval"])
    integrity = {
        k: parent.get(k)
        for k in ["corpus_unchanged", "graph_unchanged", "vectors_unchanged"]
    }
    if not all(v is True for v in integrity.values()):
        result["execution_status"] = "integrity_failed"
    return {
        "runner": CONTRACT,
        "source_receipt_sha256": sha,
        "source_plan_fingerprint": fingerprint,
        "execution": result,
        "snapshot_integrity": integrity,
        "legacy_labels_unchanged": {
            k: parent.get(k) for k in ["degraded", "full_config_success"]
        },
        "answer_and_grade_unchanged_sha256": _hash(
            {
                k: parent[k]
                for k in ["reader", "task_grade", "citation_grade", "evidence_score"]
            }
        ),
        "new_provider_calls": 0,
        "parent_rewritten": False,
        "publication_ready": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = args.receipt.read_bytes()
    if args.output.exists() or args.receipt.resolve() == args.output.resolve():
        parser.error("preserve all existing receipts")
    result = derive_receipt(json.loads(original), hashlib.sha256(original).hexdigest())
    if args.receipt.read_bytes() != original:
        raise ValueError("parent changed during classification")
    save(args.output, result)
    print(json.dumps(result["execution"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
