import copy

import pytest

from doppel_memory.context_packing import (
    FORMAT,
    encode,
    pack_context_items,
    unpack_context,
)


def items(count=12):
    return [
        {
            "channel": "raw",
            "scope_key": "same-scope-" + "x" * 70,
            "memory_id": f"memory-{i}",
            "text": "unchanged 引文\n" + str(i),
            "role": "user" if i % 2 == 0 else "assistant",
            "actor": "owner" if i % 2 == 0 else "agent",
            "authority": "human_self" if i % 2 == 0 else "agent_output",
            "observed_at": "2024-01-01T00:00:00Z",
            "source_events": [f"event-{i}"],
            "temporal_status": None,
            "valid_from": None,
            "valid_to": None,
        }
        for i in range(count)
    ]


def test_lossless_factoring_preserves_actor_time_sources_and_inputs():
    source = items()
    before = copy.deepcopy(source)
    result = pack_context_items(source)
    assert result.payload["format"] == FORMAT
    assert unpack_context(result.payload) == source == before
    assert result.wire_bytes < result.baseline_bytes
    for item in result.payload["items"]:
        assert {
            "role",
            "actor",
            "authority",
            "observed_at",
            "source_events",
            "text",
            "memory_id",
        } <= item.keys()
    assert "scope_key" in result.payload["shared"]


@pytest.mark.parametrize("budget", [2, 100, 500, 1000, 2000, 5000, 24000])
def test_retention_is_monotonic_and_bounded_for_every_budget(budget):
    source = items(30)
    result = pack_context_items(source, byte_limit=budget)
    selected = unpack_context(result.payload)
    assert result.wire_bytes == len(encode(result.payload)) <= budget
    assert len(selected) <= 20
    assert set(result.baseline_ranks) <= set(result.selected_ranks)
    assert list(result.selected_ranks) == sorted(result.selected_ranks)
    assert selected == [source[i - 1] for i in result.selected_ranks]


def test_freed_bytes_can_add_whole_sources_without_displacing_old_sources():
    source = items(20)
    budget = len(encode(source[:5]))
    result = pack_context_items(source, byte_limit=budget)
    assert len(result.baseline_ranks) == 5
    assert len(result.selected_ranks) > 5
    assert unpack_context(result.payload) == [
        source[i - 1] for i in result.selected_ranks
    ]


def test_inconsistent_or_absent_temporal_fields_are_not_factored_as_defaults():
    source = items()
    source[0]["valid_from"] = "2023-01-01"
    del source[1]["valid_to"]
    packed = pack_context_items(source)
    assert unpack_context(packed.payload) == source
    assert "valid_from" not in packed.payload["shared"]
    assert "valid_to" not in packed.payload["shared"]


@pytest.mark.parametrize(
    "fault", ["scope", "duplicate", "identity", "text", "nan", "coercion"]
)
def test_bad_sources_fail_instead_of_being_silently_repaired(fault):
    source = items()
    if fault == "scope":
        source[0]["scope_key"] = "other"
    elif fault == "duplicate":
        source[1]["memory_id"] = source[0]["memory_id"]
    elif fault == "identity":
        del source[0]["memory_id"]
    elif fault == "text":
        source[0]["text"] = None
    elif fault == "nan":
        source[0]["extra"] = float("nan")
    else:
        source[0]["extra"] = {1: "coerced-key"}
    with pytest.raises((ValueError, TypeError)):
        pack_context_items(source)


def test_decoder_rejects_role_factoring_and_overlapping_metadata():
    with pytest.raises(ValueError):
        unpack_context(
            {"format": FORMAT, "shared": {"actor": "owner"}, "items": items()}
        )
    with pytest.raises(ValueError):
        unpack_context(
            {"format": FORMAT, "shared": {"scope_key": "other"}, "items": items()}
        )


def test_format_fallback_empty_oversized_and_candidate_limit():
    assert pack_context_items([]).payload == []
    source = items(1)
    source[0]["text"] = "x" * 30000
    assert unpack_context(pack_context_items(source).payload) == []
    assert pack_context_items(items(), candidate_limit=2).selected_ranks == (1, 2)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mode": "unknown"},
        {"byte_limit": 1},
        {"item_limit": True},
        {"candidate_limit": 0},
    ],
)
def test_invalid_options_are_rejected(kwargs):
    with pytest.raises(ValueError):
        pack_context_items(items(), **kwargs)
