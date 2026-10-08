"""Manifest selection/mapping tests use synthetic histories, never gold for routing."""

import json
from copy import deepcopy

import pytest

from benchmarks.public_memory_pilot import TEMPORAL_POLICY, build_manifest


def records() -> list[dict]:
    return [
        {
            "question_id": f"synthetic-{i}",
            "question_type": "multi-session",
            "question": "SYNTHETIC_QUERY_NOT_IN_MANIFEST",
            "answer": "GOLD_NOT_IN_MANIFEST",
            "answer_session_ids": ["source"],
            "question_date": "2024/01/02 12:00",
            "haystack_session_ids": ["source"],
            "haystack_dates": ["2024/01/01 12:00"],
            "haystack_sessions": [
                [
                    {"role": "user", "content": "", "has_answer": False},
                    {
                        "role": "user",
                        "content": f"ORIGINAL_HISTORY_{i}",
                        "has_answer": True,
                    },
                ]
            ],
        }
        for i in range(8)
    ]


def manifest(source: list[dict], **changes: object) -> dict:
    args = {
        "dataset_namespace": "synthetic-v1",
        "run_namespace": "run-v1",
        "source_sha256": "a" * 64,
        "diagnostic_count": 2,
        "reserved_count": 2,
    }
    args.update(changes)
    return build_manifest(source, **args)


def test_reordering_input_does_not_change_frozen_selection() -> None:
    original = records()
    assert manifest(original) == manifest(list(reversed(original)))
    assert (
        manifest(original)["manifest_fingerprint"]
        != manifest(original, seed=2)["manifest_fingerprint"]
    )


def test_labels_queries_categories_do_not_choose_samples_or_change_write_mapping() -> (
    None
):
    original = records()
    changed = deepcopy(original)
    for raw in changed:
        raw["answer"] = "CHANGED_GOLD"
        raw["question"] = "A changed query"
        raw["answer_session_ids"] = []
        raw["question_type"] = "temporal-reasoning"
        raw["haystack_sessions"][0][1]["has_answer"] = False
    assert manifest(original) == manifest(changed)
    encoded = json.dumps(manifest(original))
    assert "GOLD_NOT_IN_MANIFEST" not in encoded
    assert "SYNTHETIC_QUERY_NOT_IN_MANIFEST" not in encoded
    assert "ORIGINAL_HISTORY" not in encoded
    assert "has_answer" not in encoded and "answer_session_ids" not in encoded


def test_exact_shared_histories_stay_in_one_partition_and_one_sample() -> None:
    source = records()
    twin = deepcopy(source[0])
    twin["question_id"] = "another-question-on-same-history"
    source.append(twin)
    result = manifest(source, diagnostic_count=4, reserved_count=4)
    assert result["exact_history_group_count"] == 8
    assert len({row["history_group"] for row in result["cases"]}) == 8
    assert sum(row["cases_in_exact_history_group"] == 2 for row in result["cases"]) == 1
    assert (
        sum(
            row["case_id"] in {"synthetic-0", twin["question_id"]}
            for row in result["cases"]
        )
        == 1
    )
    assert result["reserved_is_independently_blind"] is False


def test_blank_turn_source_maps_and_temporal_protocol_are_explicit() -> None:
    result = manifest(records())
    for row in result["cases"]:
        assert row["raw_turn_count"] == 2 and row["transport_turn_count"] == 1
        chunk = row["chunks"][0]
        assert chunk["source_turn_indices"] == [1]
        assert chunk["source_session_index"] == 0
        assert len(chunk["event_ids"]) == 1
    assert result["temporal_policy"] == TEMPORAL_POLICY
    assert result["llm_calls"] == 0 and result["quality_metrics_available"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"diagnostic_count": 0},
        {"reserved_count": True},
        {"reserved_count": 99},
        {"source_sha256": "bad"},
        {"seed": "1"},
        {"max_messages": 0},
    ],
)
def test_invalid_preregistration_fails(changes: dict) -> None:
    with pytest.raises(ValueError):
        manifest(records(), **changes)


def test_duplicate_case_identity_is_not_counted_twice() -> None:
    source = records()
    source.append(deepcopy(source[0]))
    with pytest.raises(ValueError, match="duplicate"):
        manifest(source)


def test_exclude_complete_prior_groups_including_reserved_and_aliases() -> None:
    source = records()
    prior = manifest(source, diagnostic_count=1, reserved_count=1)
    excluded = [r["history_group"] for r in prior["cases"]]
    twin = deepcopy(
        next(r for r in source if r["question_id"] == prior["cases"][0]["case_id"])
    )
    twin["question_id"] = "alias-of-opened-history"
    source.append(twin)
    result = manifest(source, excluded_history_groups=excluded)
    assert not set(excluded) & {r["history_group"] for r in result["cases"]}
    assert result["eligible_history_group_count"] == 6
    assert "alias-of-opened-history" not in {r["case_id"] for r in result["cases"]}


def test_strata_use_public_type_but_not_gold_or_query() -> None:
    source = records()
    for index, raw in enumerate(source):
        raw["question_type"] = [
            "multi-session",
            "knowledge-update",
            "temporal-reasoning",
        ][index % 3]
    result = manifest(
        source, diagnostic_count=3, reserved_count=2, stratify_by_question_type=True
    )
    assert len({r["sampling_stratum"] for r in result["cases"][:3]}) == 3
    changed = deepcopy(source)
    for raw in changed:
        raw["answer"] = "DIFFERENT GOLD"
        raw["question"] = "Different query"
        raw["answer_session_ids"] = []
        raw["haystack_sessions"][0][1]["has_answer"] = False
    assert (
        manifest(
            changed,
            diagnostic_count=3,
            reserved_count=2,
            stratify_by_question_type=True,
        )
        == result
    )
    assert (
        manifest(
            list(reversed(source)),
            diagnostic_count=3,
            reserved_count=2,
            stratify_by_question_type=True,
        )
        == result
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"excluded_history_groups": ["bad"]},
        {"excluded_history_groups": ["f" * 64]},
        {"stratify_by_question_type": 1},
    ],
)
def test_invalid_extended_selection_fails(changes):
    with pytest.raises(ValueError):
        manifest(records(), **changes)
