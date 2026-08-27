"""Concurrent-safe SQLite reference backend with schema migrations."""

from __future__ import annotations

import asyncio
import json
import math
import re
import sqlite3
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from doppel_memory._cursor import decode_cursor, encode_cursor
from doppel_memory.models import (
    ACTIVE_MEMORY_STATES,
    Actor,
    ChatMessage,
    FactAuthority,
    MemoryFilter,
    MemoryIsolationError,
    MemoryPage,
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

SCHEMA_VERSION = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS doppel_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    scope_user TEXT NOT NULL,
    scope_agent TEXT NOT NULL,
    scope_platform TEXT NOT NULL DEFAULT '',
    scope_chat_type TEXT NOT NULL DEFAULT '',
    scope_chat_id TEXT NOT NULL DEFAULT '',
    scope_extra_json TEXT NOT NULL DEFAULT '{}',
    scope_key TEXT NOT NULL,
    content TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT '',
    authority TEXT NOT NULL DEFAULT 'derived_summary',
    state TEXT NOT NULL DEFAULT 'confirmed',
    tags TEXT NOT NULL DEFAULT '[]',
    importance REAL NOT NULL DEFAULT 0.5,
    idempotency_key TEXT NOT NULL DEFAULT '',
    source_event_id TEXT NOT NULL DEFAULT '',
    source_message_id TEXT NOT NULL DEFAULT '',
    extractor TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
"""

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_memories_scope_key ON memories(scope_key);
CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);
CREATE INDEX IF NOT EXISTS idx_memories_actor ON memories(actor);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_memories_scope_idempotency
ON memories(scope_key, idempotency_key) WHERE idempotency_key != '';
"""

_FTS_TRIGGERS = (
    """CREATE TRIGGER IF NOT EXISTS memories_fts_insert AFTER INSERT ON memories BEGIN
           INSERT INTO memories_fts(rowid, content, metadata_json)
           VALUES (new.rowid, new.content, new.metadata_json);
       END""",
    """CREATE TRIGGER IF NOT EXISTS memories_fts_delete AFTER DELETE ON memories BEGIN
           INSERT INTO memories_fts(memories_fts, rowid, content, metadata_json)
           VALUES ('delete', old.rowid, old.content, old.metadata_json);
       END""",
    """CREATE TRIGGER IF NOT EXISTS memories_fts_update AFTER UPDATE ON memories BEGIN
           INSERT INTO memories_fts(memories_fts, rowid, content, metadata_json)
           VALUES ('delete', old.rowid, old.content, old.metadata_json);
           INSERT INTO memories_fts(rowid, content, metadata_json)
           VALUES (new.rowid, new.content, new.metadata_json);
       END""",
)


class SQLiteStore(MemoryStore):
    def __init__(
        self, database: str = "doppel.sqlite3", *, enable_fts: bool = True
    ) -> None:
        self._database = database
        self._enable_fts = enable_fts
        self._fts_available = False
        self._conn: sqlite3.Connection | None = None
        self._init_lock = asyncio.Lock()
        self._operation_lock = asyncio.Lock()
        self._capabilities = StoreCapabilities(
            substring_search=True,
            full_text_search=enable_fts,
            temporal_search=True,
            hard_delete=True,
            transactions=True,
            pagination=True,
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
            async with self._init_lock:
                if self._conn is None:
                    self._conn = await asyncio.to_thread(self._open)
        return self._conn

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._database, check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        if self._database != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL")
        self._fts_available = self._migrate(conn, enable_fts=self._enable_fts)
        if self._capabilities.full_text_search != self._fts_available:
            self._capabilities = self._capabilities.model_copy(
                update={"full_text_search": self._fts_available}
            )
        return conn

    @staticmethod
    def _migrate(conn: sqlite3.Connection, *, enable_fts: bool) -> bool:
        conn.executescript(_SCHEMA)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(memories)")}
        additions = {
            "scope_extra_json": "TEXT NOT NULL DEFAULT '{}'",
            "scope_key": "TEXT NOT NULL DEFAULT ''",
            "idempotency_key": "TEXT NOT NULL DEFAULT ''",
            "version": "INTEGER NOT NULL DEFAULT 1",
        }
        for name, declaration in additions.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE memories ADD COLUMN {name} {declaration}")

        conn.execute("DROP INDEX IF EXISTS uq_memories_message_id")
        conn.execute("DROP INDEX IF EXISTS uq_memories_event_id")
        rows = conn.execute(
            """SELECT id, kind, scope_user, scope_agent, scope_platform,
                      scope_chat_type, scope_chat_id, scope_extra_json,
                      scope_key, idempotency_key, source_message_id, source_event_id,
                      created_at, updated_at
               FROM memories"""
        ).fetchall()
        for row in rows:
            extra = json.loads(row["scope_extra_json"] or "{}")
            scope = MemoryScope(
                user_id=row["scope_user"],
                agent_id=row["scope_agent"],
                platform=row["scope_platform"],
                chat_type=row["scope_chat_type"],
                chat_id=row["scope_chat_id"],
                extra_dimensions=extra,
            )
            key = row["idempotency_key"] or ""
            if not key and row["kind"] == "event":
                identity = row["source_message_id"] or row["source_event_id"] or ""
                key = f"event:{identity}" if identity else ""
            conn.execute(
                """UPDATE memories
                   SET scope_key=?, idempotency_key=?, created_at=?, updated_at=?
                   WHERE id=?""",
                (
                    scope.scope_key,
                    key,
                    _normalize_legacy_time(row["created_at"]),
                    _normalize_legacy_time(row["updated_at"]),
                    row["id"],
                ),
            )
        conn.executescript(_INDEXES)
        fts_available = SQLiteStore._setup_fts(conn) if enable_fts else False
        conn.execute(
            "INSERT OR REPLACE INTO doppel_meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
        return fts_available

    @staticmethod
    def _setup_fts(conn: sqlite3.Connection) -> bool:
        try:
            conn.execute(
                """CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                       content,
                       metadata_json,
                       content='memories',
                       content_rowid='rowid',
                       tokenize='unicode61'
                   )"""
            )
            for statement in _FTS_TRIGGERS:
                conn.execute(statement)
            conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild')")
        except sqlite3.OperationalError:
            return False
        return True

    async def put(
        self, record: MemoryRecord, *, idempotency_key: str | None = None
    ) -> WriteResult:
        conn = await self._ensure_conn()
        key = str(idempotency_key or record.idempotency_key or "").strip()
        memory_id = record.memory_id or f"mem-{uuid4().hex}"
        stored = record.model_copy(
            update={"memory_id": memory_id, "idempotency_key": key}, deep=True
        )

        def _run() -> WriteResult:
            if key:
                duplicate = conn.execute(
                    "SELECT * FROM memories WHERE scope_key=? AND idempotency_key=? LIMIT 1",
                    (stored.scope.scope_key, key),
                ).fetchone()
                if duplicate:
                    return WriteResult(
                        status=WriteStatus.DUPLICATE,
                        record=self._row_to_record(duplicate),
                    )
            try:
                conn.execute(
                    """INSERT INTO memories
                       (id, kind, scope_user, scope_agent, scope_platform, scope_chat_type,
                        scope_chat_id, scope_extra_json, scope_key, content, actor, authority,
                        state, tags, importance, idempotency_key, source_event_id,
                        source_message_id, extractor, created_at, updated_at, version,
                        metadata_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    self._record_row(stored),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                if key:
                    duplicate = conn.execute(
                        "SELECT * FROM memories WHERE scope_key=? AND idempotency_key=? LIMIT 1",
                        (stored.scope.scope_key, key),
                    ).fetchone()
                    if duplicate:
                        return WriteResult(
                            status=WriteStatus.DUPLICATE,
                            record=self._row_to_record(duplicate),
                        )
                return WriteResult(
                    status=WriteStatus.FAILED,
                    error_code="integrity_error",
                    message=str(exc),
                )
            return WriteResult(status=WriteStatus.CREATED, record=stored)

        async with self._operation_lock:
            return await asyncio.to_thread(_run)

    @staticmethod
    def _record_row(record: MemoryRecord) -> tuple[Any, ...]:
        return (
            record.memory_id,
            record.kind,
            record.scope.user_id,
            record.scope.agent_id,
            record.scope.platform,
            record.scope.chat_type,
            record.scope.chat_id,
            json.dumps(
                record.scope.extra_dimensions, ensure_ascii=False, sort_keys=True
            ),
            record.scope.scope_key,
            record.content,
            record.actor,
            record.authority.value,
            record.state.value,
            json.dumps(record.tags, ensure_ascii=False),
            record.importance,
            record.idempotency_key,
            record.source_event_id,
            record.source_message_id,
            record.extractor,
            record.created_at.isoformat(),
            record.updated_at.isoformat(),
            record.version,
            json.dumps(record.metadata, ensure_ascii=False),
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
        conn = await self._ensure_conn()
        filter_obj = filters or MemoryFilter()

        def _run() -> list[RecallResult]:
            query_text = str(query or "").strip()
            fts_query = _fts_query(query_text)

            def _select(*, full_text: bool) -> list[sqlite3.Row]:
                scope_keys = list(dict.fromkeys(scope.scope_key for scope in scopes))
                placeholders = ",".join("?" for _ in scope_keys)
                where = [f"m.scope_key IN ({placeholders})"]
                params: list[Any] = list(scope_keys)
                if query_text:
                    if full_text:
                        where.append("memories_fts MATCH ?")
                        params.append(fts_query)
                    else:
                        where.append(
                            "(m.content LIKE ? ESCAPE '\\' "
                            "OR m.metadata_json LIKE ? ESCAPE '\\')"
                        )
                        pattern = f"%{_escape_like(query_text)}%"
                        params.extend((pattern, pattern))
                if filter_obj.states is not None:
                    values = [state.value for state in filter_obj.states]
                    where.append(f"m.state IN ({','.join('?' for _ in values)})")
                    params.extend(values)
                elif not filter_obj.include_inactive:
                    values = [state.value for state in ACTIVE_MEMORY_STATES]
                    where.append(f"m.state IN ({','.join('?' for _ in values)})")
                    params.extend(values)
                if filter_obj.kinds:
                    values = list(filter_obj.kinds)
                    where.append(f"m.kind IN ({','.join('?' for _ in values)})")
                    params.extend(values)
                if filter_obj.actors:
                    values = list(filter_obj.actors)
                    where.append(f"m.actor IN ({','.join('?' for _ in values)})")
                    params.extend(values)
                if filter_obj.exclude_actors:
                    values = list(filter_obj.exclude_actors)
                    where.append(f"m.actor NOT IN ({','.join('?' for _ in values)})")
                    params.extend(values)
                if filter_obj.authorities:
                    values = [authority.value for authority in filter_obj.authorities]
                    where.append(f"m.authority IN ({','.join('?' for _ in values)})")
                    params.extend(values)
                if filter_obj.exclude_authorities:
                    values = [
                        authority.value for authority in filter_obj.exclude_authorities
                    ]
                    where.append(
                        f"m.authority NOT IN ({','.join('?' for _ in values)})"
                    )
                    params.extend(values)
                if filter_obj.importance_min is not None:
                    where.append("m.importance >= ?")
                    params.append(filter_obj.importance_min)
                if filter_obj.time_from is not None:
                    where.append("m.created_at >= ?")
                    params.append(filter_obj.time_from.isoformat())
                if filter_obj.time_to is not None:
                    where.append("m.created_at <= ?")
                    params.append(filter_obj.time_to.isoformat())
                if filter_obj.tags:
                    for tag in filter_obj.tags:
                        where.append("m.tags LIKE ? ESCAPE '\\'")
                        params.append(
                            f"%{_escape_like(json.dumps(tag, ensure_ascii=False))}%"
                        )

                if full_text:
                    select = "SELECT m.*, bm25(memories_fts) AS fts_rank"
                    source = (
                        " FROM memories_fts JOIN memories AS m "
                        "ON m.rowid=memories_fts.rowid"
                    )
                    order = " ORDER BY fts_rank ASC, m.created_at DESC"
                else:
                    select = "SELECT m.*"
                    source = " FROM memories AS m"
                    order = " ORDER BY m.created_at DESC"
                params.append(limit)
                return conn.execute(
                    select
                    + source
                    + " WHERE "
                    + " AND ".join(where)
                    + order
                    + " LIMIT ?",
                    params,
                ).fetchall()

            rows: list[sqlite3.Row] = []
            used_full_text = False
            if query_text and fts_query and self._fts_available:
                try:
                    rows = _select(full_text=True)
                    used_full_text = bool(rows)
                except sqlite3.OperationalError:
                    rows = []
            if not rows:
                rows = _select(full_text=False)
            return [
                self._row_to_recall(
                    row,
                    similarity=(
                        _fts_similarity(float(row["fts_rank"]))
                        if used_full_text
                        else 0.0
                    ),
                )
                for row in rows
            ]

        async with self._operation_lock:
            return await asyncio.to_thread(_run)

    async def scan(
        self,
        scope: MemoryScope,
        *,
        filters: MemoryFilter | None = None,
        cursor: str = "",
        limit: int = 100,
    ) -> MemoryPage:
        """Scan one exact scope in stable oldest-first order."""
        if limit <= 0:
            return MemoryPage()
        conn = await self._ensure_conn()
        filter_obj = filters or MemoryFilter()

        def _run() -> MemoryPage:
            where = ["scope_key=?"]
            params: list[Any] = [scope.scope_key]
            if cursor:
                after_time, after_id = decode_cursor(cursor)
                after_iso = after_time.astimezone(UTC).isoformat()
                where.append("(created_at > ? OR (created_at = ? AND id > ?))")
                params.extend((after_iso, after_iso, after_id))
            if filter_obj.states is not None:
                values = [state.value for state in filter_obj.states]
                where.append(f"state IN ({','.join('?' for _ in values)})")
                params.extend(values)
            elif not filter_obj.include_inactive:
                values = [state.value for state in ACTIVE_MEMORY_STATES]
                where.append(f"state IN ({','.join('?' for _ in values)})")
                params.extend(values)
            if filter_obj.kinds:
                values = list(filter_obj.kinds)
                where.append(f"kind IN ({','.join('?' for _ in values)})")
                params.extend(values)
            if filter_obj.actors:
                values = list(filter_obj.actors)
                where.append(f"actor IN ({','.join('?' for _ in values)})")
                params.extend(values)
            if filter_obj.exclude_actors:
                values = list(filter_obj.exclude_actors)
                where.append(f"actor NOT IN ({','.join('?' for _ in values)})")
                params.extend(values)
            if filter_obj.authorities:
                values = [authority.value for authority in filter_obj.authorities]
                where.append(f"authority IN ({','.join('?' for _ in values)})")
                params.extend(values)
            if filter_obj.exclude_authorities:
                values = [
                    authority.value for authority in filter_obj.exclude_authorities
                ]
                where.append(f"authority NOT IN ({','.join('?' for _ in values)})")
                params.extend(values)
            if filter_obj.importance_min is not None:
                where.append("importance >= ?")
                params.append(filter_obj.importance_min)
            if filter_obj.time_from is not None:
                where.append("created_at >= ?")
                params.append(filter_obj.time_from.astimezone(UTC).isoformat())
            if filter_obj.time_to is not None:
                where.append("created_at <= ?")
                params.append(filter_obj.time_to.astimezone(UTC).isoformat())
            if filter_obj.tags:
                for tag in filter_obj.tags:
                    where.append("tags LIKE ? ESCAPE '\\'")
                    params.append(
                        f"%{_escape_like(json.dumps(tag, ensure_ascii=False))}%"
                    )

            params.append(limit + 1)
            rows = conn.execute(
                "SELECT * FROM memories WHERE "
                + " AND ".join(where)
                + " ORDER BY created_at ASC, id ASC LIMIT ?",
                params,
            ).fetchall()
            has_more = len(rows) > limit
            records = [self._row_to_record(row) for row in rows[:limit]]
            next_cursor = cursor
            if records:
                last = records[-1]
                next_cursor = encode_cursor(last.created_at, last.memory_id)
            return MemoryPage(
                records=records, next_cursor=next_cursor, has_more=has_more
            )

        async with self._operation_lock:
            return await asyncio.to_thread(_run)

    async def list_recent_owner_messages(
        self, scope: MemoryScope, *, limit: int = 5
    ) -> list[ChatMessage]:
        if limit <= 0:
            return []
        conn = await self._ensure_conn()

        def _run() -> list[ChatMessage]:
            active = [state.value for state in ACTIVE_MEMORY_STATES]
            rows = conn.execute(
                """SELECT * FROM memories
                   WHERE scope_key=? AND kind='event' AND actor=?
                     AND state IN (?, ?)
                   ORDER BY created_at DESC LIMIT ?""",
                (scope.scope_key, Actor.OWNER, active[0], active[1], limit),
            ).fetchall()
            messages = []
            for row in reversed(rows):
                metadata = json.loads(row["metadata_json"] or "{}")
                messages.append(
                    ChatMessage(
                        actor=Actor.OWNER,
                        text=row["content"],
                        at=row["created_at"],
                        event_id=row["source_event_id"],
                        message_id=row["source_message_id"],
                        sender_id=metadata.get("sender_id", ""),
                        message_type=metadata.get("message_type", "message"),
                        reply_to_id=metadata.get("reply_to_id", ""),
                        quoted_message_id=metadata.get("quoted_message_id", ""),
                        thread_id=metadata.get("thread_id", ""),
                        thread_root_id=metadata.get("thread_root_id", ""),
                        attachments=metadata.get("attachments", []),
                        raw=metadata.get("raw", {}),
                        parts=metadata.get("parts", []),
                    )
                )
            return messages

        async with self._operation_lock:
            return await asyncio.to_thread(_run)

    async def get(self, scope: MemoryScope, memory_id: str) -> MemoryRecord | None:
        conn = await self._ensure_conn()

        def _run() -> MemoryRecord | None:
            row = conn.execute(
                "SELECT * FROM memories WHERE id=? AND scope_key=?",
                (memory_id, scope.scope_key),
            ).fetchone()
            return self._row_to_record(row) if row else None

        async with self._operation_lock:
            return await asyncio.to_thread(_run)

    async def transition(
        self,
        scope: MemoryScope,
        memory_id: str,
        to_state: MemoryState,
        *,
        expected_state: MemoryState | None = None,
    ) -> MemoryRecord:
        conn = await self._ensure_conn()

        def _run() -> MemoryRecord:
            where = "id=? AND scope_key=?"
            params: list[Any] = [
                to_state.value,
                utc_now().isoformat(),
                memory_id,
                scope.scope_key,
            ]
            if expected_state is not None:
                where += " AND state=?"
                params.append(expected_state.value)
            cursor = conn.execute(
                f"UPDATE memories SET state=?, updated_at=?, version=version+1 WHERE {where}",
                params,
            )
            if cursor.rowcount == 0:
                conn.rollback()
                current = conn.execute(
                    "SELECT state FROM memories WHERE id=? AND scope_key=?",
                    (memory_id, scope.scope_key),
                ).fetchone()
                if current is None:
                    raise KeyError(memory_id)
                raise MemoryStateConflictError(
                    f"expected {expected_state.value if expected_state else '*'}, found {current['state']}"
                )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM memories WHERE id=? AND scope_key=?",
                (memory_id, scope.scope_key),
            ).fetchone()
            return self._row_to_record(row)

        async with self._operation_lock:
            return await asyncio.to_thread(_run)

    async def forget(
        self, scope: MemoryScope, memory_id: str, *, hard: bool = False
    ) -> bool:
        if not hard:
            try:
                await self.transition(scope, memory_id, MemoryState.EXPIRED)
                return True
            except KeyError:
                return False
        conn = await self._ensure_conn()

        def _run() -> bool:
            cursor = conn.execute(
                "DELETE FROM memories WHERE id=? AND scope_key=?",
                (memory_id, scope.scope_key),
            )
            conn.commit()
            return cursor.rowcount > 0

        async with self._operation_lock:
            return await asyncio.to_thread(_run)

    async def health(self) -> dict[str, Any]:
        conn = await self._ensure_conn()

        def _run() -> dict[str, Any]:
            count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            version = conn.execute(
                "SELECT value FROM doppel_meta WHERE key='schema_version'"
            ).fetchone()[0]
            return {
                "enabled": True,
                "ok": True,
                "records": count,
                "database": self._database,
                "schema_version": int(version),
                "full_text_search": self._fts_available,
            }

        async with self._operation_lock:
            return await asyncio.to_thread(_run)

    async def close(self) -> None:
        async with self._operation_lock:
            if self._conn is not None:
                await asyncio.to_thread(self._conn.close)
                self._conn = None

    @staticmethod
    def _row_scope(row: sqlite3.Row) -> MemoryScope:
        return MemoryScope(
            user_id=row["scope_user"],
            agent_id=row["scope_agent"],
            platform=row["scope_platform"],
            chat_type=row["scope_chat_type"],
            chat_id=row["scope_chat_id"],
            extra_dimensions=json.loads(row["scope_extra_json"] or "{}"),
        )

    @classmethod
    def _row_to_record(cls, row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            memory_id=row["id"],
            kind=row["kind"],
            scope=cls._row_scope(row),
            content=row["content"],
            actor=row["actor"],
            authority=FactAuthority(row["authority"]),
            state=MemoryState(row["state"]),
            tags=json.loads(row["tags"] or "[]"),
            importance=row["importance"],
            idempotency_key=row["idempotency_key"],
            source_event_id=row["source_event_id"],
            source_message_id=row["source_message_id"],
            extractor=row["extractor"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version=row["version"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    @classmethod
    def _row_to_recall(
        cls, row: sqlite3.Row, *, similarity: float = 0.0
    ) -> RecallResult:
        record = cls._row_to_record(row)
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
            similarity=similarity,
            state=record.state,
        )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _fts_query(value: str) -> str:
    terms = re.findall(r"\w+", value, flags=re.UNICODE)
    return " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)


def _fts_similarity(rank: float) -> float:
    """Map FTS5's lower-is-better BM25 rank monotonically into ``(0, 1)``."""

    return 1.0 / (1.0 + math.exp(max(-60.0, min(60.0, rank))))


def _normalize_legacy_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return utc_now().isoformat()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()
