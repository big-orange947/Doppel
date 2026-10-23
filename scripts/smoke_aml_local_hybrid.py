"""Opt-in real loopback/PG/model smoke; synthetic data only, no paid APIs.

Requires an absent, dedicated schema and new local directory. Retains six small
source/vector fixtures for inspection; never drops schemas or edits old caches.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from doppel_memory.indexing import memory_index_fingerprint
from doppel_memory.postgres_store import PostgreSQLStore
from doppel_memory.vector import PostgreSQLVectorIndex
from integrations.aml.contract import memory_scope
from integrations.aml.local_models import LocalEmbedding
from integrations.aml.retrieval import LOCAL_RERANK_POLICIES

NAMESPACE = "local-hybrid-live-smoke-v1"
OWNER = " smoke-owner-a "
QUERY = {"user_id": OWNER, "query": "optical instrument", "top_k": 10}
WRITES = [
    {
        "request_id": "a-first",
        "user_id": OWNER,
        "session_id": "a-january",
        "messages": [
            {
                "role": "user",
                "content": "I left my telescope with Morgan for safekeeping.",
                "timestamp": 1704067200000,
            },
            {
                "role": "assistant",
                "content": "I suggested buying a protective case for the telescope.",
                "timestamp": 1704067201000,
            },
        ],
    },
    {
        "request_id": "a-second",
        "user_id": OWNER,
        "session_id": "a-march",
        "messages": [
            {
                "role": "user",
                "content": "The telescope is now back with me. Morgan returned it on March 2.",
                "timestamp": 1709337600000,
            },
            {
                "role": "assistant",
                "content": "Earlier, I recommended a padded case.",
                "timestamp": 1709337601000,
            },
        ],
    },
    {
        "request_id": "b-first",
        "user_id": "smoke-owner-b",
        "session_id": "b-private",
        "messages": [
            {
                "role": "user",
                "content": "My telescope is with SECRET_B_KEEPER.",
                "timestamp": 1704067200000,
            },
            {
                "role": "assistant",
                "content": "PRIVATE_B_ADVICE about telescope maintenance.",
                "timestamp": 1704067201000,
            },
        ],
    },
]


def validate_evidence(response: dict) -> None:
    rows = response["data"]
    sources = [json.loads(row["content"])["source"] for row in rows]
    expected = {
        (write["session_id"], i): message
        for write in WRITES[:2]
        for i, message in enumerate(write["messages"])
    }
    assert len(sources) == len(expected) == 4
    assert len({row["id"] for row in rows}) == 4
    assert {(s["session_id"], s["turn_index"]) for s in sources} == set(expected)
    for source in sources:
        original = expected[(source["session_id"], source["turn_index"])]
        role = original["role"]
        assert source["text"] == original["content"]
        assert source["transport_role"] == role
        assert source["speaker"] == (
            "owner" if role == "user" else "historical_assistant"
        )
        assert source["actor"] == ("owner" if role == "user" else "agent")
        assert source["source_authority"] == (
            "human_self" if role == "user" else "agent_output"
        )
        assert (
            source["observed_at"]
            == datetime.fromtimestamp(original["timestamp"] / 1000, UTC).isoformat()
        )
    assert "SECRET_B" not in json.dumps(response) and "PRIVATE_B" not in json.dumps(
        response
    )


async def run(args) -> dict:
    asyncpg = importlib.import_module("asyncpg")

    dsn = os.environ["DOPPEL_AML_PG_DSN"]
    if args.output.exists() or args.directory.exists():
        raise ValueError("use a new output and state directory; no overwrite/reset")
    connection = await asyncpg.connect(dsn)
    try:
        if await connection.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name=$1)",
            args.schema,
        ):
            raise ValueError("dedicated smoke schema already exists; refusing mutation")
    finally:
        await connection.close()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    token = secrets.token_urlsafe(32)
    env = dict(
        os.environ,
        DOPPEL_AML_BEARER_TOKEN=token,
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
    )
    for key in list(env):
        if "API_KEY" in key.upper():
            env.pop(key)
    command = [
        sys.executable,
        "-m",
        "integrations.aml.service",
        "--directory",
        str(args.directory),
        "--namespace",
        NAMESPACE,
        "--bind-owner-roles",
        "--profile",
        "local-hybrid",
        "--pg-schema",
        args.schema,
        "--embedding-model-path",
        str(args.embedding_model_path),
        "--reranker-model-path",
        str(args.reranker_model_path),
        "--reranker-device",
        args.reranker_device,
        "--rerank-policy",
        args.rerank_policy,
        "--port",
        str(port),
    ]
    report = {
        "runner": "doppel.aml-local-hybrid-smoke.v1",
        "passed": False,
        "schema": args.schema,
        "namespace": NAMESPACE,
        "device_requested": args.reranker_device,
        "rerank_policy": args.rerank_policy,
        "paid_calls": 0,
        "model_downloads_allowed": False,
        "fixtures_retained": True,
        "phases": [],
    }
    before = None
    profile_id = None
    try:
        for phase in ("initial", "restart"):
            process = await asyncio.to_thread(
                subprocess.Popen,
                command,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            started = time.monotonic()
            try:
                async with httpx.AsyncClient(
                    base_url=f"http://127.0.0.1:{port}",
                    headers={"Authorization": f"Bearer {token}"},
                    trust_env=False,
                    timeout=60,
                ) as client:
                    while True:
                        if process.poll() is not None:
                            raise RuntimeError(
                                f"service startup exited ({process.returncode})"
                            )
                        try:
                            ready = await client.post("/search", json=QUERY)
                            assert ready.status_code == 200, (
                                f"readiness HTTP {ready.status_code}"
                            )
                            break
                        except httpx.TransportError:
                            if time.monotonic() - started > 180:
                                raise TimeoutError(
                                    "local service startup exceeded 180s"
                                ) from None
                            await asyncio.sleep(0.5)
                    startup_seconds = time.monotonic() - started
                    health = await client.get("/healthz")
                    assert health.status_code == 200
                    assert health.json() == {"status": "alive"}
                    readiness = await client.get("/readyz")
                    assert readiness.status_code == 200
                    current_profile = readiness.json()["profile_id"]
                    assert len(current_profile) == 64
                    if profile_id is None:
                        profile_id = current_profile
                    assert current_profile == profile_id
                    if phase == "initial":
                        assert ready.json() == {"data": []}
                        for write in WRITES:
                            added = await client.post("/add", json=write)
                            assert added.status_code == 200, (
                                f"add HTTP {added.status_code}"
                            )
                            assert added.json() == {
                                "success": True,
                                **{
                                    k: write[k]
                                    for k in ("request_id", "user_id", "session_id")
                                },
                            }
                    else:
                        validate_evidence(ready.json())
                        assert ready.json() == before, (
                            "restart changed evidence/order/scores"
                        )
                    for write in WRITES:
                        assert (
                            await client.post("/add", json=write)
                        ).status_code == 200
                    search_started = time.monotonic()
                    result = await client.post("/search", json=QUERY)
                    assert result.status_code == 200, (
                        f"search HTTP {result.status_code}"
                    )
                    validate_evidence(result.json())
                    wide = await client.post("/search", json={**QUERY, "top_k": 1000})
                    assert wide.status_code == 200 and wide.json() == result.json()
                    if before is None:
                        before = result.json()
                    else:
                        assert result.json() == before
                    assert (
                        await client.post(
                            "/search", json={**QUERY, "user_id": OWNER.strip()}
                        )
                    ).json() == {"data": []}
                    other = await client.post(
                        "/search", json={**QUERY, "user_id": "smoke-owner-b"}
                    )
                    assert other.status_code == 200 and len(other.json()["data"]) == 2
                    assert all(
                        json.loads(row["content"])["source"]["session_id"]
                        == "b-private"
                        for row in other.json()["data"]
                    )
                    assert (
                        await client.post(
                            "/add", json={**WRITES[0], "session_id": "conflict"}
                        )
                    ).status_code == 409
                    assert (
                        await client.post(
                            "/search",
                            json=QUERY,
                            headers={"Authorization": "Bearer invalid"},
                        )
                    ).status_code == 401
                    report["phases"].append(
                        {
                            "name": phase,
                            "passed": True,
                            "startup_seconds": round(startup_seconds, 3),
                            "search_and_checks_seconds": round(
                                time.monotonic() - search_started, 3
                            ),
                            "owner_a_hits": 4,
                            "owner_b_hits": 2,
                        }
                    )
                    print(
                        f"{phase}: attributed search / isolation / idempotence / conflict / authentication passed",
                        flush=True,
                    )
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    await asyncio.to_thread(process.wait, timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    await asyncio.to_thread(process.wait, timeout=10)
        store = PostgreSQLStore(dsn, schema=args.schema)
        try:
            index = PostgreSQLVectorIndex(
                store, LocalEmbedding(args.embedding_model_path)
            )
            await index.initialize()
            with sqlite3.connect(args.directory / "service-journal.sqlite3") as journal:
                saved_profile = journal.execute("SELECT value FROM profile").fetchone()[
                    0
                ]
                assert hashlib.sha256(saved_profile.encode()).hexdigest() == profile_id
                policy_identity = json.loads(saved_profile)["strategy"]["reranker"]
                if args.rerank_policy == "rank-fusion":
                    assert policy_identity["policy"] == "retrieval-neural-rrf-v1"
                    assert policy_identity["rrf_k"] == 60
                    assert policy_identity["max_candidates"] == 80
                else:
                    assert "policy" not in policy_identity
                mappings = journal.execute(
                    "SELECT scope,memory FROM sources"
                ).fetchall()
                assert (
                    journal.execute(
                        "SELECT count(*) FROM writes WHERE done<>1"
                    ).fetchone()[0]
                    == 0
                )
            scopes = {
                s.scope_key: s
                for s in [
                    memory_scope(NAMESPACE, OWNER),
                    memory_scope(NAMESPACE, "smoke-owner-b"),
                ]
            }
            assert len(mappings) == 6
            for scope_key, memory_id in mappings:
                record = await store.get(scopes[scope_key], memory_id)
                assert record is not None
                entry = await index.inspect(scopes[scope_key], memory_id)
                assert (
                    entry is not None
                    and entry.fingerprint == memory_index_fingerprint(record)
                )
                assert (
                    entry.scope_key == scope_key
                    and entry.source_version == record.version
                )
            pool = await store._ensure_pool()
            async with pool.acquire() as connection:
                assert (
                    await connection.fetchval(
                        f'SELECT count(*) FROM "{args.schema}"."doppel_memory_records"'
                    )
                    == 6
                )
                assert (
                    await connection.fetchval(
                        f"SELECT count(*) FROM {index._table_sql}"
                    )
                    == 6
                )
            report.update(
                passed=True,
                verified_index_entries=6,
                raw_records=6,
                schema_version=1,
                profile_id=profile_id,
                reranker_identity=policy_identity,
                embedding=index.identity,
                results_sha256=hashlib.sha256(
                    json.dumps(before, sort_keys=True).encode()
                ).hexdigest(),
            )
        finally:
            await store.close()
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        # Never persist arbitrary provider/database exception text or credentials.
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--embedding-model-path", type=Path, required=True)
    parser.add_argument("--reranker-model-path", type=Path, required=True)
    parser.add_argument("--reranker-device", default="cpu")
    parser.add_argument("--rerank-policy", choices=LOCAL_RERANK_POLICIES, default="bge")
    args = parser.parse_args()
    # Validate quoted SQL identifier before any DB contact.
    PostgreSQLStore(os.environ["DOPPEL_AML_PG_DSN"], schema=args.schema)
    result = asyncio.run(run(args))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
