from __future__ import annotations

from copy import deepcopy

import pytest

from benchmarks import public_memory_fresh_cohort as experiment
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_pilot import _hash, build_manifest

SHA = "a" * 64


def dataset():
    types = [
        "single-session-user",
        "single-session-assistant",
        "single-session-preference",
        "multi-session",
        "temporal-reasoning",
        "knowledge-update",
    ]
    result = []
    for n in range(42):
        result.append(
            {
                "question_id": f"case-{n}" + ("_abs" if n >= 36 else ""),
                "question_type": types[n % len(types)],
                "question": "PRIVATE QUESTION",
                "question_date": "2026/02/01 (Sun) 12:00",
                "answer": "PRIVATE GOLD",
                "answer_session_ids": [f"session-{n}"],
                "haystack_dates": ["2026/01/01 (Thu) 12:00"],
                "haystack_session_ids": [f"session-{n}"],
                "haystack_sessions": [
                    [
                        {
                            "role": "user",
                            "content": f"Generic source {n}",
                            "has_answer": True,
                        }
                    ]
                ],
            }
        )
    return result


def prior(records):
    return build_manifest(
        records,
        dataset_namespace=experiment.NAMESPACE,
        run_namespace="prior",
        source_sha256=SHA,
        diagnostic_count=1,
        reserved_count=1,
    )


def observation(identity):
    plan = {"binding": {"source": SHA}}
    plan["plan_fingerprint"] = _hash(plan)
    return {
        "plan": plan,
        "rows": [{"case_id": identity, "score": True, "answer": "PRIVATE GOLD"}],
    }


def test_projection_never_copies_question_gold_or_evidence_labels():
    raw = dataset()[0]
    clean = experiment.sampling_projection(raw)
    assert clean["question"] != raw["question"] and clean["answer"] != raw["answer"]
    assert clean["answer_session_ids"] == []
    assert "has_answer" not in clean["haystack_sessions"][0][0]
    assert (
        clean["haystack_sessions"][0][0]["content"]
        == raw["haystack_sessions"][0][0]["content"]
    )


def test_fresh_cases_exclude_old_development_reserved_and_additional_opened():
    raw = dataset()
    old = prior(raw)
    old_ids = {c["case_id"] for c in old["cases"]}
    extra = next(r["question_id"] for r in raw if r["question_id"] not in old_ids)
    manifest, ingestion = experiment.prepare(
        raw,
        source_sha=SHA,
        priors=[old],
        observed=[observation(extra)],
        count=7,
        reserved=2,
    )
    selected = {c["case_id"] for c in manifest["cases"]}
    assert selected.isdisjoint(old_ids | {extra})
    assert len(manifest["excluded_history_groups"]) == 3
    assert len([c for c in manifest["cases"] if c["partition"] == "diagnostic"]) == 7
    assert (
        len([c for c in manifest["cases"] if c["partition"] == "reserved-not-run"]) == 2
    )
    assert (
        ingestion["scope_count"] == 7
        and ingestion["max_calls"] == ingestion["total_chunks"]
    )
    assert not manifest["independently_blind"]


def test_selection_invariant_to_answers_questions_scores_and_turn_labels():
    raw = dataset()
    old = prior(raw)
    a, ingestion_a = experiment.prepare(
        raw, source_sha=SHA, priors=[old], observed=[], count=7, reserved=2
    )
    changed = deepcopy(raw)
    for item in changed:
        item["question"] = "CHANGED QUESTION"
        item["answer"] = {"invalid_for_scoring": "DO NOT READ"}
        item["answer_session_ids"] = ["not-in-source"]
        item["haystack_sessions"][0][0]["has_answer"] = "invalid annotation"
    b, ingestion_b = experiment.prepare(
        changed, source_sha=SHA, priors=[old], observed=[], count=7, reserved=2
    )
    assert a == b and ingestion_a == ingestion_b


def test_source_runtime_payload_matches_original_despite_query_redaction():
    raw = dataset()[0]
    original = prepare_case(raw, dataset_namespace=experiment.NAMESPACE)
    redacted = prepare_case(
        experiment.sampling_projection(raw), dataset_namespace=experiment.NAMESPACE
    )
    assert original.runtime.sessions == redacted.runtime.sessions
    assert original.runtime.user_id == redacted.runtime.user_id
    assert original.runtime.ingestion_chunks() == redacted.runtime.ingestion_chunks()


def test_frozen_profile_is_full_not_graphless_and_live_is_not_silently_authorized():
    raw = dataset()
    manifest, ingestion = experiment.prepare(
        raw, source_sha=SHA, priors=[prior(raw)], observed=[], count=7, reserved=2
    )
    plan = experiment.build_plan(manifest, ingestion, input_bindings={"dataset": SHA})
    assert plan["profiles"] == ["full_high_config", "raw_vector_reranked"]
    assert not plan["query_config"]["semantic_fallback_to_lexical"]
    assert not plan["query_config"]["relation_fallback_to_nonrelation"]
    assert plan["max_query_calls"] == 7 * 8
    assert plan["graph_and_schema_call_limits"] is None
    assert not plan["live_execution_authorized_by_this_preflight"]
    assert plan["clock_policy"] == "provided-history-v1"
    assert plan["ingestion_plan"]["analyzer"][1] == "8"
    assert plan["ingestion_plan"]["consolidator"][1] == "5"
    assert plan["reader_instructions_sha256"] and plan["source_sha256"]
    assert "PRIVATE GOLD" not in str(plan) and "PRIVATE QUESTION" not in str(plan)


@pytest.mark.parametrize("failure", ["fingerprint", "source", "opened", "duplicate"])
def test_invalid_exclusion_or_source_fails_closed(failure):
    raw = dataset()
    old = prior(raw)
    observed = []
    if failure == "fingerprint":
        old["seed"] += 1
    elif failure == "source":
        old["source_sha256"] = "b" * 64
        old["manifest_fingerprint"] = _hash(
            {k: v for k, v in old.items() if k != "manifest_fingerprint"}
        )
    elif failure == "opened":
        observed = [observation("missing")]
    else:
        raw.append(deepcopy(raw[0]))
    with pytest.raises(ValueError):
        experiment.prepare(
            raw, source_sha=SHA, priors=[old], observed=observed, count=7, reserved=2
        )
