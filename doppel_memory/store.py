"""Backend-neutral memory store contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from doppel_memory.models import (
    ChatMessage,
    FactAuthority,
    MemoryFilter,
    MemoryKind,
    MemoryPage,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    RecallResult,
    StoreCapabilities,
    WriteResult,
)


class MemoryStore(ABC):
    """Exact-scope persistence contract implemented by every backend."""

    @property
    @abstractmethod
    def capabilities(self) -> StoreCapabilities: ...

    @property
    @abstractmethod
    def is_enabled(self) -> bool: ...

    @abstractmethod
    async def put(
        self, record: MemoryRecord, *, idempotency_key: str | None = None
    ) -> WriteResult:
        """Persist one arbitrary memory record within its exact scope."""

    async def write_event(
        self, scope: MemoryScope, message: ChatMessage
    ) -> WriteResult:
        key = message.identity_key
        idempotency_key = f"event:{key}" if key else ""
        return await self.put(
            MemoryRecord(
                kind=MemoryKind.EVENT,
                scope=scope,
                content=message.text,
                actor=message.actor,
                authority=message.fact_authority,
                state=MemoryState.CONFIRMED,
                idempotency_key=idempotency_key,
                source_event_id=message.event_id,
                source_message_id=message.message_id,
                extractor="ingestor",
                created_at=message.at,
                updated_at=message.at,
                metadata={
                    "message_type": message.message_type,
                    "sender_id": message.sender_id,
                    "reply_to_id": message.reply_to_id,
                    "quoted_message_id": message.quoted_message_id,
                    "thread_id": message.thread_id,
                    "thread_root_id": message.thread_root_id,
                    "attachments": message.attachments,
                    "raw": message.raw,
                },
            ),
            idempotency_key=idempotency_key or None,
        )

    async def write_background(
        self,
        scope: MemoryScope,
        content: str,
        tags: list[str] | None = None,
        *,
        importance: float = 0.5,
        source: str = "manual",
    ) -> WriteResult:
        return await self.put(
            MemoryRecord(
                kind=MemoryKind.BACKGROUND,
                scope=scope,
                content=content,
                tags=list(tags or []),
                importance=importance,
                extractor=source,
            )
        )

    async def write_relation(
        self,
        scope: MemoryScope,
        *,
        counterpart: str,
        relationship: str = "",
        address: str = "",
        communication_preference: str = "",
        attributes: dict[str, Any] | None = None,
    ) -> WriteResult:
        return await self.put(
            MemoryRecord(
                kind=MemoryKind.RELATION,
                scope=scope,
                content=f"relationship={relationship} address={address}",
                authority=FactAuthority.DERIVED_SUMMARY,
                extractor="relation_writer",
                metadata={
                    "counterpart": counterpart,
                    "relationship": relationship,
                    "address": address,
                    "communication_preference": communication_preference,
                    **(attributes or {}),
                },
            )
        )

    @abstractmethod
    async def search(
        self,
        query: str,
        scopes: list[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> list[RecallResult]: ...

    async def scan(
        self,
        scope: MemoryScope,
        *,
        filters: MemoryFilter | None = None,
        cursor: str = "",
        limit: int = 100,
    ) -> MemoryPage:
        """Read oldest-first; return a resumable cursor even on the final page."""
        raise NotImplementedError("backend does not support paginated scans")

    @abstractmethod
    async def list_recent_owner_messages(
        self, scope: MemoryScope, *, limit: int = 5
    ) -> list[ChatMessage]: ...

    @abstractmethod
    async def get(self, scope: MemoryScope, memory_id: str) -> MemoryRecord | None: ...

    @abstractmethod
    async def transition(
        self,
        scope: MemoryScope,
        memory_id: str,
        to_state: MemoryState,
        *,
        expected_state: MemoryState | None = None,
    ) -> MemoryRecord: ...

    @abstractmethod
    async def forget(
        self, scope: MemoryScope, memory_id: str, *, hard: bool = False
    ) -> bool: ...

    @abstractmethod
    async def health(self) -> dict[str, Any]: ...

    async def close(self) -> None:
        """Release backend resources; no-op for stores without resources."""
