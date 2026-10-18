"""Explicit source positions; never infer conversation order from timestamps."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from doppel_memory.models import MemoryScope


class SourcePosition(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, revalidate_instances="always"
    )

    scope_key: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    memory_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)


class SourceOrderResolver(Protocol):
    """Host-owned stable sequence; no question, labels or text are requested."""

    async def locate(
        self, scope: MemoryScope, memory_id: str
    ) -> SourcePosition | None: ...

    async def neighbors(
        self, scope: MemoryScope, anchor: SourcePosition, *, before: int, after: int
    ) -> Sequence[SourcePosition]: ...


class ExplicitSourceOrderIndex:
    """In-process reference index over host-supplied immutable source ordinals.

    Not a persistent database index or authorization mechanism. Missing ordinals
    remain gaps: neighbors do not cross gaps by treating list indices as order.
    """

    def __init__(self, positions: Sequence[SourcePosition]):
        self._by_id: dict[tuple[str, str], SourcePosition] = {}
        self._by_position: dict[tuple[str, str, int], SourcePosition] = {}
        for value in positions:
            position = SourcePosition.model_validate(value).model_copy(deep=True)
            key = (position.scope_key, position.memory_id)
            order = (position.scope_key, position.session_id, position.ordinal)
            if key in self._by_id or order in self._by_position:
                raise ValueError(
                    "source IDs and scoped session ordinals must be unique"
                )
            self._by_id[key] = position
            self._by_position[order] = position

    async def locate(self, scope: MemoryScope, memory_id: str) -> SourcePosition | None:
        value = self._by_id.get((scope.scope_key, memory_id))
        return value.model_copy(deep=True) if value else None

    async def neighbors(
        self, scope: MemoryScope, anchor: SourcePosition, *, before: int, after: int
    ) -> Sequence[SourcePosition]:
        if (
            anchor.scope_key != scope.scope_key
            or await self.locate(scope, anchor.memory_id) != anchor
        ):
            raise ValueError("source anchor is not bound to this explicit index")
        if (
            type(before) is not int
            or type(after) is not int
            or not 0 <= before <= 4
            or not 0 <= after <= 4
        ):
            raise ValueError("source neighborhood radius must be between zero and four")
        offsets = sorted(
            [*range(-before, 0), *range(1, after + 1)], key=lambda d: (abs(d), d)
        )
        return [
            value.model_copy(deep=True)
            for offset in offsets
            if (
                value := self._by_position.get(
                    (scope.scope_key, anchor.session_id, anchor.ordinal + offset)
                )
            )
            is not None
        ]
