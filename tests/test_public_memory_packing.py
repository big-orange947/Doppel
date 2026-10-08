"""Synthetic packing behavior and paired-report integrity; no benchmark gold."""

from copy import deepcopy

import pytest

from benchmarks.public_memory_comparison import (
    CANDIDATE_LIMIT,
    CONTEXT_BYTE_LIMIT,
    ITEM_LIMIT,
    encoded,
    pack_context,
    pack_ranked_fit,
)
from benchmarks.public_memory_packing import PROFILES, build_plan, compare_packing


def item(index, text="short", **metadata):
    return {"memory_id": str(index), "text": text, **metadata}


def test_skip_whole_oversized_item_without_stopping_or_rewriting():
    items = [item(0), item(1, "x" * CONTEXT_BYTE_LIMIT), item(2)]
    before = deepcopy(items)
    assert pack_context(items) == items[:1]
    packed, trace = pack_ranked_fit(items)
    assert packed == [items[0], items[2]]
    assert trace["selected_rank_positions"] == [1, 3]
    assert trace["over_budget_rank_positions"] == [2]
    assert items == before
    assert trace["text_modified"] is False
    assert trace["source_expansion_executed"] is False


def test_empty_head_can_be_skipped_and_all_oversized_is_honest_empty():
    huge = item(0, "x" * CONTEXT_BYTE_LIMIT)
    assert pack_context([huge, item(1)]) == []
    assert pack_ranked_fit([huge, item(1)])[0] == [item(1)]
    assert pack_ranked_fit([huge] * 90)[0] == []
    assert pack_ranked_fit([])[0] == []


def test_shared_item_and_candidate_caps_and_late_item_discoverability():
    items = [item(i) for i in range(90)]
    packed, trace = pack_ranked_fit(items)
    assert len(packed) == ITEM_LIMIT
    assert trace["considered_candidates"] == ITEM_LIMIT
    items = [item(i, "x" * CONTEXT_BYTE_LIMIT) for i in range(79)] + [
        item(79),
        item(80),
    ]
    packed, trace = pack_ranked_fit(items)
    assert packed == [item(79)]
    assert trace["considered_candidates"] == CANDIDATE_LIMIT


def test_multibyte_and_metadata_count_toward_actual_serialized_cap():
    items = [item(i, "中文" * 1000, source_events=["source"] * 100) for i in range(80)]
    packed, _ = pack_ranked_fit(items)
    assert len(encoded(packed)) <= CONTEXT_BYTE_LIMIT
    assert len(encoded([*packed, items[len(packed)]])) > CONTEXT_BYTE_LIMIT
    assert pack_ranked_fit([item(0, source_events=["x" * 24000]), item(1)])[0] == [
        item(1)
    ]


def test_never_drops_prefix_and_preserves_authority_dates_and_ids():
    items = [
        item(
            i,
            "data" * (i * 100),
            role="assistant",
            authority="agent_output",
            observed_at="2024-01-01",
            source_events=[str(i)],
        )
        for i in range(80)
    ]
    prefix = pack_context(items)
    fitted, _ = pack_ranked_fit(items)
    assert fitted[: len(prefix)] == prefix
    assert all(i in items for i in fitted)
    assert all(i["authority"] == "agent_output" for i in fitted)


def comparisons():
    old = {"status": "complete", "rows": []}
    new = {"status": "complete", "rows": []}
    for case in range(10):
        for profile in PROFILES:
            base = {
                "case_id": str(case),
                "profile": profile,
                "context": [item(0)],
                "packed_context_bytes": len(encoded([item(0)])),
                "packed_item_count": 1,
                "packed_provenance_coverage": {"annotated_turn_recall": 0.5},
            }
            old["rows"].append(base)
            new["rows"].append(
                {
                    **deepcopy(base),
                    "packing_policy": "rank_prefix",
                    "packing_trace": None,
                }
            )
            new["rows"].append(
                {
                    **deepcopy(base),
                    "profile": profile + "_ranked_fit",
                    "context": [item(0), item(1)],
                    "packed_item_count": 2,
                    "packed_context_bytes": len(encoded([item(0), item(1)])),
                    "packed_provenance_coverage": {"annotated_turn_recall": 1},
                    "packing_policy": "ranked_fit",
                    "packing_trace": {},
                }
            )
    return old, new


def test_exact_baseline_required_and_no_answer_metrics_generated():
    old, new = comparisons()
    result = compare_packing(old, new)
    assert result["baseline_reproduced"] and result["baseline_contexts_preserved"]
    assert result["qa_metrics_available"] is False
    assert (
        result["summary"][PROFILES[0] + "_ranked_fit"][
            "packed_turn_provenance_coverage"
        ]
        == 1
    )
    assert all(c["added_items"] == 1 for c in result["paired_changes"])
    new["rows"][0]["context"][0]["text"] = "changed baseline"
    assert compare_packing(old, new)["baseline_reproduced"] is False


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "identity", "incomplete"])
def test_bad_pairs_cannot_be_comparisons(mutation):
    old, new = comparisons()
    if mutation == "missing":
        new["rows"].pop()
    elif mutation == "duplicate":
        new["rows"][1] = deepcopy(new["rows"][0])
    elif mutation == "identity":
        new["rows"][0]["case_id"] = "other"
    else:
        new["status"] = "failed"
    with pytest.raises(ValueError):
        compare_packing(old, new)


def test_fit_must_keep_exact_prefix_content_not_only_same_ids():
    old, new = comparisons()
    new["rows"][1]["context"][0]["authority"] = "human_self"
    assert compare_packing(old, new)["baseline_contexts_preserved"] is False


def parent():
    old, _ = comparisons()
    return {
        "status": "complete",
        "parent_artifacts_preserved": True,
        "plan": {"plan_fingerprint": "a" * 64},
        "ingestion": {
            "all_histories_ingested": True,
            "plan": {"plan_fingerprint": "b" * 64},
        },
        "retrieval": {
            **old,
            "budget": {
                "candidate_items": 80,
                "final_items": 20,
                "serialized_context_utf8_bytes": 24000,
                "reader_tokens_matched": False,
            },
            "reranker": {
                k: "synthetic"
                for k in (
                    "name",
                    "version",
                    "model_artifact_sha256",
                    "max_length",
                    "batch_size",
                )
            },
        },
    }


def test_frozen_zero_provider_budget_and_parent_hash_binding():
    plan = build_plan(parent(), input_sha256={"report": "x"})
    assert plan["max_provider_calls"] == 0
    assert plan["expected_rows"] == 60
    assert plan["core_default_changed"] is False
    assert (
        build_plan(parent(), input_sha256={"report": "y"})["plan_fingerprint"]
        != plan["plan_fingerprint"]
    )


@pytest.mark.parametrize("mutation", ["duplicate", "budget", "incomplete"])
def test_parent_must_be_complete_fixed_ten_history_comparison(mutation):
    value = parent()
    if mutation == "duplicate":
        value["retrieval"]["rows"][0] = deepcopy(value["retrieval"]["rows"][1])
    elif mutation == "budget":
        value["retrieval"]["budget"]["final_items"] = 40
    else:
        value["ingestion"]["all_histories_ingested"] = False
    with pytest.raises(ValueError):
        build_plan(value, input_sha256={})
