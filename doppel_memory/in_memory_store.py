"""InMemoryStore：零依赖内存后端（测试与示例用，非持久化）。

能力声明：无语义检索（仅子串匹配）、无持久化；开发/示例场景够用。
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from doppel_memory.models import (
    ChatMessage,
    FactAuthority,
    MemoryFilter,
    MemoryIsolationError,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    RecallResult,
    StoreCapabilities,
)
from doppel_memory.store import MemoryStore


class InMemoryStore(MemoryStore):
    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []
        self._owner_samples: dict[str, list[ChatMessage]] = {}
        self._seen_keys: dict[str, set[str]] = {}
        self._capabilities = StoreCapabilities(
            semantic_search=False,
            full_text_search=True,
            temporal_search=True,
            graph_relations=False,
            metadata_filter=True,
            hard_delete=True,
            transactions=False,
            reranking=False,
        )

    @property
    def capabilities(self) -> StoreCapabilities:
        return self._capabilities

    @property
    def is_enabled(self) -> bool:
        return True

    # ---------------------------------------------------------------- 写入

    async def write_event(self, scope: MemoryScope, message: ChatMessage) -> MemoryRecord:
        record = self._upsert_event(scope, message)
        return record if record else MemoryRecord(memory_id="", scope=scope)

    def _upsert_event(self, scope: MemoryScope, message: ChatMessage) -> MemoryRecord | None:
        key = message.identity_key
        seen = self._seen_keys.setdefault(scope.group_id, set())
        if key and key in seen:
            return None
        if key:
            seen.add(key)
        record = MemoryRecord(
            memory_id=self._new_id("evt"),
            kind=MemoryKind.EVENT,
            scope=scope,
            content=message.text,
            actor=message.actor.value,
            authority=message.fact_authority,
            source_event_id=message.event_id,
            source_message_id=message.message_id,
            extractor="ingestor",
            created_at=message.at or _now(),
            updated_at=message.at or _now(),
            metadata={"message_type": message.message_type, "reply_to_id": message.reply_to_id},
        )
        self._records.append(record)
        if message.actor.value == "owner" and message.text:
            samples = self._owner_samples.setdefault(scope.group_id, [])
            samples.append(message)
            if len(samples) > 50:
                del samples[0]
        return record

    async def write_background(
        self,
        scope: MemoryScope,
        content: str,
        tags: list[str] | None = None,
        *,
        importance: float = 0.5,
        source: str = "manual",
    ) -> MemoryRecord:
        record = MemoryRecord(
            memory_id=self._new_id("bg"),
            kind=MemoryKind.BACKGROUND,
            scope=scope,
            content=content,
            state=MemoryState.CONFIRMED,
            tags=list(tags or []),
            importance=importance,
            extractor=source,
            created_at=_now(),
            updated_at=_now(),
        )
        self._records.append(record)
        return record

    async def write_relation(
        self,
        scope: MemoryScope,
        *,
        counterpart: str,
        relationship: str = "",
        address: str = "",
        communication_preference: str = "",
        attributes: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        record = MemoryRecord(
            memory_id=self._new_id("rel"),
            kind=MemoryKind.RELATION,
            scope=scope,
            content=f"relationship={relationship} address={address}",
            state=MemoryState.CONFIRMED,
            created_at=_now(),
            updated_at=_now(),
            metadata={
                "counterpart": counterpart,
                "relationship": relationship,
                "address": address,
                "communication_preference": communication_preference,
                **(attributes or {}),
            },
        )
        self._records.append(record)
        return record

    # ---------------------------------------------------------------- 检索

    async def search(
        self,
        query: str,
        scopes: list[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> list[RecallResult]:
        if not scopes:
            raise MemoryIsolationError(
                "search requires explicit scopes; Doppel refuses unscoped search "
                "to prevent memory leaking across users/sessions."
            )
        filter_obj = filters or MemoryFilter()
        results: list[RecallResult] = []
        for record in self._records:
            if not any(scope.matches(record.scope) for scope in scopes):
                continue
            if not self._matches(record, filter_obj):
                continue
            query_text = str(query or "").strip()
            if query_text and not self._contains(record, query_text):
                continue
            results.append(self._to_recall(record))
        return results[:limit]

    async def list_recent_owner_messages(
        self, scope: MemoryScope, *, limit: int = 5
    ) -> list[ChatMessage]:
        samples = []
        for record in reversed(self._records):
            if record.scope.group_id != scope.group_id:
                continue
            if record.kind == MemoryKind.EVENT and record.actor == "owner":
                samples.append(
                    ChatMessage(actor="owner", text=record.content, at=record.created_at)
                )
            if len(samples) >= limit:
                break
        return list(reversed(samples))

    # ---------------------------------------------------------------- 管理

    async def forget(self, memory_id: str, *, hard: bool = False) -> bool:
        target = next((r for r in self._records if r.memory_id == memory_id), None)
        if target is None:
            return False
        if hard:
            self._records.remove(target)
        else:
            target.state = MemoryState.EXPIRED
            target.updated_at = _now()
        return True

    async def health(self) -> dict[str, Any]:
        return {"enabled": True, "ok": True, "records": len(self._records)}

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _contains(record: MemoryRecord, query: str) -> bool:
        if query in record.content:
            return True
        import json

        return query in json.dumps(record.metadata, ensure_ascii=False)

    @staticmethod
    def _matches(record: MemoryRecord, f: MemoryFilter) -> bool:
        if f.kinds is not None and record.kind not in f.kinds:
            return False
        if f.actors is not None and record.actor not in f.actors:
            return False
        if f.exclude_actors is not None and record.actor in f.exclude_actors:
            return False
        if f.authorities is not None and record.authority not in f.authorities:
            return False
        if f.exclude_authorities is not None and record.authority in f.exclude_authorities:
            return False
        if f.states is not None and record.state not in f.states:
            return False
        if f.tags is not None and not f.tags.issubset(set(record.tags)):
            return False
        if f.importance_min is not None and record.importance < f.importance_min:
            return False
        if f.time_from and record.created_at and record.created_at < f.time_from:
            return False
        if f.time_to and record.created_at and record.created_at > f.time_to:
            return False
        return True

    @staticmethod
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
            valid_at=record.created_at,
            state=record.state,
        )

    @staticmethod
    def _new_id(prefix: str) -> str:
        digest = hashlib.sha256(f"{prefix}:{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:12]
        return f"{prefix}-{digest}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
