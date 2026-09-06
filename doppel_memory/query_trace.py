"""Opt-in, bounded query diagnostics; no query text or memory content is copied."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import MemoryRecord

TraceSource = Literal["store", "semantic", "relation", "engine"]
TraceStage = Literal[
    "discovery",
    "store_validation",
    "relation_gate",
    "structural_gate",
    "score_gate",
    "evidence_gate",
    "ranking",
]


class PersonalMemoryQueryTraceEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: TraceStage
    source: TraceSource
    reason: str
    scope_key: str = ""
    memory_id: str = ""
    count: int = Field(default=1, ge=0)
    scores: dict[str, float] = Field(default_factory=dict)


class PersonalMemoryQueryTrace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    coverage: Literal["engine_boundary"] = "engine_boundary"
    events: list[PersonalMemoryQueryTraceEvent] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    event_limit: int = Field(ge=1, le=10_000)
    events_seen: int = Field(ge=0)
    dropped_events: int = Field(ge=0)


def validate_trace_limit(limit: int) -> None:
    if type(limit) is not int or not 0 <= limit <= 10_000:
        raise ValueError("trace_limit must be an integer between 0 and 10000")


class _QueryTraceCollector:
    """Per-execution state. Rejected foreign candidates never expose identifiers."""

    def __init__(self, limit: int, scope_keys: set[str]) -> None:
        self.limit = limit
        self.scope_keys = scope_keys
        self.events: list[PersonalMemoryQueryTraceEvent] = []
        self.counts: dict[str, int] = {}
        self.events_seen = 0

    def add(
        self,
        stage: TraceStage,
        source: TraceSource,
        reason: str,
        record: MemoryRecord | None = None,
        *,
        count: int = 1,
        scores: dict[str, float] | None = None,
    ) -> None:
        key = f"{stage}:{source}:{reason}"
        self.counts[key] = self.counts.get(key, 0) + count
        self.events_seen += 1
        if len(self.events) >= self.limit:
            return
        authorized = record is not None and record.scope.scope_key in self.scope_keys
        self.events.append(
            PersonalMemoryQueryTraceEvent(
                stage=stage,
                source=source,
                reason=reason,
                count=count,
                scope_key=record.scope.scope_key
                if record is not None and authorized
                else "",
                memory_id=record.memory_id if record is not None and authorized else "",
                scores=(scores or {}) if authorized else {},
            )
        )

    def result(self) -> PersonalMemoryQueryTrace:
        return PersonalMemoryQueryTrace(
            events=self.events,
            counts=self.counts,
            event_limit=self.limit,
            events_seen=self.events_seen,
            dropped_events=self.events_seen - len(self.events),
        )
