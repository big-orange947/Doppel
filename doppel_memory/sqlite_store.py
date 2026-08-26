"""SQLiteStore：零配置默认后端（本地文件、无需 Neo4j/LLM）。

- 检索：FTS5 关键词 + scope 过滤 + metadata filter；``semantic_search=False`` 如实声明。
- 幂等：事件表按 (scope_group, message_id/event_id) 唯一约束。
- 支持硬删除/事务；单文件即记忆库，适合默认接入与示例。
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    scope_user TEXT NOT NULL,
    scope_agent TEXT NOT NULL DEFAULT '',
    scope_platform TEXT NOT NULL DEFAULT '',
    scope_chat_type TEXT NOT NULL DEFAULT '',
    scope_chat_id TEXT NOT NULL DEFAULT '',
    scope_group TEXT NOT NULL,
    content TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT '',
    authority TEXT NOT NULL DEFAULT 'derived_summary',
    state TEXT NOT NULL DEFAULT 'confirmed',
    tags TEXT NOT NULL DEFAULT '[]',
    importance REAL NOT NULL DEFAULT 0.5,
    source_event_id TEXT NOT NULL DEFAULT '',
    source_message_id TEXT NOT NULL DEFAULT '',
    extractor TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_memories_scope_group ON memories(scope_group);
CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);
CREATE INDEX IF NOT EXISTS idx_memories_actor ON memories(actor);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_memories_message_id ON memories(source_message_id) WHERE source_message_id != '';
CREATE UNIQUE INDEX IF NOT EXISTS uq_memories_event_id ON memories(source_event_id) WHERE source_event_id != '';
"""


class SQLiteStore(MemoryStore):
    def __init__(self, database: str = "doppel.sqlite3") -> None:
        self._database = database
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()
        self._capabilities = StoreCapabilities(
            semantic_search=False,
            full_text_search=True,
            temporal_search=True,
            graph_relations=False,
            metadata_filter=True,
            hard_delete=True,
            transactions=True,
            reranking=False,
        )

    @property
    def capabilities(self) -> StoreCapabilities:
        return self._capabilities

    @property
    def is_enabled(self) -> bool:
        return True

    @property
    def database(self) -> str:
        return self._database

    async def _ensure_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            async with self._lock:
                if self._conn is None:
                    self._conn = await asyncio.to_thread(self._open)
        return self._conn

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._database, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        conn.commit()
        return conn

    # ---------------------------------------------------------------- 写入

    async def write_event(self, scope: MemoryScope, message: ChatMessage) -> MemoryRecord:
        return await self._insert(
            scope=scope,
            kind=MemoryKind.EVENT,
            content=message.text,
            actor=message.actor.value,
            authority=message.fact_authority,
            source_event_id=message.event_id,
            source_message_id=message.message_id,
            extractor="ingestor",
            created_at=message.at or _now(),
            metadata={"message_type": message.message_type, "reply_to_id": message.reply_to_id},
            message=message,
        )

    async def write_background(
        self,
        scope: MemoryScope,
        content: str,
        tags: list[str] | None = None,
        *,
        importance: float = 0.5,
        source: str = "manual",
    ) -> MemoryRecord:
        return await self._insert(
            scope=scope,
            kind=MemoryKind.BACKGROUND,
            content=content,
            extractor=source,
            tags=list(tags or []),
            importance=importance,
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
    ) -> MemoryRecord:
        return await self._insert(
            scope=scope,
            kind=MemoryKind.RELATION,
            content=f"relationship={relationship} address={address}",
            extractor="relation_writer",
            metadata={
                "counterpart": counterpart,
                "relationship": relationship,
                "address": address,
                "communication_preference": communication_preference,
                **(attributes or {}),
            },
        )

    async def _insert(
        self,
        *,
        scope: MemoryScope,
        kind: str,
        content: str,
        actor: str = "",
        authority: FactAuthority | None = None,
        tags: list[str] | None = None,
        importance: float = 0.5,
        source_event_id: str = "",
        source_message_id: str = "",
        extractor: str = "",
        created_at: str = "",
        metadata: dict[str, Any] | None = None,
        message: ChatMessage | None = None,
    ) -> MemoryRecord:
        conn = await self._ensure_conn()
        memory_id = _new_id(kind)
        created = created_at or _now()
        row = (
            memory_id,
            kind,
            scope.user_id,
            scope.agent_id,
            scope.platform,
            scope.chat_type,
            scope.chat_id,
            scope.group_id,
            content,
            actor,
            (authority or FactAuthority.DERIVED_SUMMARY).value,
            MemoryState.CONFIRMED.value,
            json.dumps(tags or [], ensure_ascii=False),
            importance,
            source_event_id,
            source_message_id,
            extractor,
            created,
            created,
            json.dumps(metadata or {}, ensure_ascii=False),
        )

        def _run() -> str | None:
            # 事件幂等：同 identity_key（message_id 或 event_id）跳过；空串不参与匹配。
            if kind == MemoryKind.EVENT and (source_message_id or source_event_id):
                existing = None
                if source_message_id:
                    existing = conn.execute(
                        "SELECT id FROM memories WHERE source_message_id=? LIMIT 1",
                        (source_message_id,),
                    ).fetchone()
                if existing is None and source_event_id:
                    existing = conn.execute(
                        "SELECT id FROM memories WHERE source_event_id=? LIMIT 1",
                        (source_event_id,),
                    ).fetchone()
                if existing:
                    return None
            conn.execute(
                """INSERT OR IGNORE INTO memories
                   (id, kind, scope_user, scope_agent, scope_platform, scope_chat_type,
                    scope_chat_id, scope_group, content, actor, authority, state, tags,
                    importance, source_event_id, source_message_id, extractor,
                    created_at, updated_at, metadata_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                row,
            )
            conn.commit()
            return memory_id

        inserted = await asyncio.to_thread(_run)
        if inserted is None:
            return MemoryRecord(memory_id="", scope=scope)
        return await self.get(inserted) or MemoryRecord(memory_id=inserted, scope=scope)

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
                "search requires explicit scopes; Doppel refuses unscoped search."
            )
        conn = await self._ensure_conn()
        filter_obj = filters or MemoryFilter()

        def _run() -> list[RecallResult]:
            group_ids = [scope.group_id for scope in scopes]
            params: list[Any] = []
            where = [f"scope_group IN ({','.join('?' * len(group_ids))})"]
            params.extend(group_ids)
            query_text = str(query or "").strip()
            if query_text:
                where.append("content LIKE ? ESCAPE '\\'")
                params.append(f"%{_escape_like(query_text)}%")
            sql = "SELECT memories.* FROM memories WHERE " + " AND ".join(where)
            if filter_obj.importance_min is not None:
                sql += " AND importance >= ?"
                params.append(filter_obj.importance_min)
            if filter_obj.time_from:
                sql += " AND created_at >= ?"
                params.append(filter_obj.time_from)
            if filter_obj.time_to:
                sql += " AND created_at <= ?"
                params.append(filter_obj.time_to)
            if filter_obj.kinds:
                sql += f" AND kind IN ({','.join('?' * len(filter_obj.kinds))})"
                params.extend(filter_obj.kinds)
            if filter_obj.actors:
                sql += f" AND actor IN ({','.join('?' * len(filter_obj.actors))})"
                params.extend(filter_obj.actors)
            if filter_obj.exclude_actors:
                sql += f" AND actor NOT IN ({','.join('?' * len(filter_obj.exclude_actors))})"
                params.extend(filter_obj.exclude_actors)
            if filter_obj.authorities:
                sql += f" AND authority IN ({','.join('?' * len(filter_obj.authorities))})"
                params.extend(a.value for a in filter_obj.authorities)
            if filter_obj.exclude_authorities:
                sql += f" AND authority NOT IN ({','.join('?' * len(filter_obj.exclude_authorities))})"
                params.extend(a.value for a in filter_obj.exclude_authorities)
            if filter_obj.states:
                sql += f" AND state IN ({','.join('?' * len(filter_obj.states))})"
                params.extend(s.value for s in filter_obj.states)
            if filter_obj.tags:
                for tag in filter_obj.tags:
                    sql += " AND tags LIKE ?"
                    params.append(f'%"{tag}"%')
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_recall(row) for row in rows]

        return await asyncio.to_thread(_run)

    async def list_recent_owner_messages(
        self, scope: MemoryScope, *, limit: int = 5
    ) -> list[ChatMessage]:
        conn = await self._ensure_conn()

        def _run() -> list[ChatMessage]:
            rows = conn.execute(
                """SELECT content, created_at, source_event_id, source_message_id
                   FROM memories WHERE scope_group=? AND kind='event' AND actor='owner'
                   ORDER BY created_at DESC LIMIT ?""",
                (scope.group_id, limit),
            ).fetchall()
            return [
                ChatMessage(
                    actor="owner",
                    text=row["content"],
                    at=row["created_at"],
                    event_id=row["source_event_id"] or "",
                    message_id=row["source_message_id"] or "",
                )
                for row in reversed(rows)
            ]

        return await asyncio.to_thread(_run)

    # ---------------------------------------------------------------- 管理

    async def get(self, memory_id: str) -> MemoryRecord | None:
        conn = await self._ensure_conn()

        def _run() -> MemoryRecord | None:
            row = conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            return self._row_to_record(row) if row else None

        return await asyncio.to_thread(_run)

    async def forget(self, memory_id: str, *, hard: bool = False) -> bool:
        conn = await self._ensure_conn()

        def _run() -> bool:
            if hard:
                cursor = conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
            else:
                cursor = conn.execute(
                    "UPDATE memories SET state='expired', updated_at=? WHERE id=?",
                    (_now(), memory_id),
                )
            conn.commit()
            return cursor.rowcount > 0

        return await asyncio.to_thread(_run)

    async def health(self) -> dict[str, Any]:
        conn = await self._ensure_conn()

        def _run() -> dict[str, Any]:
            count = conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()["c"]
            return {"enabled": True, "ok": True, "records": count, "database": self._database}

        return await asyncio.to_thread(_run)

    async def close(self) -> None:
        if self._conn is not None:
            await asyncio.to_thread(self._conn.close)
            self._conn = None

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            memory_id=row["id"],
            kind=row["kind"],
            scope=MemoryScope(
                user_id=row["scope_user"],
                agent_id=row["scope_agent"],
                platform=row["scope_platform"],
                chat_type=row["scope_chat_type"],
                chat_id=row["scope_chat_id"],
            ),
            content=row["content"],
            actor=row["actor"],
            authority=FactAuthority(row["authority"]) if row["authority"] else FactAuthority.DERIVED_SUMMARY,
            state=MemoryState(row["state"]) if row["state"] else MemoryState.CONFIRMED,
            tags=json.loads(row["tags"] or "[]"),
            importance=row["importance"],
            source_event_id=row["source_event_id"],
            source_message_id=row["source_message_id"],
            extractor=row["extractor"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    @staticmethod
    def _row_to_recall(row: sqlite3.Row) -> RecallResult:
        return RecallResult(
            fact=row["content"],
            kind=row["kind"],
            scope=MemoryScope(
                user_id=row["scope_user"],
                agent_id=row["scope_agent"],
                platform=row["scope_platform"],
                chat_type=row["scope_chat_type"],
                chat_id=row["scope_chat_id"],
            ),
            memory_id=row["id"],
            actor=row["actor"],
            authority=FactAuthority(row["authority"]) if row["authority"] else FactAuthority.DERIVED_SUMMARY,
            source_event_id=row["source_event_id"],
            source_message_id=row["source_message_id"],
            extractor=row["extractor"],
            extracted_at=row["updated_at"],
            raw_text=row["content"],
            valid_at=row["created_at"],
            state=MemoryState(row["state"]) if row["state"] else MemoryState.CONFIRMED,
        )


def _escape_like(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _new_id(kind: str) -> str:
    digest = hashlib_hex(f"{kind}:{datetime.now(timezone.utc).isoformat()}")
    return f"{kind[:3]}-{digest[:12]}"


def hashlib_hex(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
