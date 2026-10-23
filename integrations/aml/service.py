"""Runnable repository-only AML transport with explicit raw retrieval profiles.

Not the high-config retrieval profile or an official/compliant evaluation claim.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import math
import os
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from doppel_memory import ChatMessage, SQLiteStore
from doppel_memory.lexical import BM25RetrievalStrategy
from doppel_memory.models import MemoryRecord
from doppel_memory.store import MemoryStore
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.contract import (
    AddRequest,
    SearchRequest,
    TextualBoundary,
    WriteConflict,
    WriteNotReady,
    WriteReceipt,
    event_ids,
    memory_scope,
    payload_fingerprint,
    write_key,
)
from integrations.aml.retrieval import LOCAL_RERANK_POLICIES, RawRetrievalProfile


class SQLiteRawBackend:
    """Raw-only durable writes with fail-closed partial-ingest visibility.

    A SQLite journal coordinates cooperating local instances, not distributed
    hosts. Default Store/retrieval is SQLite/BM25; custom profiles are explicit.
    """

    def __init__(
        self,
        directory: Path,
        *,
        namespace: str,
        role_actors: dict[str, str],
        store: MemoryStore | None = None,
        retrieval: RawRetrievalProfile | None = None,
    ):
        if not namespace.strip() or role_actors != {
            "user": "owner",
            "assistant": "agent",
        }:
            raise ValueError(
                "explicit owner/historical-assistant role binding required"
            )
        if store is not None and retrieval is None:
            raise ValueError("a custom Store requires an explicit retrieval profile")
        directory.mkdir(parents=True, exist_ok=True)
        self.store = (
            store if store is not None else SQLiteStore(str(directory / "raw.sqlite3"))
        )
        self.retrieval = retrieval
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
                "strategy": retrieval.identity if retrieval else "bm25-raw-smoke-v1",
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
        self.profile_id = hashlib.sha256(profile.encode()).hexdigest()
        self._probe_scope = memory_scope(namespace, "__service_readiness__")
        self._closed = False
        self.lock = asyncio.Lock()
        self.retriever = AttributedContextRetriever(
            self.store,
            strategy=retrieval.strategy if retrieval else BM25RetrievalStrategy(),
            resolve_event=self.resolve_event,
            reranker=retrieval.reranker if retrieval else None,
            candidate_limit=retrieval.candidate_limit if retrieval else None,
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
                    "SELECT 1 FROM writes WHERE scope=? AND done<>1 AND key<>? LIMIT 1",
                    (scope.scope_key, key),
                ).fetchone():
                    raise WriteNotReady("repair unfinished request before another add")
                observed = row[2] if row else datetime.now(UTC).isoformat()
                self.journal.execute(
                    "INSERT OR IGNORE INTO writes VALUES (?,?,?,?,0)",
                    (key, payload, scope.scope_key, observed),
                )
                if self.retrieval is not None and row and row[3]:
                    # -1 preserves source completion across a failed index repair;
                    # retries must validate, never rewrite/resurrect, those sources.
                    self.journal.execute(
                        "UPDATE writes SET done=-1 WHERE key=?", (key,)
                    )
                self.journal.execute(
                    "COMMIT"
                )  # durable pending marker before Store writes
                self.journal.execute("BEGIN IMMEDIATE")
                records: list[MemoryRecord] = []
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
                    records.append(stored)
                # The durable pending marker remains visible if indexing fails.
                # Never acknowledge a hybrid write on lexical readiness alone.
                if self.retrieval is not None:
                    await self.retrieval.prepare_records(records)
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
                "SELECT 1 FROM writes WHERE scope=? AND done<>1 LIMIT 1",
                (scope.scope_key,),
            ).fetchone():
                raise WriteNotReady("scope has unfinished ingestion")
            return await self.retriever.search_evidence(
                scope, request.query, limit=request.top_k
            )

    async def close(self):
        self._closed = True
        try:
            await self.store.close()
        finally:
            self.journal.close()

    async def ready(self):
        """Dependency connectivity/profile probe, not a QA or coverage certificate."""
        if self._closed:
            raise WriteNotReady("service backend is closed")
        async with self.lock:
            self.journal.execute("SELECT 1").fetchone()
            await self.store.get(self._probe_scope, "__service_readiness__")
            if self.retrieval is not None:
                if self.retrieval.probe is None:
                    raise WriteNotReady("custom retrieval has no readiness probe")
                await self.retrieval.probe()


def validate_service_bounds(
    bearer_token: str,
    *,
    max_body_bytes: int = 2_000_000,
    max_concurrency: int = 8,
    timeout_seconds: float = 30,
    max_messages: int = 1000,
    max_results: int = 1000,
) -> None:
    if (
        not bearer_token
        or any(not 33 <= ord(c) <= 126 for c in bearer_token)
        or any(
            type(v) is not int or v < 1
            for v in (
                max_body_bytes,
                max_concurrency,
                max_messages,
                max_results,
            )
        )
        or max_messages > 1000
        or max_results > 1000
        or type(timeout_seconds) not in {int, float}
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError(
            "visible ASCII token and positive finite service bounds required"
        )


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
        max_messages: int = 1000,
        max_results: int = 1000,
        readiness_probe: Callable[[], Awaitable[None]] | None = None,
        profile_id: str = "",
    ):
        validate_service_bounds(
            bearer_token,
            max_body_bytes=max_body_bytes,
            max_concurrency=max_concurrency,
            timeout_seconds=timeout_seconds,
            max_messages=max_messages,
            max_results=max_results,
        )
        self.boundary, self.token = boundary, bearer_token
        self.max_body_bytes, self.max_concurrency = max_body_bytes, max_concurrency
        self.timeout_seconds, self.active = timeout_seconds, 0
        self.max_messages, self.max_results = max_messages, max_results
        self.readiness_probe, self.profile_id = readiness_probe, profile_id

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
        route = (scope.get("method"), scope.get("path"))
        if route == ("GET", "/healthz"):
            return await respond(200, {"status": "alive"})
        if route not in {("POST", "/add"), ("POST", "/search"), ("GET", "/readyz")}:
            return await respond(404, {"error": "not_found"})
        if self.active >= self.max_concurrency:
            return await respond(503, {"error": "busy"})
        self.active += 1
        try:

            async def dispatch():
                if scope["path"] == "/readyz":
                    if self.readiness_probe is None:
                        raise WriteNotReady("no readiness probe configured")
                    try:
                        await asyncio.wait_for(
                            self.readiness_probe(), min(5, self.timeout_seconds)
                        )
                    except Exception:  # noqa: BLE001 - redact arbitrary dependency errors
                        raise WriteNotReady("dependency probe failed") from None
                    return await respond(
                        200, {"status": "ready", "profile_id": self.profile_id}
                    )
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
                        if len(request.messages) > self.max_messages:
                            return await respond(413, {"error": "too_many_messages"})
                        result = await self.boundary.add(request)
                    else:
                        request = SearchRequest.model_validate(payload)
                        if request.top_k > self.max_results:
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
    parser.add_argument("--profile", choices=("bm25", "local-hybrid"), default="bm25")
    parser.add_argument("--pg-schema")
    parser.add_argument("--embedding-model-path", type=Path)
    parser.add_argument("--reranker-model-path", type=Path)
    parser.add_argument("--reranker-device", default="cpu")
    parser.add_argument("--rerank-policy", choices=LOCAL_RERANK_POLICIES)
    parser.add_argument("--request-timeout-seconds", type=float, default=30)
    parser.add_argument("--max-concurrency", type=int, default=8)
    parser.add_argument("--max-body-bytes", type=int, default=2_000_000)
    parser.add_argument("--max-messages", type=int, default=1000)
    parser.add_argument("--max-results", type=int, default=1000)
    parser.add_argument("--allow-remote-bind", action="store_true")
    args = parser.parse_args()
    if args.rerank_policy is not None and args.profile != "local-hybrid":
        parser.error("--rerank-policy requires --profile local-hybrid")
    token = os.environ.get("DOPPEL_AML_BEARER_TOKEN", "")
    if not token.strip():
        parser.error("DOPPEL_AML_BEARER_TOKEN must be set")
    # Validate all transport settings before opening files, DBs or models.
    limits = {
        "timeout_seconds": args.request_timeout_seconds,
        "max_concurrency": args.max_concurrency,
        "max_body_bytes": args.max_body_bytes,
        "max_messages": args.max_messages,
        "max_results": args.max_results,
    }
    try:
        validate_service_bounds(token, **limits)
    except ValueError:
        parser.error(
            "token must be visible ASCII; bounds positive and finite; messages/results between 1 and 1000"
        )
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if args.host not in {"127.0.0.1", "::1", "localhost"} and (
        not args.allow_remote_bind or len(token) < 32
    ):
        parser.error(
            "non-loopback binding requires --allow-remote-bind and a token of at least 32 characters; use a TLS proxy"
        )
    if args.profile == "local-hybrid" and not (
        args.pg_schema
        and args.embedding_model_path
        and args.reranker_model_path
        and os.environ.get("DOPPEL_AML_PG_DSN", "").strip()
    ):
        parser.error(
            "local-hybrid requires DOPPEL_AML_PG_DSN, --pg-schema and both local model paths"
        )

    async def serve():
        import uvicorn  # optional dependency; no LLM/provider keys read

        if args.profile == "local-hybrid":
            from integrations.aml.retrieval import create_local_hybrid_backend

            backend = await create_local_hybrid_backend(
                args.directory,
                namespace=args.namespace,
                dsn=os.environ["DOPPEL_AML_PG_DSN"],
                schema=args.pg_schema,
                embedding_model_path=args.embedding_model_path,
                reranker_model_path=args.reranker_model_path,
                reranker_device=args.reranker_device,
                rerank_policy=args.rerank_policy or "bge",
            )
        else:
            backend = SQLiteRawBackend(
                args.directory,
                namespace=args.namespace,
                role_actors={"user": "owner", "assistant": "agent"},
            )
        try:
            await backend.ready()
            app = TextualASGI(
                TextualBoundary(backend, namespace=args.namespace),
                bearer_token=token,
                readiness_probe=backend.ready,
                profile_id=backend.profile_id,
                **limits,
            )
            await uvicorn.Server(
                uvicorn.Config(
                    app,
                    host=args.host,
                    port=args.port,
                    access_log=False,
                    log_level="warning",
                    proxy_headers=False,
                )
            ).serve()
        finally:
            await backend.close()

    asyncio.run(serve())


if __name__ == "__main__":
    main()
