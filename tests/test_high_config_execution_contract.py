from copy import deepcopy

import pytest

from benchmarks.high_config_execution_contract import (
    BOUNDED_WARNING,
    assess_execution,
    derive_receipt,
)
from benchmarks.public_memory_pilot import _hash


def result():
    return {
        "base": {
            "complete": False,
            "warnings": [BOUNDED_WARNING],
            "count": {"status": "not_requested"},
            "memory_reranking": {"status": "completed", "offered_candidates": 100},
        },
        "hybrid": {
            "path_reranking": {"status": "not_run", "hits": []},
            "promoted_path_hits": [],
        },
        "source_failures": 0,
        "graph_exploration_searches": 1,
    }


def test_normal_top_k_and_empty_path_branch_are_not_failures():
    before = result()
    output = assess_execution(before)
    assert output["execution_status"] == "completed_within_contract"
    assert output["retrieval_coverage"] == "bounded_index_candidates"
    assert output["path_reranker_branch"] == "empty_candidate_set"
    assert not output["publication_acceptance_granted"]
    assert before == result()


@pytest.mark.parametrize(
    "warning",
    [
        "raw_reranker_degraded",
        "source_backing_incomplete",
        "memory_reranking_limit_exceeded",
    ],
)
def test_actual_degradation_not_hidden_by_bounded_warning(warning):
    r = result()
    r["warnings"] = [warning]
    assert assess_execution(r)["execution_status"] == "degraded"


def test_unknown_warning_requires_review():
    r = result()
    r["warnings"] = ["future_unknown_condition"]
    output = assess_execution(r)
    assert output["execution_status"] == "review_required"
    assert output["unclassified_warnings"] == ["future_unknown_condition"]


@pytest.mark.parametrize(
    "warning",
    [
        "current/as-of candidates lack topic identity; conflict status unassessed",
        "multiple current/as-of assertions in topic opaque-slot; semantic compatibility unassessed",
    ],
)
def test_ambiguity_metadata_limit_is_not_quietly_whitelisted(warning):
    r = result()
    r["warnings"] = [warning]
    output = assess_execution(r)
    assert output["execution_status"] == "review_required"
    assert output["unclassified_warnings"] == [warning]
    assert not output["publication_acceptance_granted"]


def test_bounded_source_coverage_not_claimed_exhaustive():
    r = result()
    r["warnings"] = ["source_backing_limit_reached"]
    output = assess_execution(r)
    assert output["source_coverage"] == "bounded"
    assert output["execution_status"] == "completed_within_contract"


def test_exact_count_requires_full_scope_even_if_answer_correct():
    r = result()
    r["base"]["count"] = {"status": "exact"}
    assert (
        "exact_count_without_complete_scope_read"
        in assess_execution(r)["execution_failures"]
    )
    r["base"]["complete"] = True
    assert assess_execution(r)["aggregation_status"] == "exact"


def test_derived_receipt_preserves_old_labels_and_scores():
    plan = {"fixed": "source"}
    plan["plan_fingerprint"] = _hash(plan)
    parent = {
        "plan": plan,
        "status": "complete",
        "retrieval": result(),
        "degraded": True,
        "full_config_success": False,
        "corpus_unchanged": True,
        "vectors_unchanged": True,
        "graph_unchanged": True,
        "reader": {"answer": "unchanged"},
        "task_grade": {"answer_correct": False},
        "citation_grade": {},
        "evidence_score": {},
    }
    before = deepcopy(parent)
    derived = derive_receipt(parent, "sha")
    assert parent == before
    assert derived["legacy_labels_unchanged"] == {
        "degraded": True,
        "full_config_success": False,
    }
    assert derived["execution"]["execution_status"] == "completed_within_contract"
    parent["vectors_unchanged"] = False
    assert (
        derive_receipt(parent, "sha")["execution"]["execution_status"]
        == "integrity_failed"
    )
