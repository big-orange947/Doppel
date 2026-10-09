"""Gold-free, explicit reference versus observation policy for diagnostics.

This selects no cases and reads no scoring annotations. Causal replay and
complete supplied-history evaluation are different protocols, never pooled.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from benchmarks.public_longmemeval import RuntimeCase

ClockPolicy = Literal["strict-reference-v1", "provided-history-v1"]
POLICIES = ("strict-reference-v1", "provided-history-v1")


def observation_policy(runtime: RuntimeCase, policy: ClockPolicy) -> dict:
    if policy not in POLICIES:
        raise ValueError("unsupported observation policy")
    reference = runtime.query.reference_time
    timestamps = [turn.at for session in runtime.sessions for turn in session.turns]
    if any(t.tzinfo is None for t in [reference, *timestamps]):
        raise ValueError("runtime clocks must be timezone aware")
    reference = reference.astimezone(UTC)
    latest = max(timestamps).astimezone(UTC) if timestamps else None
    horizon = reference
    if policy == "provided-history-v1" and latest is not None:
        horizon = max(reference, latest)
    return {
        "policy": policy,
        "reference_time": reference.isoformat(),
        "observed_until": horizon.isoformat(),
        "latest_provided_observation": latest.isoformat() if latest else None,
        "provided_turn_count": len(timestamps),
        "provided_turns_after_reference": sum(t > reference for t in timestamps),
        "uses_scoring_annotations": False,
        "causal_replay": policy == "strict-reference-v1",
    }


def explicit_horizon(clock: dict) -> datetime | None:
    """Default policy retains the old V2 wire shape, explicit policy uses V3."""
    if clock["policy"] == "strict-reference-v1":
        return None
    if clock["policy"] != "provided-history-v1":
        raise ValueError("unsupported observation policy")
    horizon = datetime.fromisoformat(clock["observed_until"])
    if horizon.tzinfo is None:
        raise ValueError("observation clock requires a timezone")
    return horizon.astimezone(UTC)
