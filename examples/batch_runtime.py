"""Reference host-side adapters for periodic Doppel tasks.

These adapters are intentionally examples, not core defaults. They keep transient
IM events and scheduler checkpoints outside the long-term memory Store.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from doppel_memory import (
    BatchCheckpoint,
    ChatMessage,
    HistoryPage,
    MemoryIsolationError,
    MemoryScope,
)

_EVENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS im_event_log (
    scope_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    event_key TEXT NOT NULL,
    actor TEXT NOT NULL,
    message_json TEXT NOT NULL,
    PRIMARY KEY (scope_key, event_key)
);
CREATE INDEX IF NOT EXISTS idx_im_event_log_scan
ON im_event_log(scope_key, created_at, event_key);
"""

_CHECKPOINT_SCHEMA = """
CREATE TABLE IF NOT EXISTS batch_checkpoints (
    task_key TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    checkpoint_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (task_key, scope_key)
);
"""


class SQLiteEventLog:
    """Small external event log; it is not a Doppel ``MemoryStore``."""

    def __init__(self, database: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(database), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_EVENT_SCHEMA)
        self._lock = asyncio.Lock()

    async def append(self, scope: MemoryScope, message: ChatMessage) -> bool:
        """Append idempotently; source adapters must provide a stable event identity."""

        event_key = message.identity_key
        if not event_key:
            raise ValueError("external event log requires message_id or event_id")

        def _write() -> bool:
            cursor = self._conn.execute(
                """INSERT OR IGNORE INTO im_event_log
                   (scope_key, created_at, event_key, actor, message_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    scope.scope_key,
                    message.at.astimezone(UTC).isoformat(),
                    event_key,
                    message.actor,
                    message.model_dump_json(),
                ),
            )
            self._conn.commit()
            return cursor.rowcount == 1

        async with self._lock:
            return await asyncio.to_thread(_write)

    def history(self, scope: MemoryScope) -> SQLiteEventHistoryReader:
        """Expose only the read-only protocol to a batch task."""

        return SQLiteEventHistoryReader(self, scope)

    async def _read(
        self,
        scope: MemoryScope,
        *,
        cursor: str,
        limit: int,
        actors: set[str] | None,
        time_from: datetime | None,
        time_to: datetime | None,
    ) -> HistoryPage:
        if limit <= 0:
            return HistoryPage(next_cursor=cursor)
        after = _decode_cursor(cursor, scope) if cursor else None

        def _query() -> HistoryPage:
            where = ["scope_key=?"]
            params: list[Any] = [scope.scope_key]
            if after is not None:
                after_time, after_key = after
                after_iso = after_time.astimezone(UTC).isoformat()
                where.append("(created_at > ? OR (created_at = ? AND event_key > ?))")
                params.extend((after_iso, after_iso, after_key))
            if actors:
                values = sorted(actors)
                where.append(f"actor IN ({','.join('?' for _ in values)})")
                params.extend(values)
            if time_from is not None:
                where.append("created_at >= ?")
                params.append(time_from.astimezone(UTC).isoformat())
            if time_to is not None:
                where.append("created_at <= ?")
                params.append(time_to.astimezone(UTC).isoformat())
            params.append(limit + 1)
            rows = self._conn.execute(
                "SELECT * FROM im_event_log WHERE "
                + " AND ".join(where)
                + " ORDER BY created_at ASC, event_key ASC LIMIT ?",
                params,
            ).fetchall()
            has_more = len(rows) > limit
            selected = rows[:limit]
            messages = [
                ChatMessage.model_validate_json(row["message_json"]) for row in selected
            ]
            next_cursor = cursor
            if selected:
                last = selected[-1]
                next_cursor = _encode_cursor(
                    scope,
                    datetime.fromisoformat(last["created_at"]),
                    last["event_key"],
                )
            return HistoryPage(
                messages=messages,
                next_cursor=next_cursor,
                has_more=has_more,
            )

        async with self._lock:
            return await asyncio.to_thread(_query)

    async def close(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._conn.close)


class SQLiteEventHistoryReader:
    """Exact-scope read-only view over ``SQLiteEventLog``."""

    def __init__(self, event_log: SQLiteEventLog, scope: MemoryScope) -> None:
        self._event_log = event_log
        self._scope = scope

    @property
    def scope(self) -> MemoryScope:
        return self._scope

    async def read(
        self,
        *,
        cursor: str = "",
        limit: int = 500,
        actors: set[str] | None = None,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
    ) -> HistoryPage:
        return await self._event_log._read(
            self._scope,
            cursor=cursor,
            limit=limit,
            actors=actors,
            time_from=time_from,
            time_to=time_to,
        )


class SQLiteCheckpointStore:
    """Host-owned checkpoint recipe keyed by task and exact scope."""

    def __init__(self, database: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(database), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_CHECKPOINT_SCHEMA)
        self._lock = asyncio.Lock()

    async def load(self, task_key: str, scope: MemoryScope) -> BatchCheckpoint | None:
        def _query() -> BatchCheckpoint | None:
            row = self._conn.execute(
                """SELECT checkpoint_json FROM batch_checkpoints
                   WHERE task_key=? AND scope_key=?""",
                (task_key, scope.scope_key),
            ).fetchone()
            if row is None:
                return None
            return BatchCheckpoint.model_validate_json(row["checkpoint_json"])

        async with self._lock:
            return await asyncio.to_thread(_query)

    async def save(
        self,
        task_key: str,
        scope: MemoryScope,
        checkpoint: BatchCheckpoint,
    ) -> None:
        def _write() -> None:
            self._conn.execute(
                """INSERT INTO batch_checkpoints
                   (task_key, scope_key, checkpoint_json, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(task_key, scope_key) DO UPDATE SET
                     checkpoint_json=excluded.checkpoint_json,
                     updated_at=excluded.updated_at""",
                (
                    task_key,
                    scope.scope_key,
                    checkpoint.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                ),
            )
            self._conn.commit()

        async with self._lock:
            await asyncio.to_thread(_write)

    async def close(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._conn.close)


def _encode_cursor(scope: MemoryScope, created_at: datetime, event_key: str) -> str:
    payload = json.dumps(
        [scope.scope_key, created_at.astimezone(UTC).isoformat(), event_key],
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str, scope: MemoryScope) -> tuple[datetime, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload_scope, created_at, event_key = json.loads(
            base64.urlsafe_b64decode((cursor + padding).encode())
        )
        parsed = datetime.fromisoformat(str(created_at))
        if parsed.tzinfo is None or not event_key:
            raise ValueError("cursor contents are incomplete")
        if payload_scope != scope.scope_key:
            raise MemoryIsolationError("event-log cursor belongs to another scope")
        return parsed.astimezone(UTC), str(event_key)
    except MemoryIsolationError:
        raise
    except (
        binascii.Error,
        UnicodeDecodeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("invalid event-log cursor") from exc
