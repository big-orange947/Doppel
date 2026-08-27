"""Async PostgreSQL Store with exact-scope isolation and lazy optional imports."""

from __future__ import annotations

import asyncio
import importlib
import json
import re
from collections.abc import Mapping
from datetime import UTC
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

SCHEMA_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class PostgreSQLStore(MemoryStore):
    """Production-oriented PostgreSQL implementation of the stable Store contract.

    The driver is imported only when the first operation opens the pool, so importing
    :mod:`doppel_memory` does not require the ``postgres`` optional dependency.
    Schema creation is opt-in because many production roles intentionally cannot create
    schemas. Tables and indexes inside an existing schema are migrated automatically.
    """

    def __init__(
        self,
        dsn: str,
        *,
        schema: str = "public",
        create_schema: bool = False,
        min_pool_size: int = 1,
        max_pool_size: int = 10,
        command_timeout: float = 30.0,
    ) -> None:
        if not str(dsn or "").strip():
            raise ValueError("PostgreSQL DSN is required")
        if not _IDENTIFIER.fullmatch(schema):
            raise ValueError(
                "schema must be an unquoted PostgreSQL identifier containing only "
                "letters, digits, and underscores"
            )
        if min_pool_size < 0:
            raise ValueError("min_pool_size must be >= 0")
        if max_pool_size <= 0 or max_pool_size < min_pool_size:
            raise ValueError("max_pool_size must be positive and >= min_pool_size")
        if command_timeout <= 0:
            raise ValueError("command_timeout must be positive")

        self._dsn = dsn.strip()
        self._schema = schema
        self._schema_sql = f'"{schema}"'
        self._records_sql = f'{self._schema_sql}."doppel_memory_records"'
        self._meta_sql = f'{self._schema_sql}."doppel_memory_meta"'
        self._create_schema = create_schema
        self._min_pool_size = min_pool_size
        self._max_pool_size = max_pool_size
        self._command_timeout = command_timeout
        self._pool: Any | None = None
        self._init_lock = asyncio.Lock()
        self._capabilities = StoreCapabilities(
            substring_search=True,
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
    def schema(self) -> str:
        return self._schema

    async def _ensure_pool(self) -> Any:
        if self._pool is None:
            async with self._init_lock:
                if self._pool is None:
                    driver = _load_asyncpg()
                    pool = await driver.create_pool(
                        dsn=self._dsn,
                        min_size=self._min_pool_size,
                        max_size=self._max_pool_size,
                        command_timeout=self._command_timeout,
                    )
                    try:
                        async with pool.acquire() as connection:
                            await self._migrate(connection)
                    except BaseException:
                        await pool.close()
                        raise
                    self._pool = pool
        return self._pool

    async def _migrate(self, connection: Any) -> None:
        async with connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                f"doppel-memory-schema:{self._schema}",
            )
            if self._create_schema:
                await connection.execute(
                    f"CREATE SCHEMA IF NOT EXISTS {self._schema_sql}"
                )
            await connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._meta_sql} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            await connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._records_sql} (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    scope_user TEXT NOT NULL,
                    scope_agent TEXT NOT NULL,
                    scope_platform TEXT NOT NULL DEFAULT '',
                    scope_chat_type TEXT NOT NULL DEFAULT '',
                    scope_chat_id TEXT NOT NULL DEFAULT '',
                    scope_extra JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    scope_key TEXT NOT NULL,
                    content TEXT NOT NULL,
                    actor TEXT NOT NULL DEFAULT '',
                    authority TEXT NOT NULL DEFAULT 'derived_summary',
                    state TEXT NOT NULL DEFAULT 'confirmed',
                    tags TEXT[] NOT NULL DEFAULT ARRAY[]::text[],
                    importance DOUBLE PRECISION NOT NULL DEFAULT 0.5,
                    idempotency_key TEXT NOT NULL DEFAULT '',
                    source_event_id TEXT NOT NULL DEFAULT '',
                    source_message_id TEXT NOT NULL DEFAULT '',
                    extractor TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb
                )
                """
            )
            await connection.execute(
                f"CREATE INDEX IF NOT EXISTS doppel_memory_idx_scope_key "
                f"ON {self._records_sql}(scope_key)"
            )
            await connection.execute(
                f"CREATE INDEX IF NOT EXISTS doppel_memory_idx_created "
                f"ON {self._records_sql}(created_at, id)"
            )
            await connection.execute(
                f"CREATE INDEX IF NOT EXISTS doppel_memory_idx_tags "
                f"ON {self._records_sql} USING GIN(tags)"
            )
            await connection.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS doppel_memory_uq_scope_idempotency "
                f"ON {self._records_sql}(scope_key, idempotency_key) "
                "WHERE idempotency_key <> ''"
            )
            await connection.execute(
                f"""
                INSERT INTO {self._meta_sql}(key, value)
                VALUES('schema_version', $1)
                ON CONFLICT (key) DO NOTHING
                """,
                str(SCHEMA_VERSION),
            )
            stored_version = await connection.fetchval(
                f"SELECT value FROM {self._meta_sql} WHERE key='schema_version'"
            )
            if int(stored_version) != SCHEMA_VERSION:
                raise RuntimeError(
                    "unsupported PostgreSQL schema version: "
                    f"database={stored_version}, library={SCHEMA_VERSION}"
                )

    async def put(
        self, record: MemoryRecord, *, idempotency_key: str | None = None
    ) -> WriteResult:
        pool = await self._ensure_pool()
        key = str(idempotency_key or record.idempotency_key or "").strip()
        memory_id = record.memory_id or f"mem-{uuid4().hex}"
        stored = record.model_copy(
            update={"memory_id": memory_id, "idempotency_key": key}, deep=True
        )
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                INSERT INTO {self._records_sql}
                    (id, kind, scope_user, scope_agent, scope_platform,
                     scope_chat_type, scope_chat_id, scope_extra, scope_key,
                     content, actor, authority, state, tags, importance,
                     idempotency_key, source_event_id, source_message_id,
                     extractor, created_at, updated_at, version, metadata)
                VALUES
                    ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9,
                     $10, $11, $12, $13, $14::text[], $15,
                     $16, $17, $18, $19, $20, $21, $22, $23::jsonb)
                ON CONFLICT DO NOTHING
                RETURNING *
                """,
                *self._record_args(stored),
            )
            if row is not None:
                return WriteResult(
                    status=WriteStatus.CREATED,
                    record=self._row_to_record(row),
                )
            if key:
                duplicate = await connection.fetchrow(
                    f"SELECT * FROM {self._records_sql} "
                    "WHERE scope_key=$1 AND idempotency_key=$2 LIMIT 1",
                    stored.scope.scope_key,
                    key,
                )
                if duplicate is not None:
                    return WriteResult(
                        status=WriteStatus.DUPLICATE,
                        record=self._row_to_record(duplicate),
                    )
            return WriteResult(
                status=WriteStatus.FAILED,
                error_code="integrity_error",
                message=f"memory ID already exists: {memory_id}",
            )

    @staticmethod
    def _record_args(record: MemoryRecord) -> tuple[Any, ...]:
        return (
            record.memory_id,
            record.kind,
            record.scope.user_id,
            record.scope.agent_id,
            record.scope.platform,
            record.scope.chat_type,
            record.scope.chat_id,
            json.dumps(
                dict(record.scope.extra_dimensions),
                ensure_ascii=False,
                sort_keys=True,
            ),
            record.scope.scope_key,
            record.content,
            record.actor,
            record.authority.value,
            record.state.value,
            list(record.tags),
            record.importance,
            record.idempotency_key,
            record.source_event_id,
            record.source_message_id,
            record.extractor,
            record.created_at,
            record.updated_at,
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
        pool = await self._ensure_pool()
        scope_keys = list(dict.fromkeys(scope.scope_key for scope in scopes))
        where = ["scope_key = ANY($1::text[])"]
        params: list[Any] = [scope_keys]
        query_text = str(query or "").strip()
        if query_text:
            params.append(query_text)
            where.append(
                f"(strpos(content, ${len(params)}) > 0 OR "
                f"strpos(metadata::text, ${len(params)}) > 0)"
            )
        self._append_filters(where, params, filters or MemoryFilter())
        params.append(limit)
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                f"SELECT * FROM {self._records_sql} WHERE "
                + " AND ".join(where)
                + f" ORDER BY created_at DESC, id ASC LIMIT ${len(params)}",
                *params,
            )
        return [self._row_to_recall(row) for row in rows]

    async def scan(
        self,
        scope: MemoryScope,
        *,
        filters: MemoryFilter | None = None,
        cursor: str = "",
        limit: int = 100,
    ) -> MemoryPage:
        if limit <= 0:
            return MemoryPage()
        pool = await self._ensure_pool()
        where = ["scope_key=$1"]
        params: list[Any] = [scope.scope_key]
        if cursor:
            after_time, after_id = decode_cursor(cursor)
            params.extend((after_time.astimezone(UTC), after_id))
            where.append(
                f"(created_at > ${len(params) - 1} OR "
                f"(created_at = ${len(params) - 1} AND id > ${len(params)}))"
            )
        self._append_filters(where, params, filters or MemoryFilter())
        params.append(limit + 1)
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                f"SELECT * FROM {self._records_sql} WHERE "
                + " AND ".join(where)
                + f" ORDER BY created_at ASC, id ASC LIMIT ${len(params)}",
                *params,
            )
        has_more = len(rows) > limit
        records = [self._row_to_record(row) for row in rows[:limit]]
        next_cursor = cursor
        if records:
            last = records[-1]
            next_cursor = encode_cursor(last.created_at, last.memory_id)
        return MemoryPage(
            records=records,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    @staticmethod
    def _append_filters(
        where: list[str],
        params: list[Any],
        filters: MemoryFilter,
        *,
        prefix: str = "",
    ) -> None:
        def append_any(
            column: str, values: list[str], *, exclude: bool = False
        ) -> None:
            params.append(values)
            operator = "<> ALL" if exclude else "= ANY"
            where.append(f"{prefix}{column} {operator}(${len(params)}::text[])")

        if filters.states is not None:
            append_any("state", [state.value for state in filters.states])
        elif not filters.include_inactive:
            append_any("state", [state.value for state in ACTIVE_MEMORY_STATES])
        if filters.kinds:
            append_any("kind", list(filters.kinds))
        if filters.actors:
            append_any("actor", list(filters.actors))
        if filters.exclude_actors:
            append_any("actor", list(filters.exclude_actors), exclude=True)
        if filters.authorities:
            append_any(
                "authority", [authority.value for authority in filters.authorities]
            )
        if filters.exclude_authorities:
            append_any(
                "authority",
                [authority.value for authority in filters.exclude_authorities],
                exclude=True,
            )
        if filters.importance_min is not None:
            params.append(filters.importance_min)
            where.append(f"{prefix}importance >= ${len(params)}")
        if filters.time_from is not None:
            params.append(filters.time_from)
            where.append(f"{prefix}created_at >= ${len(params)}")
        if filters.time_to is not None:
            params.append(filters.time_to)
            where.append(f"{prefix}created_at <= ${len(params)}")
        if filters.tags:
            params.append(list(filters.tags))
            where.append(f"{prefix}tags @> ${len(params)}::text[]")

    async def list_recent_owner_messages(
        self, scope: MemoryScope, *, limit: int = 5
    ) -> list[ChatMessage]:
        if limit <= 0:
            return []
        pool = await self._ensure_pool()
        active = [state.value for state in ACTIVE_MEMORY_STATES]
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT * FROM {self._records_sql}
                WHERE scope_key=$1 AND kind='event' AND actor=$2
                  AND state = ANY($3::text[])
                ORDER BY created_at DESC, id DESC LIMIT $4
                """,
                scope.scope_key,
                Actor.OWNER,
                active,
                limit,
            )
        messages: list[ChatMessage] = []
        for row in reversed(rows):
            metadata = _json_object(row["metadata"])
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

    async def get(self, scope: MemoryScope, memory_id: str) -> MemoryRecord | None:
        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                f"SELECT * FROM {self._records_sql} WHERE id=$1 AND scope_key=$2",
                memory_id,
                scope.scope_key,
            )
        return self._row_to_record(row) if row is not None else None

    async def transition(
        self,
        scope: MemoryScope,
        memory_id: str,
        to_state: MemoryState,
        *,
        expected_state: MemoryState | None = None,
    ) -> MemoryRecord:
        pool = await self._ensure_pool()
        params: list[Any] = [
            to_state.value,
            utc_now(),
            memory_id,
            scope.scope_key,
        ]
        expected_clause = ""
        if expected_state is not None:
            params.append(expected_state.value)
            expected_clause = f" AND state=${len(params)}"
        async with pool.acquire() as connection, connection.transaction():
            row = await connection.fetchrow(
                f"""
                    UPDATE {self._records_sql}
                    SET state=$1, updated_at=$2, version=version+1
                    WHERE id=$3 AND scope_key=$4{expected_clause}
                    RETURNING *
                """,
                *params,
            )
            if row is not None:
                return self._row_to_record(row)
            current = await connection.fetchrow(
                f"SELECT state FROM {self._records_sql} WHERE id=$1 AND scope_key=$2",
                memory_id,
                scope.scope_key,
            )
            if current is None:
                raise KeyError(memory_id)
            expected = expected_state.value if expected_state is not None else "*"
            raise MemoryStateConflictError(
                f"expected {expected}, found {current['state']}"
            )

    async def forget(
        self, scope: MemoryScope, memory_id: str, *, hard: bool = False
    ) -> bool:
        if not hard:
            try:
                await self.transition(scope, memory_id, MemoryState.EXPIRED)
                return True
            except KeyError:
                return False
        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            status = await connection.execute(
                f"DELETE FROM {self._records_sql} WHERE id=$1 AND scope_key=$2",
                memory_id,
                scope.scope_key,
            )
        return status == "DELETE 1"

    async def health(self) -> dict[str, Any]:
        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            count = await connection.fetchval(
                f"SELECT COUNT(*) FROM {self._records_sql}"
            )
            version = await connection.fetchval(
                f"SELECT value FROM {self._meta_sql} WHERE key='schema_version'"
            )
            server_version = await connection.fetchval(
                "SELECT current_setting('server_version')"
            )
        return {
            "enabled": True,
            "ok": True,
            "records": int(count),
            "backend": "postgresql",
            "schema": self._schema,
            "schema_version": int(version),
            "server_version": str(server_version),
            "full_text_search": False,
        }

    async def close(self) -> None:
        async with self._init_lock:
            pool = self._pool
            self._pool = None
            if pool is not None:
                await pool.close()

    @staticmethod
    def _row_scope(row: Mapping[str, Any]) -> MemoryScope:
        return MemoryScope(
            user_id=row["scope_user"],
            agent_id=row["scope_agent"],
            platform=row["scope_platform"],
            chat_type=row["scope_chat_type"],
            chat_id=row["scope_chat_id"],
            extra_dimensions=_json_object(row["scope_extra"]),
        )

    @classmethod
    def _row_to_record(cls, row: Mapping[str, Any]) -> MemoryRecord:
        return MemoryRecord(
            memory_id=row["id"],
            kind=row["kind"],
            scope=cls._row_scope(row),
            content=row["content"],
            actor=row["actor"],
            authority=FactAuthority(row["authority"]),
            state=MemoryState(row["state"]),
            tags=list(row["tags"] or []),
            importance=row["importance"],
            idempotency_key=row["idempotency_key"],
            source_event_id=row["source_event_id"],
            source_message_id=row["source_message_id"],
            extractor=row["extractor"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version=row["version"],
            metadata=_json_object(row["metadata"]),
        )

    @classmethod
    def _row_to_recall(cls, row: Mapping[str, Any]) -> RecallResult:
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
            similarity=0.0,
            state=record.state,
        )


def _load_asyncpg() -> Any:
    try:
        return importlib.import_module("asyncpg")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PostgreSQL support requires the optional dependency; install "
            "doppel-memory[postgres]"
        ) from exc


def _json_object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        decoded = json.loads(value or "{}")
    else:
        decoded = dict(value)
    if not isinstance(decoded, dict):
        raise TypeError("expected a JSON object from PostgreSQL")
    return decoded
