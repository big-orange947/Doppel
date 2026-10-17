from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_retrieval_packing as audit
from benchmarks.public_memory_retrieval_expansion import build_plan, prepare
from tests.test_public_memory_retrieval_expansion import bound


def receipt():
    raw, parent_manifest = bound()
    cases, manifest = prepare(
        raw, parent_manifest, source_sha=parent_manifest["source_sha256"]
    )
    plan = build_plan(manifest, SimpleNamespace(report=dict))
    rows = []
    for _, scoring in cases:
        positions = list(scoring.evidence_turns)
        score = audit.score_evidence(scoring, positions)
        for profile in plan["profiles"]:
            rows.append(
                {
                    "case_id": scoring.case_id,
                    "profile": profile,
                    "hits": len(positions),
                    "retrieved_source_positions": positions,
                    "at_20": score,
                    "at_5": score,
                }
            )
    parent = {
        "runner": audit.PARENT_RUNNER,
        "status": "complete",
        "plan": plan,
        "rows": rows,
        "blocks": [{"rows": rows}],
        "llm_calls": 0,
        "provider_tokens": 0,
        "graph_calls": 0,
    }
    return cases, manifest, parent


def test_frozen_plan_has_zero_models_and_binds_all_rows_and_bytes():
    _, manifest, parent = receipt()
    plan = audit.build_plan(parent, manifest, {"retrieval_report": "original"})
    assert plan["expected_rows"] == 160 and plan["context_byte_limit"] == 24000
    assert plan["llm_calls"] == plan["graph_calls"] == 0
    assert plan["retrieval_rerun"] is False
    assert "PRIVATE GOLD" not in str(plan)
    changed = audit.build_plan(parent, manifest, {"retrieval_report": "different"})
    assert changed["plan_fingerprint"] != plan["plan_fingerprint"]


@pytest.mark.parametrize(
    "mutation", ["duplicate", "missing", "blocks", "status", "provider", "runtime"]
)
def test_incomplete_or_changed_retrieval_receipt_rejected(mutation):
    _, manifest, original = receipt()
    parent = deepcopy(original)
    if mutation == "duplicate":
        parent["rows"][0] = deepcopy(parent["rows"][1])
    elif mutation == "missing":
        parent["rows"].pop()
    elif mutation == "blocks":
        parent["blocks"] = []
    elif mutation == "status":
        parent["status"] = "failed"
    elif mutation == "provider":
        parent["llm_calls"] = 1
    else:
        parent["plan"]["runtime_source_sha256"] = "changed"
        parent["plan"]["plan_fingerprint"] = audit._hash(
            {k: v for k, v in parent["plan"].items() if k != "plan_fingerprint"}
        )
    with pytest.raises(ValueError):
        audit.build_plan(parent, manifest, {})


def scoring(negative=False):
    return SimpleNamespace(evidence_turns=((0, 1),), abstention=negative)


def row_for(positions, score):
    return {
        "case_id": "generic",
        "profile": "fixed",
        "hits": len(positions),
        "retrieved_source_positions": positions,
        "at_20": audit.score_evidence(score, positions),
        "at_5": audit.score_evidence(score, positions[:5]),
    }


def test_packing_stops_at_first_overflow_without_gold_skip_or_text_truncation():
    score = scoring()
    items = {
        (0, 0): {"text": "small"},
        (0, 1): {"text": "中" * 9000},
        (0, 2): {"text": "would fit but must not skip"},
    }
    original = deepcopy(items)
    result = audit.audit_row(row_for(list(items), score), score, items)
    assert result["before"]["annotated_turn_hits"] == 1
    assert result["after"]["annotated_turn_hits"] == 0
    assert result["packed_count"] == 1 and result["first_excluded_rank"] == 2
    assert result["lost_labelled_positions"] == [[0, 1]]
    assert result["text_modified"] is False and items == original
    assert result["packed_context_bytes"] == len(audit.encoded([items[(0, 0)]]))


def test_utf8_exact_boundary_and_empty_first_item_overflow():
    score = scoring()
    overhead = len(audit.encoded([{"text": ""}]))
    item = {"text": "x" * (24000 - overhead)}
    row = row_for([(0, 1)], score)
    assert audit.audit_row(row, score, {(0, 1): item})["packed_context_bytes"] == 24000
    item["text"] += "x"
    result = audit.audit_row(row, score, {(0, 1): item})
    assert result["packed_count"] == 0 and result["packed_context_bytes"] == 2


@pytest.mark.parametrize("mutation", ["duplicate", "unknown", "count", "score"])
def test_ranking_source_and_old_scores_cannot_silently_change(mutation):
    score = scoring()
    row = row_for([(0, 1)], score)
    if mutation == "duplicate":
        row["retrieved_source_positions"] *= 2
        row["hits"] = 2
    elif mutation == "unknown":
        row["retrieved_source_positions"] = [(1, 0)]
    elif mutation == "count":
        row["hits"] = 0
    else:
        row["at_20"]["annotated_turn_hits"] = 0
    with pytest.raises(ValueError):
        audit.audit_row(row, score, {(0, 1): {"text": "source"}})


def test_negative_related_annotations_are_not_answer_support():
    rows = []
    for negative in (False, True):
        score = scoring(negative)
        result = audit.audit_row(
            row_for([(0, 1)], score), score, {(0, 1): {"text": "source"}}
        )
        rows.append(result)
    summary = audit.summarize(rows)["fixed"]
    assert summary["questions"] == 2 and summary["negative_questions"] == 1
    assert summary["annotated_turns"] == summary["after_hits"] == 1
    assert summary["all_required_after"] == 1
