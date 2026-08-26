"""Deterministic in-memory reference backend."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from doppel_memory.models import (
    ACTIVE_MEMORY_STATES,
    Actor,
    ChatMessage,
    MemoryFilter,
    MemoryIsolationError,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    MemoryStateConflictError,
    RecallResult,
    StoreCapabilities,
    WriteResult,
    WriteStatus,
    utc_now,
)
from doppel_memory.store import MemoryStore


class InMemoryStore(MemoryStore):
    def __init__(self) -> None:
        self._records: dict[str, MemoryRecord] = {}
        self._idempotency: dict[tuple[str, str], str] = {}
        self._capabilities = StoreCapabilities(
            substring_search=True,
            temporal_search=True,
            hard_delete=True,
        )

    @property
    def capabilities(self) -> StoreCapabilities:
        return self._capabilities

    @property
    def is_enabled(self) -> bool:
        return True

    async def put(
        self, record: MemoryRecord, *, idempotency_key: str | None = None
    ) -> WriteResult:
        key = str(idempotency_key or record.idempotency_key or "").strip()
        index_key = (record.scope.scope_key, key)
        if key and index_key in self._idempotency:
            existing = self._records.get(self._idempotency[index_key])
            return WriteResult(
                status=WriteStatus.DUPLICATE,
                record=existing.model_copy(deep=True) if existing else None,
            )

        memory_id = record.memory_id or f"mem-{uuid4().hex}"
        if memory_id in self._records:
            return WriteResult(
                status=WriteStatus.FAILED,
                error_code="memory_id_conflict",
                message=f"memory_id already exists: {memory_id}",
            )
        stored = record.model_copy(
            update={
                "memory_id": memory_id,
                "idempotency_key": key,
            },
            deep=True,
        )
        self._records[memory_id] = stored
        if key:
            self._idempotency[index_key] = memory_id
        return WriteResult(
            status=WriteStatus.CREATED, record=stored.model_copy(deep=True)
        )

    async def search(
        self,
        query: str,
        scopes: list[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> list[RecallResult]:
        if not scopes:
            raise MemoryIsolationError("search requires at least one exact scope")
        if limit <= 0:
            return []
        allowed = {scope.scope_key for scope in scopes}
        filter_obj = filters or MemoryFilter()
        query_text = str(query or "").strip()
        records = sorted(
            self._records.values(), key=lambda item: item.created_at, reverse=True
        )
        results: list[RecallResult] = []
        for record in records:
            if record.scope.scope_key not in allowed:
                continue
            if not _matches(record, filter_obj):
                continue
            if query_text and not _contains(record, query_text):
                continue
            results.append(_to_recall(record))
            if len(results) >= limit:
                break
        return results

    async def list_recent_owner_messages(
        self, scope: MemoryScope, *, limit: int = 5
    ) -> list[ChatMessage]:
        if limit <= 0:
            return []
        records = sorted(
            self._records.values(), key=lambda item: item.created_at, reverse=True
        )
        samples = [
            ChatMessage(
                actor=Actor.OWNER,
                text=record.content,
                at=record.created_at,
                event_id=record.source_event_id,
                message_id=record.source_message_id,
                message_type=str(record.metadata.get("message_type", "message")),
                reply_to_id=str(record.metadata.get("reply_to_id", "")),
                quoted_message_id=str(record.metadata.get("quoted_message_id", "")),
                attachments=list(record.metadata.get("attachments", [])),
            )
            for record in records
            if record.scope.scope_key == scope.scope_key
            and record.kind == "event"
            and record.actor == Actor.OWNER
            and record.state in ACTIVE_MEMORY_STATES
        ][:limit]
        return list(reversed(samples))

    async def get(self, scope: MemoryScope, memory_id: str) -> MemoryRecord | None:
        record = self._records.get(memory_id)
        if record is None or record.scope.scope_key != scope.scope_key:
            return None
        return record.model_copy(deep=True)

    async def transition(
        self,
        scope: MemoryScope,
        memory_id: str,
        to_state: MemoryState,
        *,
        expected_state: MemoryState | None = None,
    ) -> MemoryRecord:
        record = self._records.get(memory_id)
        if record is None or record.scope.scope_key != scope.scope_key:
            raise KeyError(memory_id)
        if expected_state is not None and record.state != expected_state:
            raise MemoryStateConflictError(
                f"expected {expected_state.value}, found {record.state.value}"
            )
        updated = record.model_copy(
            update={
                "state": to_state,
                "updated_at": utc_now(),
                "version": record.version + 1,
            },
            deep=True,
        )
        self._records[memory_id] = updated
        return updated.model_copy(deep=True)

    async def forget(
        self, scope: MemoryScope, memory_id: str, *, hard: bool = False
    ) -> bool:
        record = self._records.get(memory_id)
        if record is None or record.scope.scope_key != scope.scope_key:
            return False
        if not hard:
            await self.transition(scope, memory_id, MemoryState.EXPIRED)
            return True
        del self._records[memory_id]
        if record.idempotency_key:
            self._idempotency.pop((scope.scope_key, record.idempotency_key), None)
        return True

    async def health(self) -> dict[str, Any]:
        return {"enabled": True, "ok": True, "records": len(self._records)}


def _contains(record: MemoryRecord, query: str) -> bool:
    return query in record.content or query in json.dumps(
        record.metadata, ensure_ascii=False
    )


def _matches(record: MemoryRecord, filters: MemoryFilter) -> bool:
    if filters.states is not None:
        if record.state not in filters.states:
            return False
    elif not filters.include_inactive and record.state not in ACTIVE_MEMORY_STATES:
        return False
    if filters.kinds is not None and record.kind not in filters.kinds:
        return False
    if filters.actors is not None and record.actor not in filters.actors:
        return False
    if filters.exclude_actors is not None and record.actor in filters.exclude_actors:
        return False
    if filters.authorities is not None and record.authority not in filters.authorities:
        return False
    if (
        filters.exclude_authorities is not None
        and record.authority in filters.exclude_authorities
    ):
        return False
    if filters.tags is not None and not filters.tags.issubset(record.tags):
        return False
    if (
        filters.importance_min is not None
        and record.importance < filters.importance_min
    ):
        return False
    if filters.time_from is not None and record.created_at < filters.time_from:
        return False
    return not (filters.time_to is not None and record.created_at > filters.time_to)


def _to_recall(record: MemoryRecord) -> RecallResult:
    return RecallResult(
        fact=record.content,
        kind=record.kind,
        scope=record.scope,
        memory_id=record.memory_id,
        actor=record.actor,
        authority=record.authority,
        source_event_id=record.source_event_id,
        source_message_id=record.source_message_id,
        extractor=record.extractor,
        extracted_at=record.updated_at,
        raw_text=record.content,
        derived_chain=list(record.metadata.get("derived_chain", [])),
        valid_at=record.created_at,
        state=record.state,
    )
