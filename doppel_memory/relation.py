"""Scope-bound relation candidates kept separate from semantic retrieval."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from doppel_memory.models import MemoryFilter, MemoryScope


class RelationIndexUnavailableError(RuntimeError):
    """A relation candidate source cannot honor the current request."""


class RelationQuery(BaseModel):
    """Structured, scope-free relation lookup produced by a trusted query plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query_text: str
    entity_mentions: list[str] = Field(default_factory=list)
    relation_hints: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    subject: str
    subject_id: str
    valid_at: datetime | None = None
    time_from: datetime | None = None
    time_to: datetime | None = None

    @field_validator("query_text", "subject", "subject_id", mode="before")
    @classmethod
    def _normalize_text(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("entity_mentions", "relation_hints", mode="before")
    @classmethod
    def _normalize_terms(cls, value: object) -> list[str]:
        terms = [str(item or "").strip() for item in _list_items(value)]
        return list(dict.fromkeys(item for item in terms if item))

    @field_validator("relation_types", mode="before")
    @classmethod
    def _normalize_relation_types(cls, value: object) -> list[str]:
        relation_types = [
            str(item or "").strip().upper() for item in _list_items(value)
        ]
        normalized = list(dict.fromkeys(item for item in relation_types if item))
        invalid = [
            item
            for item in normalized
            if re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", item) is None
        ]
        if invalid:
            raise ValueError(
                "relation types must be canonical uppercase identifiers: "
                f"{invalid}"
            )
        return normalized

    @field_validator("valid_at", "time_from", "time_to")
    @classmethod
    def _normalize_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("relation query times must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_interval(self) -> RelationQuery:
        if self.time_from and self.time_to and self.time_to < self.time_from:
            raise ValueError("relation time_to must not precede time_from")
        if self.valid_at is not None and (
            self.time_from is not None or self.time_to is not None
        ):
            raise ValueError("relation query cannot mix valid_at with a time range")
        return self


class RelationRerankItem(BaseModel):
    """One opaque graph edge offered for textual relation scoring.

    The item deliberately excludes scope, subject identifiers, memory identifiers,
    lifecycle state, and time metadata. A reranker can judge whether an edge's text
    addresses the requested relationship, but cannot become an authority for any
    of Doppel's isolation or factual-governance decisions.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    relation_type: str
    fact: str = ""

    @field_validator("item_id", "relation_type", "fact", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("item_id", "relation_type")
    @classmethod
    def _require_text(cls, value: str) -> str:
        if not value:
            raise ValueError("relation rerank item identifiers must not be empty")
        return value


class RelationRerankRequest(BaseModel):
    """Text-only batch presented to a host-supplied relation reranker."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query_text: str
    relation_hints: list[str] = Field(default_factory=list)
    items: list[RelationRerankItem] = Field(default_factory=list)

    @field_validator("query_text", mode="before")
    @classmethod
    def _normalize_query(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("relation_hints", mode="before")
    @classmethod
    def _normalize_hints(cls, value: object) -> list[str]:
        hints = [str(item or "").strip() for item in _list_items(value)]
        return list(dict.fromkeys(item for item in hints if item))

    @model_validator(mode="after")
    def _require_unique_items(self) -> RelationRerankRequest:
        item_ids = [item.item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("relation rerank request item IDs must be unique")
        return self


class RelationRerankScore(BaseModel):
    """Normalized textual relevance returned for one opaque edge item."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    score: float = Field(ge=0.0, le=1.0)

    @field_validator("item_id", mode="before")
    @classmethod
    def _normalize_item_id(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("item_id")
    @classmethod
    def _require_item_id(cls, value: str) -> str:
        if not value:
            raise ValueError("relation rerank score item_id must not be empty")
        return value


@runtime_checkable
class RelationReranker(Protocol):
    """Host-supplied text scorer; never an isolation or factual authority."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    async def rerank(
        self, request: RelationRerankRequest
    ) -> Sequence[RelationRerankScore]: ...


class RelationCandidate(BaseModel):
    """One graph relation mapped back to an authoritative Doppel memory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: MemoryScope
    memory_id: str
    source: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    score: float = Field(ge=0.0, le=1.0)
    relation_type: str
    fact: str = ""
    match_kind: Literal["adjacency", "type", "lexical", "reranker", "none"] = (
        "adjacency"
    )
    reranker_score: float | None = Field(default=None, ge=0.0, le=1.0)
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
        "fact",
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
        items = [str(item or "").strip() for item in _list_items(value)]
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


def _list_items(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]
