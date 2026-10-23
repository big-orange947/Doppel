import copy

import pytest

from benchmarks.public_memory_comparison import pack_ranked_fit
from benchmarks.public_memory_packing_replay import compare, stage_totals, summarize


def items():
    return [
        {
            "scope_key": "s" * 68,
            "memory_id": str(i),
            "text": "x" * 3000,
            "role": "user",
            "actor": "owner",
            "authority": "human_self",
            "observed_at": "2024-01-01",
            "source_events": [str(i)],
            "channel": "raw",
            "temporal_status": None,
            "valid_from": None,
            "valid_to": None,
        }
        for i in range(20)
    ]


def test_policies_do_not_see_or_change_annotations_and_exact_baseline_required():
    ranked = items()
    original, _ = pack_ranked_fit(ranked)
    before = copy.deepcopy(ranked)
    first = compare(ranked, original, ["19"])
    second = compare(ranked, original, ["0", "1"])
    assert ranked == before
    for policy in first:
        assert first[policy]["selected_ids"] == second[policy]["selected_ids"]
    with pytest.raises(ValueError, match="exact context"):
        compare(ranked, original[:-1], [])


def test_summary_and_negative_denominators_are_not_qa_scores():
    ranked = items()
    original, _ = pack_ranked_fit(ranked)
    positive = compare(ranked, original, ["0"])
    negative = compare(ranked, original, [])
    result = summarize([{"policies": positive}, {"policies": negative}])
    assert result["retain"]["positive_questions"] == 1
    assert result["retain"]["annotated_count"] == 1
    assert result["retain"]["coverage_loss_questions"] == 0
    coverage = {"annotated_turn_count": 2, "annotated_turn_hits": 1}
    totals = stage_totals(
        [
            {
                k: coverage
                for k in ("candidate_coverage", "retrieved_coverage", "packed_coverage")
            }
        ]
    )
    assert totals["packed_coverage"] == {"hits": 1, "annotated": 2, "recall": 0.5}


def test_negative_annotations_are_not_positive_recall_or_an_automatic_success():
    coverage = {
        "annotated_turn_count": 1,
        "annotated_turn_hits": 1,
        "abstention_label": True,
    }
    row = {
        k: coverage
        for k in ("candidate_coverage", "retrieved_coverage", "packed_coverage")
    }
    assert stage_totals([row])["packed_coverage"] == {
        "hits": 0,
        "annotated": 0,
        "recall": None,
    }
