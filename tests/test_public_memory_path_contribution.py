from copy import deepcopy

import pytest

from benchmarks.public_memory_path_contribution import contribution
from benchmarks.public_memory_pilot import _hash


def receipt():
    plan = {"protocol": "synthetic"}
    plan["plan_fingerprint"] = _hash(plan)
    return {
        "runner": "doppel.public-memory-consecutive-high-config-query.v3",
        "status": "complete",
        "plan": plan,
        "scope_ordinal": 4,
        "case_id": "synthetic",
        "corpus_unchanged": True,
        "vectors_unchanged": True,
        "graph_unchanged": True,
        "context": [{"memory_id": "a"}, {"memory_id": "b"}],
        "reader": {"cited_memory_ids": ["a"]},
        "retrieval": {
            "base": {"hits": [{"record": {"memory_id": "a"}}]},
            "hybrid": {
                "assembly": {
                    "candidates": [
                        {
                            "record": {"memory_id": "a"},
                            "base_rank": 1,
                            "path_ids": ["p"],
                        },
                        {
                            "record": {"memory_id": "b"},
                            "base_rank": None,
                            "path_ids": ["q"],
                        },
                    ]
                }
            },
        },
    }


def test_descriptive_membership_not_graph_uplift_or_semantic_truth():
    r = receipt()
    before = deepcopy(r)
    result = contribution(r)
    assert r == before
    assert result["path_added_to_base_ids"] == ["b"]
    assert result["packed_path_added_to_base_ids"] == ["b"]
    assert result["cited_path_added_to_base_ids"] == []
    assert result["cited_path_supported_ids"] == ["a"]
    for key in (
        "base_is_graph_free",
        "counterfactual_executed",
        "graph_uplift_demonstrated",
        "semantic_truth_verified",
        "answer_quality_assessed",
        "publication_ready",
    ):
        assert result[key] is False


def test_citing_new_path_record_still_does_not_prove_necessity():
    r = receipt()
    r["reader"]["cited_memory_ids"] = ["b"]
    result = contribution(r)
    assert result["cited_path_added_to_base_ids"] == ["b"]
    assert result["graph_uplift_demonstrated"] is False


def test_empty_path_branch_keeps_context_and_citation_checks():
    r = receipt()
    r["retrieval"]["hybrid"] = None
    assert contribution(r)["path_supported_ids"] == []


@pytest.mark.parametrize(
    "key", ["corpus_unchanged", "vectors_unchanged", "graph_unchanged"]
)
def test_require_source_integrity(key):
    r = receipt()
    r[key] = False
    with pytest.raises(ValueError, match="integrity"):
        contribution(r)


@pytest.mark.parametrize(
    "mutation", ["partial", "fingerprint", "citation", "duplicate", "rank"]
)
def test_reject_invalid_or_inconsistent_receipts(mutation):
    r = receipt()
    if mutation == "partial":
        r["status"] = "failed"
    elif mutation == "fingerprint":
        r["plan"]["protocol"] = "changed"
    elif mutation == "citation":
        r["reader"]["cited_memory_ids"] = ["missing"]
    elif mutation == "duplicate":
        r["context"].append({"memory_id": "a"})
    else:
        r["retrieval"]["hybrid"]["assembly"]["candidates"][1]["base_rank"] = 2
    with pytest.raises(ValueError):
        contribution(r)
