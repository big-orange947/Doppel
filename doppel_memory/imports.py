"""Portable IM history interchange models and deterministic batch ingestion."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from doppel_memory.models import (
    ChatMessage,
    MemoryScope,
    WriteResult,
    WriteStatus,
    utc_now,
)


class IMImportItem(BaseModel):
    """One normalized message and the exact scope it should be imported into."""

    scope: MemoryScope
    message: ChatMessage
    source_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_id", mode="before")
    @classmethod
    def _normalize_source_id(cls, value: Any) -> str:
        return str(value or "").strip()


class IMImportBatch(BaseModel):
    """Backend-neutral JSON envelope for one exported page or import batch."""

    format_version: str = "1"
    source: str
    source_version: str = ""
    batch_id: str = ""
    exported_at: datetime = Field(default_factory=utc_now)
    cursor: str = ""
    items: list[IMImportItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "format_version",
        "source",
        "source_version",
        "batch_id",
        "cursor",
        mode="before",
    )
    @classmethod
    def _normalize_strings(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("source")
    @classmethod
    def _require_source(cls, value: str) -> str:
        if not value:
            raise ValueError("source is required")
        return value

    @field_validator("exported_at")
    @classmethod
    def _normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        return value.astimezone(UTC)


class ImportResult(BaseModel):
    """Structured aggregate that retains every underlying Store write result."""

    total: int = 0
    accepted: int = 0
    created: int = 0
    updated: int = 0
    duplicates: int = 0
    skipped: int = 0
    failed: int = 0
    write_results: list[WriteResult] = Field(default_factory=list)

    @classmethod
    def summarize(cls, results: list[WriteResult]) -> ImportResult:
        return cls(
            total=len(results),
            accepted=sum(item.accepted for item in results),
            created=sum(item.status is WriteStatus.CREATED for item in results),
            updated=sum(item.status is WriteStatus.UPDATED for item in results),
            duplicates=sum(item.status is WriteStatus.DUPLICATE for item in results),
            skipped=sum(item.status is WriteStatus.SKIPPED for item in results),
            failed=sum(item.status is WriteStatus.FAILED for item in results),
            write_results=results,
        )
