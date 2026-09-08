"""Optional, reorder-only reranking for authorized personal-memory candidates."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PersonalMemoryRerankItem(BaseModel):
    """One authorized memory exposed under a request-local opaque identifier."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    content: str

    @field_validator("item_id", "content", mode="before")
    @classmethod
    def _normalize_text(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("item_id")
    @classmethod
    def _require_item_id(cls, value: str) -> str:
        if not value:
            raise ValueError("personal-memory rerank item_id must not be empty")
        return value


class PersonalMemoryRerankRequest(BaseModel):
    """Raw question plus an already-authorized, content-only candidate window."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    items: list[PersonalMemoryRerankItem] = Field(default_factory=list)

    @field_validator("question", mode="before")
    @classmethod
    def _normalize_question(cls, value: object) -> str:
        return str(value or "").strip()

    @model_validator(mode="after")
    def _require_unique_items(self) -> PersonalMemoryRerankRequest:
        item_ids = [item.item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("personal-memory rerank item IDs must be unique")
        return self


class PersonalMemoryRerankScore(BaseModel):
    """Normalized relevance for one request-local candidate identifier."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)

    @field_validator("item_id", mode="before")
    @classmethod
    def _normalize_item_id(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("item_id")
    @classmethod
    def _require_item_id(cls, value: str) -> str:
        if not value:
            raise ValueError("personal-memory rerank score item_id must not be empty")
        return value


@runtime_checkable
class PersonalMemoryReranker(Protocol):
    """Host-supplied scorer that has no isolation or evidence authority."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    async def rerank(
        self, request: PersonalMemoryRerankRequest
    ) -> Sequence[PersonalMemoryRerankScore]: ...


class PersonalMemoryRerankConfig(BaseModel):
    """Hard bounds for an optional memory-level reranking call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_candidates: int = Field(default=64, ge=1, le=1_000, strict=True)
    max_input_chars: int = Field(default=100_000, ge=1, le=10_000_000, strict=True)
    timeout_seconds: float = Field(default=30, gt=0, le=300, allow_inf_nan=False)


class PersonalMemoryRerankSummary(BaseModel):
    """Content-free audit summary for the optional ordering stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["not_run", "completed", "unavailable", "limit_exceeded"]
    total_candidates: int = Field(default=0, ge=0)
    offered_candidates: int = Field(default=0, ge=0)
    reranked_candidates: int = Field(default=0, ge=0)


async def score_personal_memories(
    reranker: PersonalMemoryReranker,
    request: PersonalMemoryRerankRequest,
    config: PersonalMemoryRerankConfig,
    *,
    total_candidates: int,
) -> tuple[dict[str, float], PersonalMemoryRerankSummary]:
    """Run one strictly bound scoring call; provider failures preserve base order."""

    size = len(request.items)
    base = {"total_candidates": total_candidates, "offered_candidates": size}
    if not size:
        return {}, PersonalMemoryRerankSummary(status="not_run", **base)
    if (
        size > config.max_candidates
        or len(request.question) + sum(len(item.content) for item in request.items)
        > config.max_input_chars
    ):
        return {}, PersonalMemoryRerankSummary(status="limit_exceeded", **base)

    async def run() -> dict[str, float]:
        raw_scores = await reranker.rerank(request)
        scores = [PersonalMemoryRerankScore.model_validate(item) for item in raw_scores]
        item_ids = [item.item_id for item in scores]
        expected = {item.item_id for item in request.items}
        if len(item_ids) != len(set(item_ids)) or set(item_ids) != expected:
            raise ValueError("invalid personal-memory rerank score binding")
        return {item.item_id: float(item.score) for item in scores}

    try:
        scores = await asyncio.wait_for(run(), timeout=config.timeout_seconds)
    except Exception:  # noqa: BLE001 - provider errors may contain secrets or content
        return {}, PersonalMemoryRerankSummary(status="unavailable", **base)
    return scores, PersonalMemoryRerankSummary(
        status="completed",
        reranked_candidates=size,
        **base,
    )
