"""Evidence-bound occurrence coordinates, separate from state validity.

Binding verifies source identity/text/clock, not the semantic correctness of a
model's normalization. Intervals are closed; unknown time stays unknown.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from doppel_memory.models import ChatMessage, MemoryRecord


class EventTimeCoordinate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    start: datetime | None = None
    end: datetime | None = None
    precision: Literal["instant", "day", "month", "year", "range", "unknown"]
    basis: Literal["explicit", "resolved_relative", "unresolved"]
    expression: str = Field(min_length=1, max_length=1000)
    evidence_id: str = Field(min_length=1, max_length=256)

    @field_validator("start", "end")
    @classmethod
    def aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("occurrence time must include a timezone")
        return value.astimezone(UTC) if value is not None else None

    @field_validator("expression", "evidence_id")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("occurrence source binding must be nonblank")
        return value  # quotes are exact, not normalized or translated

    @model_validator(mode="after")
    def bounds(self) -> EventTimeCoordinate:
        if self.basis == "unresolved":
            if (
                self.precision != "unknown"
                or self.start is not None
                or self.end is not None
            ):
                raise ValueError("unresolved time cannot assert bounds or precision")
        elif self.start is None or self.end is None or self.precision == "unknown":
            raise ValueError("resolved time requires both bounds and known precision")
        if self.start is not None and self.end is not None:
            if self.end < self.start:
                raise ValueError("occurrence end precedes start")
            if self.precision == "instant" and self.end != self.start:
                raise ValueError("instant requires identical bounds")
            if self.precision != "instant" and self.end == self.start:
                raise ValueError("partial time must preserve an interval, not a point")
        return self


class BoundEventTime(EventTimeCoordinate):
    anchor_observed_at: datetime
    normalization_verified: Literal[False] = False

    @field_validator("anchor_observed_at")
    @classmethod
    def aware_anchor(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurrence anchor must include a timezone")
        return value.astimezone(UTC)


def bind_event_time(
    coordinate: EventTimeCoordinate, messages: Sequence[ChatMessage]
) -> BoundEventTime:
    source = next(
        (m for m in messages if m.identity_key == coordinate.evidence_id), None
    )
    if source is None or coordinate.expression not in source.text:
        raise ValueError("occurrence time must quote its bound original evidence")
    return BoundEventTime(
        **coordinate.model_dump(include=set(EventTimeCoordinate.model_fields)),
        anchor_observed_at=source.at,
    )


def record_event_time(record: MemoryRecord) -> BoundEventTime | None:
    raw = record.metadata.get("event_time")
    if raw is None:
        return None
    if record.metadata.get("personal_memory_type") != "episode":
        raise ValueError("occurrence coordinates require an episode")
    coordinate = BoundEventTime.model_validate(raw)
    evidence = record.metadata.get("evidence")
    if not isinstance(evidence, list) or not any(
        isinstance(e, dict)
        and e.get("evidence_id") == coordinate.evidence_id
        and e.get("actor") == record.actor
        and datetime.fromisoformat(str(e.get("at"))) == coordinate.anchor_observed_at
        for e in evidence
    ):
        raise ValueError("occurrence coordinate is not bound to record evidence")
    return coordinate
