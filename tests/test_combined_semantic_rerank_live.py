"""Contracts for the frozen combined semantic reranking ablation."""

from __future__ import annotations

from benchmarks.combined_semantic_rerank_live import (
    classify_baseline_rank,
    quality_gate,
    summarize,
)


def _row(case_id: str, ids: list[str], required: str) -> dict[str, object]:
    return {
        "case_id": case_id,
        "required": [required],
        "ids": ids,
        "scope_leakage": 0,
        "ineligible_hits": 0,
        "latency_ms": 1.0,
    }


def test_rank_classification_separates_recall_from_ranking() -> None:
    assert classify_baseline_rank(None, 64) == "score_gate_or_index_miss"
    assert classify_baseline_rank(1, 64) == "top_5"
    assert classify_baseline_rank(12, 64) == "ranking_error_in_context"
    assert classify_baseline_rank(21, 64) == "retrieved_outside_context"
    assert classify_baseline_rank(65, 64) == "outside_rerank_window"


def test_summary_uses_ranked_required_evidence() -> None:
    summary = summarize(
        [
            _row("a", ["required-a", "x"], "required-a"),
            _row("b", ["x", "required-b"], "required-b"),
            _row("c", ["x"], "required-c"),
        ]
    )

    assert summary["recall_at_1"] == 0.333333
    assert summary["recall_at_5"] == 0.666667
    assert summary["mrr"] == 0.5


def test_quality_gate_enforces_reorder_only_and_safety() -> None:
    baseline_rows = [
        _row(str(index), ["x"] * 11 + [f"r{index}"], f"r{index}")
        for index in range(36)
    ]
    baseline = summarize(baseline_rows)
    baseline.update(
        {"recall_at_5": 0.416667, "recall_at_10": 0.416667, "recall_at_20": 0.75}
    )
    reranked = summarize(
        [_row(str(index), [f"r{index}"], f"r{index}") for index in range(36)]
    )
    profiles = {
        "current_baseline": baseline,
        "expanded_baseline": baseline,
        "memory_reranked": reranked,
    }

    passed = quality_gate(
        profiles,
        candidate_recall_at_64=1.0,
        reorder_membership_violations=0,
        rerank_statuses={"completed": 36},
        postgres_reset=True,
    )
    failed = quality_gate(
        profiles,
        candidate_recall_at_64=1.0,
        reorder_membership_violations=1,
        rerank_statuses={"completed": 36},
        postgres_reset=True,
    )

    assert passed["ok"] is True
    assert failed["checks"]["reorder_membership"] is False
