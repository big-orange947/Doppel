"""Host-owned arrival queue and immutable per-batch history; no core API changes."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from doppel_memory import ChatMessage, HistoryPage, HistoryWindow, MemoryScope
from examples.checked_ingest import SourceEventConflictError, _portable, ingest_checked


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _checked_rows(rows):
    """Verify the enqueue-time semantic checksum before using persisted rows.

    Keep the original (sequence, payload) batch hash format for existing journals.
    This detects accidental changes, not a writer able to replace both checksums.
    """
    checked = []
    for sequence, payload, event_key, fingerprint in rows:
        try:
            message = ChatMessage.model_validate_json(payload)
        except ValueError:
            raise ValueError("arrival source integrity mismatch") from None
        if (
            not message.identity_key
            or message.identity_key != event_key
            or digest(_portable(message)) != fingerprint
        ):
            raise ValueError("arrival source integrity mismatch")
        checked.append((sequence, payload))
    return checked


class ArrivalBatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    identity: str
    scope: MemoryScope
    payloads: tuple[str, ...]

    @property
    def messages(self):
        return [ChatMessage.model_validate_json(payload) for payload in self.payloads]

    @property
    def window(self):
        return HistoryWindow(
            start=min(m.at for m in self.messages), end=max(m.at for m in self.messages)
        )

    def history(self):
        return FrozenHistory(self)


class FrozenHistory:
    """Oldest-first source-time pagination over one frozen arrival selection."""

    def __init__(self, batch):
        self.scope = batch.scope
        self.identity = batch.identity
        self._payloads = tuple(
            m.model_dump_json()
            for m in sorted(
                (m.model_copy(deep=True) for m in batch.messages),
                key=lambda m: (m.at, m.identity_key),
            )
        )

    @property
    def messages(self):
        return [ChatMessage.model_validate_json(payload) for payload in self._payloads]

    async def read(
        self, *, cursor="", limit=500, actors=None, time_from=None, time_to=None
    ):
        if type(limit) is not int or not 1 <= limit <= 2000:
            raise ValueError("invalid snapshot page size")
        binding = digest(
            [
                self.identity,
                sorted(actors or []),
                time_from.isoformat() if time_from else None,
                time_to.isoformat() if time_to else None,
            ]
        )
        offset = 0
        if cursor:
            prefix, value = cursor.rsplit(":", 1)
            if prefix != binding or not value.isdecimal():
                raise ValueError("snapshot cursor belongs to a different selection")
            offset = int(value)
        messages = [
            m
            for m in self.messages
            if (not actors or m.actor in actors)
            and (time_from is None or m.at >= time_from)
            and (time_to is None or m.at <= time_to)
        ]
        if offset > len(messages):
            raise ValueError("snapshot cursor outside selected history")
        selected = messages[offset : offset + limit]
        return HistoryPage(
            messages=[m.model_copy(deep=True) for m in selected],
            next_cursor=f"{binding}:{offset + len(selected)}",
            has_more=offset + len(selected) < len(messages),
        )


class ArrivalInbox:
    """Durable append/reserve/ack. Multiple producers, exclusively owned consumer.

    Reservations persist before work. Reopened consumers receive the same pending
    batch even if more messages arrive; ack occurs only after complete workflow.
    """

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS arrival_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS arrival_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, scope_key TEXT NOT NULL,
                    event_key TEXT NOT NULL, payload TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    batch_id TEXT, UNIQUE(scope_key,event_key));
                CREATE TABLE IF NOT EXISTS arrival_batches (
                    id TEXT PRIMARY KEY, scope_key TEXT NOT NULL, complete INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS arrival_pending_events
                    ON arrival_events(scope_key,batch_id,sequence);
                CREATE INDEX IF NOT EXISTS arrival_pending_batches
                    ON arrival_batches(scope_key,complete);
            """)
            conn.execute(
                "INSERT OR IGNORE INTO arrival_meta VALUES('identity',?)",
                (uuid4().hex,),
            )
            self.identity = conn.execute(
                "SELECT value FROM arrival_meta WHERE key='identity'"
            ).fetchone()[0]

    async def append(self, scope: MemoryScope, message: ChatMessage):
        bound = ChatMessage.model_validate_json(message.model_dump_json())
        if not bound.identity_key:
            raise ValueError("arrival event requires stable identity")
        fingerprint = digest(_portable(bound))

        def write():
            with sqlite3.connect(self.path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                previous = conn.execute(
                    "SELECT sequence,payload,event_key,fingerprint FROM arrival_events WHERE scope_key=? AND event_key=?",
                    (scope.scope_key, bound.identity_key),
                ).fetchone()
                if previous:
                    _checked_rows([previous])
                    if previous[3] != fingerprint:
                        raise SourceEventConflictError(
                            "arrival identity reused with different portable content"
                        )
                    return previous[0]
                cursor = conn.execute(
                    "INSERT INTO arrival_events(scope_key,event_key,payload,fingerprint) VALUES(?,?,?,?)",
                    (
                        scope.scope_key,
                        bound.identity_key,
                        bound.model_dump_json(),
                        fingerprint,
                    ),
                )
                return cursor.lastrowid

        return await asyncio.to_thread(write)

    async def reserve(self, scope: MemoryScope, *, max_messages=50):
        if type(max_messages) is not int or not 1 <= max_messages <= 2000:
            raise ValueError("invalid arrival batch bound")

        def reserve():
            with sqlite3.connect(self.path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                pending = conn.execute(
                    "SELECT id FROM arrival_batches WHERE scope_key=? AND complete=0 ORDER BY rowid LIMIT 1",
                    (scope.scope_key,),
                ).fetchone()
                if pending:
                    batch_id = pending[0]
                    rows = _checked_rows(
                        conn.execute(
                            "SELECT sequence,payload,event_key,fingerprint FROM arrival_events WHERE batch_id=? AND scope_key=? ORDER BY sequence",
                            (batch_id, scope.scope_key),
                        ).fetchall()
                    )
                else:
                    rows = _checked_rows(
                        conn.execute(
                            "SELECT sequence,payload,event_key,fingerprint FROM arrival_events WHERE scope_key=? AND batch_id IS NULL ORDER BY sequence LIMIT ?",
                            (scope.scope_key, max_messages),
                        ).fetchall()
                    )
                    if not rows:
                        return None
                    batch_id = "arrival_" + digest(
                        [self.identity, scope.scope_key, rows]
                    )
                    conn.execute(
                        "INSERT INTO arrival_batches(id,scope_key) VALUES(?,?)",
                        (batch_id, scope.scope_key),
                    )
                    conn.executemany(
                        "UPDATE arrival_events SET batch_id=? WHERE sequence=?",
                        [(batch_id, row[0]) for row in rows],
                    )
                if not rows or batch_id != "arrival_" + digest(
                    [self.identity, scope.scope_key, rows]
                ):
                    raise ValueError("arrival snapshot identity mismatch")
                return ArrivalBatch(
                    identity=batch_id,
                    scope=scope,
                    payloads=tuple(row[1] for row in rows),
                )

        return await asyncio.to_thread(reserve)

    async def acknowledge(self, batch: ArrivalBatch):
        def ack():
            with sqlite3.connect(self.path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                rows = _checked_rows(
                    conn.execute(
                        "SELECT sequence,payload,event_key,fingerprint FROM arrival_events WHERE batch_id=? AND scope_key=? ORDER BY sequence",
                        (batch.identity, batch.scope.scope_key),
                    ).fetchall()
                )
                if (
                    not rows
                    or batch.identity
                    != "arrival_" + digest([self.identity, batch.scope.scope_key, rows])
                    or tuple(row[1] for row in rows) != batch.payloads
                ):
                    raise ValueError("ack does not match arrival snapshot")
                conn.execute(
                    "UPDATE arrival_batches SET complete=1 WHERE id=? AND scope_key=?",
                    (batch.identity, batch.scope.scope_key),
                )

        await asyncio.to_thread(ack)


async def drain_once(inbox, scope, store, workflow_factory, *, max_steps=100):
    """Factory must create an exact batch-specific journal with bound history.

    Batch window is source time, not a new governance clock. Governance is run
    separately at a trusted host horizon, never at an old late-arrival timestamp.
    """
    if type(max_steps) is not int or max_steps < 1:
        raise ValueError("positive step bound required")
    batch = await inbox.reserve(scope)
    if batch is None:
        return {"complete": True, "empty": True}
    workflow = workflow_factory(batch)
    if (
        workflow.store is not store
        or workflow.scope != scope
        or workflow.history_identity != batch.identity
        or workflow.governance_runner is not None
    ):
        raise ValueError(
            "arrival workflow must bind its snapshot, Store, scope and separate governance"
        )
    expected_history = batch.history()
    if (
        type(workflow.history) is not FrozenHistory
        or workflow.history.scope != scope
        or workflow.history.identity != batch.identity
        or workflow.history._payloads != expected_history._payloads
    ):
        raise ValueError("arrival workflow must use the reserved frozen snapshot")
    for message in batch.messages:
        await ingest_checked(store, scope, message)
    for _ in range(max_steps):
        report = await workflow.step(batch.window)
        if not report["ok"]:
            return report
        if report["complete"]:
            await inbox.acknowledge(batch)
            return {
                **report,
                "batch_id": batch.identity,
                "messages": len(batch.messages),
                "empty": False,
            }
    return {"complete": False, "batch_id": batch.identity, "reason": "step_bound"}
