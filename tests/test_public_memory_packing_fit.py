from __future__ import annotations

from copy import deepcopy

import pytest

from benchmarks import public_memory_packing_fit as fit
from tests.test_public_memory_retrieval_packing import receipt, row_for, scoring


def baseline():
    _, manifest, parent = receipt()
    binding = {k: k for k in ("dataset", "parent_manifest", "retrieval_report")}
    plan = fit.prefix.build_plan(parent, manifest, binding)
    return (
        parent,
        manifest,
        binding,
        {
            "runner": fit.prefix.RUNNER,
            "status": "complete",
            "plan": plan,
            "rows": [{} for _ in range(160)],
            "llm_calls": 0,
            "graph_calls": 0,
        },
    )


def test_fixed_plan_reuses_twenty_not_eighty_candidates_and_budget():
    parent, manifest, binding, old = baseline()
    plan = fit.make_plan(parent, old, manifest, binding)
    assert plan["input_window"] == plan["item_limit"] == 20
    assert plan["context_byte_limit"] == 24000 and plan["llm_calls"] == 0
    assert plan["new_ranking"] is plan["source_expansion"] is False


@pytest.mark.parametrize("mutation", ["binding", "status", "rows"])
def test_changed_baseline_rejected(mutation):
    parent, manifest, binding, old = baseline()
    if mutation == "binding":
        binding["dataset"] = "different"
    elif mutation == "status":
        old["status"] = "failed"
    else:
        old["rows"].pop()
    with pytest.raises(ValueError):
        fit.make_plan(parent, old, manifest, binding)


def test_fit_adds_short_later_item_without_changing_prefix_text_or_order():
    score = scoring()
    items = {
        (0, 0): {"text": "x" * 23000},
        (0, 2): {"text": "y" * 2000},
        (0, 1): {"text": "later evidence"},
    }
    original = deepcopy(items)
    row = row_for(list(items), score)
    previous = fit.prefix.audit_row(row, score, items)
    result = fit.compare_row(row, score, items, previous)
    assert result["prefix"]["after"]["annotated_turn_hits"] == 0
    assert result["ranked_fit"]["after"]["annotated_turn_hits"] == 1
    assert result["ranked_fit"]["packing_trace"]["selected_rank_positions"] == [1, 3]
    assert result["ranked_fit"]["packed_context_bytes"] <= 24000
    assert items == original and result["prefix"] == previous


def test_individually_oversized_evidence_is_not_truncated_or_recovered():
    score = scoring()
    items = {(0, 1): {"text": "中" * 9000}, (0, 0): {"text": "short unrelated"}}
    row = row_for(list(items), score)
    previous = fit.prefix.audit_row(row, score, items)
    result = fit.compare_row(row, score, items, previous)
    assert result["ranked_fit"]["packed_count"] == 1
    assert result["ranked_fit"]["after"]["annotated_turn_hits"] == 0
    assert result["ranked_fit"]["lost_labelled_positions"] == [[0, 1]]


def test_baseline_must_match_exactly_not_just_recall():
    score = scoring()
    items = {(0, 1): {"text": "source"}}
    row = row_for(list(items), score)
    old = fit.prefix.audit_row(row, score, items)
    old["packed_context_sha256"] = "changed"
    with pytest.raises(ValueError, match="exactly reproduced"):
        fit.compare_row(row, score, items, old)
