"""Runnable repository-only AML transport and zero-LLM lexical smoke backend.

Not the high-config retrieval profile or an official/compliant evaluation claim.
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from doppel_memory import ChatMessage, SQLiteStore
from doppel_memory.lexical import BM25RetrievalStrategy
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.contract import (
    AddRequest,
    SearchRequest,
    TextualBoundary,
    WriteConflict,
    WriteNotReady,
    WriteReceipt,
    event_ids,
    payload_fingerprint,
    write_key,
)


class SQLiteRawBackend:
    """Raw-only durable writes with fail-closed partial-ingest visibility.

    The SQLite journal coordinates cooperating local instances, not unrelated
    writers/distributed hosts. No model/index calls or destructive migrations.
    """

    def __init__(self, directory: Path, *, namespace: str, role_actors: dict[str, str]):
        if not namespace.strip() or role_actors != {
            "user": "owner",
            "assistant": "agent",
        }:
            raise ValueError(
                "explicit owner/historical-assistant role binding required"
            )
        directory.mkdir(parents=True, exist_ok=True)
        self.store = SQLiteStore(str(directory / "raw.sqlite3"))
        self.journal = sqlite3.connect(
            directory / "service-journal.sqlite3", isolation_level=None, timeout=0
        )
        self.journal.execute("PRAGMA journal_mode=WAL")
        self.journal.execute("PRAGMA synchronous=FULL")
        self.journal.executescript("""
            CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS writes (key TEXT PRIMARY KEY, payload TEXT NOT NULL, scope TEXT NOT NULL, observed TEXT NOT NULL, done INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS sources (scope TEXT NOT NULL, event TEXT NOT NULL, memory TEXT NOT NULL, PRIMARY KEY(scope,event));
        """)
        profile = json.dumps(
            {
                "version": 1,
                "namespace": namespace,
                "roles": role_actors,
                "strategy": "bm25-raw-smoke-v1",
            },
            sort_keys=True,
        )
        self.journal.execute("INSERT OR IGNORE INTO profile VALUES (1,?)", (profile,))
        if (
            self.journal.execute("SELECT value FROM profile WHERE id=1").fetchone()[0]
            != profile
        ):
            self.journal.close()
            raise ValueError(
                "existing service profile differs; use a separate directory"
            )
        self.roles = dict(role_actors)
        self.lock = asyncio.Lock()
        self.retriever = AttributedContextRetriever(
            self.store,
            strategy=BM25RetrievalStrategy(),
            resolve_event=self.resolve_event,
        )

    async def resolve_event(self, scope, identity):
        row = self.journal.execute(
            "SELECT memory FROM sources WHERE scope=? AND event=?",
            (scope.scope_key, identity),
        ).fetchone()
        if row is None:
            return None
        record = await self.store.get(scope, row[0])
        if record is None or record.source_event_id != identity:
            raise WriteNotReady("source mapping no longer resolves")
        return record

    async def add(self, scope, request):
        key, payload = write_key(scope, request), payload_fingerprint(request)
        # Reject malformed time before creating a durable pending marker.
        for message in request.messages:
            if message.timestamp is not None:
                _ = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
                    milliseconds=message.timestamp
                )
        async with self.lock:
            try:
                self.journal.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError:
                raise WriteNotReady("service writer busy") from None
            try:
                row = self.journal.execute(
                    "SELECT payload,scope,observed,done FROM writes WHERE key=?", (key,)
                ).fetchone()
                if row and row[:2] != (payload, scope.scope_key):
                    raise WriteConflict("request identity reused with changed payload")
                if self.journal.execute(
                    "SELECT 1 FROM writes WHERE scope=? AND done=0 AND key<>? LIMIT 1",
                    (scope.scope_key, key),
                ).fetchone():
                    raise WriteNotReady("repair unfinished request before another add")
                observed = row[2] if row else datetime.now(UTC).isoformat()
                self.journal.execute(
                    "INSERT OR IGNORE INTO writes VALUES (?,?,?,?,0)",
                    (key, payload, scope.scope_key, observed),
                )
                self.journal.execute(
                    "COMMIT"
                )  # durable pending marker before Store writes
                self.journal.execute("BEGIN IMMEDIATE")
                for index, (identity, message) in enumerate(
                    zip(event_ids(scope, request), request.messages, strict=True)
                ):
                    at = (
                        datetime.fromisoformat(observed)
                        if message.timestamp is None
                        else datetime(1970, 1, 1, tzinfo=UTC)
                        + timedelta(milliseconds=message.timestamp)
                    )
                    raw = {
                        "source_text": message.content,
                        "transport_role": message.role,
                        "session_id": request.session_id,
                        "turn_index": index,
                    }
                    event = ChatMessage(
                        event_id=identity,
                        text=message.content,
                        actor=self.roles[message.role],
                        at=at,
                        sender_id=scope.user_id
                        if message.role == "user"
                        else scope.agent_id,
                        raw=raw,
                    )
                    if row and row[3]:
                        stored = await self.resolve_event(scope, identity)
                    else:
                        result = await self.store.write_event(scope, event)
                        stored = (
                            await self.store.get(scope, result.memory_id)
                            if result.memory_id
                            else None
                        )
                    if (
                        stored is None
                        or stored.scope.scope_key != scope.scope_key
                        or stored.kind != "event"
                        or stored.extractor != "ingestor"
                        or stored.state != "confirmed"
                        or stored.authority != event.fact_authority
                        or stored.source_event_id != identity
                        or stored.content != event.text
                        or stored.created_at != at
                        or stored.actor != event.actor
                        or stored.metadata.get("raw") != raw
                    ):
                        raise WriteNotReady("source persistence validation failed")
                    self.journal.execute(
                        "INSERT OR REPLACE INTO sources VALUES (?,?,?)",
                        (scope.scope_key, identity, stored.memory_id),
                    )
                self.journal.execute("UPDATE writes SET done=1 WHERE key=?", (key,))
                self.journal.execute("COMMIT")
            except BaseException:
                if self.journal.in_transaction:
                    self.journal.execute("ROLLBACK")
                raise
        return WriteReceipt(
            write_key=key,
            payload_fingerprint=payload,
            scope_key=scope.scope_key,
            durable=True,
            searchable=True,
        )

    async def search(self, scope, request):
        async with self.lock:
            if self.journal.execute(
                "SELECT 1 FROM writes WHERE scope=? AND done=0 LIMIT 1",
                (scope.scope_key,),
            ).fetchone():
                raise WriteNotReady("scope has unfinished ingestion")
            return await self.retriever.search_evidence(
                scope, request.query, limit=request.top_k
            )

    async def close(self):
        await self.store.close()
        self.journal.close()


class TextualASGI:
    """Bounded bearer-authenticated transport; backend is explicitly injected."""

    def __init__(
        self,
        boundary: TextualBoundary,
        *,
        bearer_token: str,
        max_body_bytes: int = 2_000_000,
        max_concurrency: int = 8,
        timeout_seconds: float = 30,
    ):
        if (
            not bearer_token.strip()
            or max_body_bytes < 1
            or max_concurrency < 1
            or timeout_seconds <= 0
        ):
            raise ValueError("token and positive service bounds required")
        self.boundary, self.token = boundary, bearer_token
        self.max_body_bytes, self.max_concurrency = max_body_bytes, max_concurrency
        self.timeout_seconds, self.active = timeout_seconds, 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            if scope["type"] == "lifespan":
                while True:
                    event = await receive()
                    await send({"type": event["type"] + ".complete"})
                    if event["type"] == "lifespan.shutdown":
                        return
            return

        async def respond(status, body):
            data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", b"application/json; charset=utf-8"),
                        (b"cache-control", b"no-store"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": data})

        authorization = [
            v for k, v in scope.get("headers", []) if k.lower() == b"authorization"
        ]
        expected = ("Bearer " + self.token).encode()
        if len(authorization) != 1 or not hmac.compare_digest(
            authorization[0], expected
        ):
            return await respond(401, {"error": "unauthorized"})
        if scope.get("method") != "POST" or scope.get("path") not in {
            "/add",
            "/search",
        }:
            return await respond(404, {"error": "not_found"})
        if self.active >= self.max_concurrency:
            return await respond(503, {"error": "busy"})
        self.active += 1
        try:

            async def dispatch():
                body = bytearray()
                while True:
                    event = await receive()
                    if event["type"] == "http.disconnect":
                        raise ConnectionError()
                    body.extend(event.get("body", b""))
                    if len(body) > self.max_body_bytes:
                        return await respond(413, {"error": "body_too_large"})
                    if not event.get("more_body", False):
                        break
                try:
                    payload = json.loads(body)
                    if scope["path"] == "/add":
                        request = AddRequest.model_validate(payload)
                        if len(request.messages) > 1000:
                            return await respond(413, {"error": "too_many_messages"})
                        result = await self.boundary.add(request)
                    else:
                        request = SearchRequest.model_validate(payload)
                        if request.top_k > 1000:
                            return await respond(422, {"error": "invalid_request"})
                        result = await self.boundary.search(request)
                except (
                    ValidationError,
                    json.JSONDecodeError,
                    UnicodeDecodeError,
                    OverflowError,
                ):
                    return await respond(422, {"error": "invalid_request"})
                return await respond(
                    200, result.model_dump(mode="json", exclude_none=True)
                )

            await asyncio.wait_for(dispatch(), self.timeout_seconds)
        except WriteConflict:
            await respond(409, {"error": "write_conflict"})
        except (WriteNotReady, TimeoutError, sqlite3.OperationalError):
            await respond(503, {"error": "not_ready"})
        except ConnectionError:
            pass
        except Exception:  # noqa: BLE001 - never expose source/credential exceptions
            await respond(500, {"error": "backend_failure"})
        finally:
            self.active -= 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--bind-owner-roles", action="store_true", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    token = os.environ.get("DOPPEL_AML_BEARER_TOKEN", "")
    if not token.strip():
        parser.error("DOPPEL_AML_BEARER_TOKEN must be set")
    import uvicorn  # optional server extra; no model/provider keys read

    backend = SQLiteRawBackend(
        args.directory,
        namespace=args.namespace,
        role_actors={"user": "owner", "assistant": "agent"},
    )
    app = TextualASGI(
        TextualBoundary(backend, namespace=args.namespace), bearer_token=token
    )
    try:
        uvicorn.run(
            app, host=args.host, port=args.port, access_log=False, log_level="warning"
        )
    finally:
        asyncio.run(backend.close())


if __name__ == "__main__":
    main()
