"""Scope-bound relation candidates kept separate from semantic retrieval."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from doppel_memory.models import MemoryFilter, MemoryScope


class RelationIndexUnavailableError(RuntimeError):
    """A relation candidate source cannot honor the current request."""


class RelationQuery(BaseModel):
    """Structured, scope-free relation lookup produced by a trusted query plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query_text: str
    entity_mentions: list[str] = Field(min_length=1)
    relation_hints: list[str] = Field(default_factory=list)
    subject: str
    subject_id: str
    valid_at: datetime | None = None

    @field_validator("query_text", "subject", "subject_id", mode="before")
    @classmethod
    def _normalize_text(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("entity_mentions", "relation_hints", mode="before")
    @classmethod
    def _normalize_terms(cls, value: object) -> list[str]:
        terms = [str(item or "").strip() for item in list(value or [])]
        return list(dict.fromkeys(item for item in terms if item))

    @field_validator("valid_at")
    @classmethod
    def _normalize_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("relation valid_at must include a timezone")
        return value.astimezone(UTC)


class RelationCandidate(BaseModel):
    """One graph relation mapped back to an authoritative Doppel memory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: MemoryScope
    memory_id: str
    source: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    score: float = Field(ge=0.0, le=1.0)
    relation_type: str
    source_entity_id: str = ""
    source_entity_name: str = ""
    target_entity_id: str = ""
    target_entity_name: str = ""
    edge_id: str
    episode_ids: list[str] = Field(min_length=1)
    valid_at: datetime | None = None
    invalid_at: datetime | None = None

    @field_validator(
        "memory_id",
        "source",
        "relation_type",
        "source_entity_id",
        "source_entity_name",
        "target_entity_id",
        "target_entity_name",
        "edge_id",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("memory_id", "relation_type", "edge_id")
    @classmethod
    def _require_text(cls, value: str) -> str:
        if not value:
            raise ValueError("relation candidate identifiers must not be empty")
        return value

    @field_validator("episode_ids", mode="before")
    @classmethod
    def _normalize_episode_ids(cls, value: object) -> list[str]:
        items = [str(item or "").strip() for item in list(value or [])]
        return list(dict.fromkeys(item for item in items if item))

    @field_validator("valid_at", "invalid_at")
    @classmethod
    def _normalize_candidate_time(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("relation candidate times must include a timezone")
        return value.astimezone(UTC)


@runtime_checkable
class RelationIndex(Protocol):
    """Exact-scope graph relation source; never a factual authority."""

    async def search_relations(
        self,
        request: RelationQuery,
        scopes: Sequence[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> Sequence[RelationCandidate]: ...
