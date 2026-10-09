from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from benchmarks.public_longmemeval import (
    QueryInput,
    RawSession,
    RuntimeCase,
    SourceTurn,
)
from benchmarks.public_memory_clock_policy import explicit_horizon, observation_policy

REF = datetime(2024, 1, 1, tzinfo=UTC)


def runtime(*timestamps):
    return RuntimeCase(
        "owner",
        (
            RawSession(
                "session",
                0,
                tuple(
                    SourceTurn("session", 0, i, "user", "opaque content", at)
                    for i, at in enumerate(timestamps)
                ),
            ),
        ),
        QueryInput("owner", "opaque question", REF),
    )


def test_supplied_history_horizon_is_uniform_not_answer_selected():
    case = runtime(REF - timedelta(days=1), REF + timedelta(hours=6))
    clock = observation_policy(case, "provided-history-v1")
    assert explicit_horizon(clock) == REF + timedelta(hours=6)
    assert clock["reference_time"] == REF.isoformat()
    assert clock["provided_turn_count"] == 2
    assert clock["provided_turns_after_reference"] == 1
    assert not clock["uses_scoring_annotations"] and not clock["causal_replay"]
    changed = replace(case, query=replace(case.query, query="different query"))
    assert observation_policy(changed, "provided-history-v1") == clock


def test_strict_policy_keeps_reference_horizon_and_legacy_plan_request():
    clock = observation_policy(runtime(REF + timedelta(days=2)), "strict-reference-v1")
    assert clock["observed_until"] == REF.isoformat()
    assert explicit_horizon(clock) is None and clock["causal_replay"]
    assert clock["provided_turns_after_reference"] == 1


@pytest.mark.parametrize("timestamps", [(), (REF - timedelta(days=1),)])
def test_empty_or_earlier_history_does_not_move_reference_backwards(timestamps):
    clock = observation_policy(runtime(*timestamps), "provided-history-v1")
    assert explicit_horizon(clock) == REF


def test_timezone_equivalence_and_session_order_do_not_change_horizon():
    later = REF + timedelta(days=1)
    a = observation_policy(runtime(REF, later), "provided-history-v1")
    b = observation_policy(
        runtime(later.astimezone(timezone(timedelta(hours=8))), REF),
        "provided-history-v1",
    )
    assert a == b


@pytest.mark.parametrize("bad", ["", "unlimited", "gold-cutoff"])
def test_unsupported_policy_fails_before_inspecting_runtime(bad):
    with pytest.raises(ValueError, match="unsupported"):
        observation_policy(None, bad)


def test_naive_source_clock_rejected():
    with pytest.raises(ValueError, match="timezone"):
        observation_policy(runtime(REF.replace(tzinfo=None)), "provided-history-v1")


def test_naive_reference_clock_rejected():
    case = runtime()
    case = replace(
        case, query=replace(case.query, reference_time=REF.replace(tzinfo=None))
    )
    with pytest.raises(ValueError, match="timezone"):
        observation_policy(case, "provided-history-v1")


def test_explicit_horizon_rejects_unknown_policy_and_naive_clock():
    with pytest.raises(ValueError, match="unsupported"):
        explicit_horizon({"policy": "unlimited"})
    with pytest.raises(ValueError, match="timezone"):
        explicit_horizon(
            {"policy": "provided-history-v1", "observed_until": "2024-01-01"}
        )
