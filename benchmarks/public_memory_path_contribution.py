"""Offline descriptive path contribution, never a graph-off ablation or judge.

Reads immutable completed query receipts only. It does not retrieve, rerank, pack,
call providers, inspect gold or claim that cited records imply a correct answer.
The base branch may itself use graph relation retrieval; base != pure vector.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from benchmarks.public_memory_pilot import _hash


def contribution(receipt):
    if receipt.get("status") != "complete" or receipt.get("runner") != (
        "doppel.public-memory-consecutive-high-config-query.v3"
    ):
        raise ValueError("completed V3 query receipt required")
    if not all(
        receipt.get(k) is True
        for k in ("corpus_unchanged", "vectors_unchanged", "graph_unchanged")
    ):
        raise ValueError("source integrity checks required")
    plan = receipt["plan"]
    if (
        _hash({k: v for k, v in plan.items() if k != "plan_fingerprint"})
        != plan["plan_fingerprint"]
    ):
        raise ValueError("plan fingerprint mismatch")
    retrieval = receipt["retrieval"]
    base = {h["record"]["memory_id"] for h in retrieval["base"]["hits"]}
    context = [i["memory_id"] for i in receipt["context"]]
    cited = receipt["reader"]["cited_memory_ids"]
    if len(set(context)) != len(context) or len(set(cited)) != len(cited):
        raise ValueError("duplicate context or citation identity")
    if not set(cited) <= set(context):
        raise ValueError("citation outside packed context")
    hybrid = retrieval.get("hybrid")
    candidates = hybrid["assembly"]["candidates"] if hybrid else []
    path_supported, only_path = set(), set()
    identities = set()
    for item in candidates:
        identity = item["record"]["memory_id"]
        if identity in identities:
            raise ValueError("duplicate assembled identity")
        identities.add(identity)
        # Reject a contradictory reported rank rather than deriving attribution
        # from rank metadata alone. This audit does not validate graph semantics.
        if (item.get("base_rank") is not None) != (identity in base):
            raise ValueError("base rank and actual base membership disagree")
        if item["path_ids"]:
            path_supported.add(identity)
            if identity not in base:
                only_path.add(identity)
    packed, citations = set(context), set(cited)
    return {
        "case_id": receipt["case_id"],
        "scope_ordinal": receipt["scope_ordinal"],
        "query_plan_fingerprint": plan["plan_fingerprint"],
        "base_is_graph_free": False,
        "counterfactual_executed": False,
        "answer_quality_assessed": False,
        "graph_uplift_demonstrated": False,
        "semantic_truth_verified": False,
        "publication_ready": False,
        "base_candidate_count": len(base),
        "assembled_candidate_count": len(identities),
        "path_supported_ids": sorted(path_supported),
        "path_added_to_base_ids": sorted(only_path),
        "packed_path_supported_ids": sorted(path_supported & packed),
        "packed_path_added_to_base_ids": sorted(only_path & packed),
        "cited_path_supported_ids": sorted(path_supported & citations),
        "cited_path_added_to_base_ids": sorted(only_path & citations),
        "limitations": [
            "base includes configured lexical/vector/graph-relation branches",
            "no graph-off retrieval, repacking or reader counterfactual",
            "path-added IDs need not be relevant or necessary for an answer",
            "original citations do not prove path necessity or task accuracy",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, action="append", required=True)
    args = parser.parse_args()
    results = []
    for path in args.receipt:
        raw = path.read_bytes()
        results.append(
            {
                "receipt_sha256": hashlib.sha256(raw).hexdigest(),
                **contribution(json.loads(raw)),
            }
        )
    print(
        json.dumps(
            {
                "runner": "doppel.public-memory-path-contribution.v1",
                "provider_calls": 0,
                "results": results,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
