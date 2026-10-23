from copy import deepcopy

import pytest

from benchmarks.public_memory_context_budget import (
    BUDGETS,
    encode,
    pack,
    replay,
    sha,
    validate_arm,
)


def item(number, text="hello"):
    return {
        "memory_id": f"m{number}",
        "scope_key": "one-owner",
        "text": text,
        "actor": "owner" if number % 2 else "assistant",
        "role": "user" if number % 2 else "assistant",
        "authority": "human_self" if number % 2 else "agent_output",
        "observed_at": "2024-01-02T00:00:00+00:00",
        "source_events": [f"event-{number}"],
    }


def arm(width, *, negative=False):
    top = [item(i) for i in range(20)]
    packed, trace = pack(top, 24000)
    return {
        "candidate_ids": [f"m{i}" for i in range(width)],
        "top20": top,
        "context": packed,
        "annotated": 0 if negative else 2,
        "candidate_annotated_ids": [] if negative else ["m0", "m30"],
        "top20_annotated_ids": [] if negative else ["m0"],
        "packed_annotated_ids": [] if negative else ["m0"],
        "packed_items": len(packed),
        "context_bytes": len(encode(packed)),
        "context_sha256": sha(encode(packed)),
        "packing_trace": trace,
    }


def source():
    return {
        "status": "complete",
        "failure": None,
        "rows": [
            {
                "ordinal": i,
                "case_id": f"case-{i}",
                "abstention_label": i <= 7,
                "arms": {str(w): arm(w, negative=i <= 7) for w in (80, 160)},
            }
            for i in range(1, 51)
        ],
    }


def test_reproduces_original_policy_and_all_attribution():
    # Import only in test; the offline command has no optional model/DB imports.
    from benchmarks.public_memory_comparison import pack_ranked_fit

    items = [item(i, "汉字🙂" * (3000 if i % 3 == 0 else 200)) for i in range(20)]
    before = deepcopy(items)
    assert pack(items, 24000) == pack_ranked_fit(items)
    for budget in BUDGETS:
        packed, _ = pack(items, budget)
        assert len(encode(packed)) <= budget
        assert all(value in items for value in packed)
    assert items == before


def test_larger_budget_can_displace_evidence_under_same_greedy_policy():
    items = [
        {"memory_id": "long", "text": "a" * 100},
        {"memory_id": "short", "text": "b" * 50},
    ]
    low = len(encode(items[1:]))
    high = len(encode(items[:1]))
    assert pack(items, low)[0] == items[1:]
    assert pack(items, high)[0] == items[:1]


def test_exact_utf8_boundary_and_item_cap():
    items = [item(i, "中文🙂") for i in range(30)]
    assert len(encode(items[:1])) > len(encode(items[:1]).decode())
    assert pack(items[:1], len(encode(items[:1])))[0] == items[:1]
    assert pack(items[:1], len(encode(items[:1])) - 1)[0] == []
    assert len(pack(items, 1000000)[0]) == 20
    assert pack([], 2)[0] == []


@pytest.mark.parametrize("budget", [0, -1, True, 24000.0])
def test_invalid_budget(budget):
    with pytest.raises(ValueError):
        pack([], budget)


@pytest.mark.parametrize(
    "damage", ["duplicate", "scope", "digest", "context", "trace", "annotation"]
)
def test_invalid_saved_arm_rejected(damage):
    saved = arm(80)
    if damage == "duplicate":
        saved["top20"][1]["memory_id"] = "m0"
    elif damage == "scope":
        saved["top20"][1]["scope_key"] = "other-owner"
    elif damage == "digest":
        saved["context_sha256"] = "0" * 64
    elif damage == "context":
        saved["context"][0]["actor"] = "other"
    elif damage == "trace":
        saved["packing_trace"]["selected_rank_positions"] = []
    else:
        saved["top20_annotated_ids"] = ["m30"]
    with pytest.raises(ValueError):
        validate_arm(saved, "80")


def test_positive_denominators_and_top20_ceiling_not_all_retrieval():
    original = source()
    snapshot = deepcopy(original)
    result = replay(original)
    assert original == snapshot
    for width in ("80", "160"):
        for value in result["summary"][width]["budgets"].values():
            assert value["positive_questions"] == 43
            assert value["annotated"] == 86
            assert value["packed_annotations"] == 43
            assert value["annotation_recall"] == 0.5
            assert value["annotations_outside_top20"] == 43
            assert value["top20_annotations_still_unpacked"] == 0
            assert value["complete_positive_questions"] == 0
            assert value["all_case_items"] == 1000


def test_labels_change_measurement_not_selection():
    original = source()
    first = replay(original)
    changed = deepcopy(original)
    for row in changed["rows"]:
        for saved in row["arms"].values():
            saved["candidate_annotated_ids"] = []
            saved["top20_annotated_ids"] = []
            saved["packed_annotated_ids"] = []
    second = replay(changed)
    for a, b in zip(first["rows"], second["rows"], strict=True):
        for width in ("80", "160"):
            for budget in ("24000", "48000", "96000"):
                for field in (
                    "selected_ids",
                    "context_sha256",
                    "context_bytes",
                    "trace",
                ):
                    assert (
                        a["arms"][width][budget][field]
                        == b["arms"][width][budget][field]
                    )


def test_rejects_incomplete_or_negative_contaminated_cohort():
    incomplete = source()
    incomplete["rows"].pop()
    with pytest.raises(ValueError):
        replay(incomplete)
    contaminated = source()
    contaminated["rows"][0]["arms"]["80"] = arm(80)
    with pytest.raises(ValueError, match="negative"):
        replay(contaminated)
