"""Regression tests for additive metrics, not relaxed benchmark gold."""
import hashlib
import json
from types import SimpleNamespace

from benchmarks.personal_retrieval_ablation import (
    PLANNER_MODE_REPORT,
    _build_relation_final_hit_attribution,
    _evaluate_result,
    _graded_relevance,
)
from doppel_memory import MemoryScope
from tests.test_personal_retrieval_ablation import _dataset, _hit, _query


def test_graded_judgments_never_inferred_from_legacy_gold():
    query = _query(required=["direct"], forbidden=["clue"])
    assert not _graded_relevance(query, ["direct"])["available"]
    query = query.model_copy(update={"relevance_grades": {"direct": 2, "clue": 1}})
    assert _graded_relevance(query, ["direct", "clue"])["ndcg_at_5"] == 1
    assert 0 < _graded_relevance(query, ["clue", "direct"])["ndcg_at_5"] < 1
    assert not _graded_relevance(query, ["unknown"])["available"]
    assert _graded_relevance(query, [])["ndcg_at_5"] == 0
    assert query.forbidden_memory_ids == ["clue"]


def test_unannotated_dataset_fingerprint_unchanged():
    dataset = _dataset()
    original = dataset.model_dump(mode="json")
    for query in original["queries"]:
        query.pop("relevance_grades")
        query.pop("retrieval_expectation")
    assert dataset.fingerprint == hashlib.sha256(json.dumps(
        original, ensure_ascii=False, sort_keys=True
    ).encode()).hexdigest()
    modified = dataset.model_copy(update={"queries": [
        dataset.queries[0].model_copy(update={"relevance_grades": {
            dataset.fixtures[0].memory_id: 2
        }}), *dataset.queries[1:]
    ]})
    assert modified.fingerprint != dataset.fingerprint
    explicit_expectation = dataset.model_copy(update={"queries": [
        dataset.queries[0].model_copy(update={
            "retrieval_expectation": "no_evidence"
        }), *dataset.queries[1:]
    ]})
    assert explicit_expectation.fingerprint != dataset.fingerprint


def test_single_source_attribution_requires_positive_score_not_just_profile():
    scope = MemoryScope(user_id="u1", agent_id="test")
    hit = _hit("m", scope=scope)
    result = SimpleNamespace(
        plan=SimpleNamespace(intent="current", as_of=None), hits=[hit],
        count=SimpleNamespace(status="not_requested", value=None), ambiguous=False,
        warnings=[],
    )
    def evaluate(profile):
        return _evaluate_result(result, _query(forbidden=["m"]), profile, 1,
                                allowed_scope_keys={scope.scope_key})
    assert evaluate("lexical_vector")["contribution"]["vector"] == 1
    assert evaluate("lexical_vector_graph")["contribution"]["vector"] == 0
    assert evaluate("lexical_vector")["forbidden"] == ["m"]
    assert evaluate("lexical_vector")["security_failures"] == []
    hit.semantic_score = 0
    assert evaluate("lexical_vector")["contribution"]["vector"] == 0


def test_relation_report_mode_not_hidden_and_not_mixed_with_oracle():
    dataset = _dataset()
    query = dataset.queries[0]
    report = {"cases": [{
        "mode": PLANNER_MODE_REPORT, "profile": "lexical_relation",
        "query_id": query.query_id, "hit_scores": [{
            "memory_id": query.required_memory_ids[0],
            "reasons": ["relation_match", "relation_edge:edge"],
        }],
    }]}
    attribution = _build_relation_final_hit_attribution(report=report, dataset=dataset)
    assert attribution["available"]
    assert not attribution["legacy_oracle_available"]
    assert attribution["per_mode"][PLANNER_MODE_REPORT]["correct_relation_final_hit_links"] == 1
