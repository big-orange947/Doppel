from copy import deepcopy

from benchmarks.public_memory_rank_fusion import ARM_NAMES, score_arm, summarize


def items():
    return {
        f"m{i}": {
            "memory_id": f"m{i}",
            "scope_key": "owner",
            "text": "中文🙂" * 500,
            "actor": "owner",
            "authority": "human_self",
            "source_events": [f"e{i}"],
        }
        for i in range(25)
    }


def test_annotation_scoring_does_not_affect_order_or_packing():
    sources = items()
    snapshot = deepcopy(sources)
    order = list(sources)
    a = score_arm(order, sources, {"m0", "m24"})
    b = score_arm(order, sources, {"m19"})
    for field in (
        "full_order",
        "top20",
        "context",
        "context_sha256",
        "context_bytes",
        "packing_trace",
    ):
        assert a[field] == b[field]
    assert a["top20_annotated_ids"] == ["m0"]
    assert a["context_bytes"] <= 24000
    assert sources == snapshot


def test_summary_excludes_negatives_and_tracks_paired_losses():
    def row(negative=False):
        return {
            "abstention_label": negative,
            "annotated": 0 if negative else 2,
            "candidate_annotations": 0 if negative else 2,
            "arms": {
                name: {
                    "top20_annotated_ids": []
                    if negative
                    else ["a", "b"]
                    if name == "cross_encoder"
                    else ["b"],
                    "packed_annotated_ids": []
                    if negative
                    else ["a"]
                    if name == "cross_encoder"
                    else ["b"],
                    "context": [{}],
                    "context_bytes": 20,
                }
                for name in ARM_NAMES
            },
        }

    result = summarize([row(), row(True)])
    assert result["rank_fusion"]["cases"] == 2
    assert result["rank_fusion"]["positives"] == 1
    assert result["rank_fusion"]["annotations"] == 2
    assert result["rank_fusion"]["paired_vs_cross_encoder"]["packed"] == {
        "recovered": 1,
        "displaced": 1,
        "gain_questions": 0,
        "loss_questions": 0,
    }
    assert result["rank_fusion"]["paired_vs_cross_encoder"]["top20"]["displaced"] == 1
    assert result["rank_fusion"]["all_case_items"] == 2


def test_empty_failure_prefix_is_not_reported_as_complete_fifty():
    result = summarize([])
    assert all(result[name]["cases"] == 0 for name in ARM_NAMES)
    assert all(result[name]["annotations"] == 0 for name in ARM_NAMES)
