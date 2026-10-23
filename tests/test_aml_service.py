from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from integrations.aml.contract import TextualBoundary
from integrations.aml.service import SQLiteRawBackend, TextualASGI


def backend(path):
    return SQLiteRawBackend(
        path, namespace="test", role_actors={"user": "owner", "assistant": "agent"}
    )


def client(host, **kwargs):
    app = TextualASGI(
        TextualBoundary(host, namespace="test"), bearer_token="test-token", **kwargs
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://local",
        headers={"Authorization": "Bearer test-token"},
    )


def payload(**updates):
    return {
        "request_id": "r1",
        "user_id": " u ",
        "session_id": "s1",
        "messages": [
            {
                "role": "user",
                "content": "My telescope is with Morgan.",
                "timestamp": 1704067200000,
            },
            {"role": "assistant", "content": "I suggested a telescope case."},
        ],
        **updates,
    }


async def test_real_http_boundary_durable_restart_retry_cross_session_and_isolation(
    tmp_path,
):
    host = backend(tmp_path)
    async with client(host) as c:
        added = await c.post("/add", json=payload())
        assert added.status_code == 200, added.text
        assert added.json()["user_id"] == " u "
        result = await c.post(
            "/search", json={"user_id": " u ", "query": "telescope", "top_k": 10}
        )
        assert result.status_code == 200, result.text
        initial = result.json()
        assert len(initial["data"]) == 2
        body = [json.loads(x["content"]) for x in initial["data"]]
        assert any("historical_assistant" in json.dumps(x) for x in body)
        assert all("score" in x for x in initial["data"])
        assert (
            await c.post(
                "/search", json={"user_id": "u", "query": "telescope", "top_k": 10}
            )
        ).json() == {"data": []}
    await host.close()
    host = backend(tmp_path)
    async with client(host) as c:
        assert (await c.post("/add", json=payload())).status_code == 200
        after = await c.post(
            "/search", json={"user_id": " u ", "query": "telescope", "top_k": 10}
        )
        assert after.json() == initial
        assert (
            await c.post("/add", json=payload(session_id="changed"))
        ).status_code == 409
        assert (
            await c.post(
                "/add",
                json=payload(
                    request_id="r2",
                    session_id="s2",
                    messages=[
                        {"role": "user", "content": "Morgan has the telescope manual."}
                    ],
                ),
            )
        ).status_code == 200
        hits = (
            await c.post(
                "/search", json={"user_id": " u ", "query": "telescope", "top_k": 10}
            )
        ).json()["data"]
        assert len(hits) == 3
    await host.close()


@pytest.mark.parametrize(
    "body,status", [(b"invalid", 422), (b"[]", 422), (b"{}", 422), (b"x" * 500, 413)]
)
async def test_bad_requests_never_echo_source_or_touch_backend(tmp_path, body, status):
    host = backend(tmp_path)
    async with client(host, max_body_bytes=256) as c:
        result = await c.post("/add", content=body)
        assert result.status_code == status
        assert host.journal.execute("SELECT count(*) FROM writes").fetchone()[0] == 0
    await host.close()


async def test_authentication_and_redacted_backend_failure(tmp_path):
    host = backend(tmp_path)
    async with client(host) as c:
        assert (
            await c.post(
                "/add", json=payload(), headers={"Authorization": "Bearer wrong"}
            )
        ).status_code == 401
        original = host.add

        async def fail(scope, request):
            raise RuntimeError("PRIVATE_HISTORY_AND_SECRET")

        host.add = fail
        result = await c.post("/add", json=payload())
        assert result.status_code == 500 and "PRIVATE" not in result.text
        host.add = original
    await host.close()


async def test_partial_failure_survives_restart_and_retry_repairs_without_duplicate(
    tmp_path,
):
    host = backend(tmp_path)
    original = host.store.write_event
    calls = 0

    async def fail_second(scope, message):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated interruption")
        return await original(scope, message)

    host.store.write_event = fail_second
    async with client(host) as c:
        assert (await c.post("/add", json=payload())).status_code == 500
        assert (
            await c.post("/add", json=payload(request_id="different"))
        ).status_code == 503
        assert (
            await c.post(
                "/search", json={"user_id": " u ", "query": "telescope", "top_k": 10}
            )
        ).status_code == 503
    await host.close()
    host = backend(tmp_path)
    async with client(host) as c:
        assert (await c.post("/add", json=payload())).status_code == 200
        result = await c.post(
            "/search", json={"user_id": " u ", "query": "telescope", "top_k": 10}
        )
        assert len(result.json()["data"]) == 2
    await host.close()


async def test_profile_drift_refused_and_timestamp_overflow_fails_closed(tmp_path):
    host = backend(tmp_path)
    async with client(host) as c:
        result = await c.post(
            "/add",
            json=payload(
                messages=[{"role": "user", "content": "secret", "timestamp": 10**100}]
            ),
        )
        assert result.status_code == 422
        assert host.journal.execute("SELECT count(*) FROM writes").fetchone()[0] == 0
        assert (await c.post("/add", json=payload())).status_code == 200
    await host.close()
    with pytest.raises(ValueError, match="profile differs"):
        SQLiteRawBackend(
            tmp_path,
            namespace="different",
            role_actors={"user": "owner", "assistant": "agent"},
        )


async def test_timeout_and_concurrency_bounds_release_capacity(tmp_path):
    host = backend(tmp_path)
    original = host.search
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow(scope, request):
        entered.set()
        await release.wait()
        return await original(scope, request)

    host.search = slow
    async with client(host, max_concurrency=1, timeout_seconds=0.05) as c:
        first = asyncio.create_task(
            c.post("/search", json={"user_id": "u", "query": "x", "top_k": 1})
        )
        await entered.wait()
        assert (
            await c.post("/search", json={"user_id": "u", "query": "x", "top_k": 1})
        ).status_code == 503
        assert (await first).status_code == 503
        release.set()
        assert (
            await c.post("/search", json={"user_id": "u", "query": "x", "top_k": 1})
        ).status_code == 200
    await host.close()


@pytest.mark.parametrize("hard", [False, True])
async def test_completed_retry_cannot_claim_revoked_sources_searchable_or_resurrect_them(
    tmp_path, hard
):
    from integrations.aml.contract import memory_scope

    host = backend(tmp_path)
    async with client(host) as c:
        assert (await c.post("/add", json=payload())).status_code == 200
        scope = memory_scope("test", " u ")
        identity = host.journal.execute(
            "SELECT memory FROM sources LIMIT 1"
        ).fetchone()[0]
        assert await host.store.forget(scope, identity, hard=hard)
        assert (await c.post("/add", json=payload())).status_code == 503
        stored = await host.store.get(scope, identity)
        if hard:
            assert stored is None
        else:
            assert stored is not None and stored.state == "expired"
    await host.close()


@pytest.mark.parametrize("competition_transport", [False, True])
async def test_actual_tcp_process_restart(tmp_path, competition_transport):
    import os
    import socket
    import subprocess
    import sys

    pytest.importorskip("uvicorn")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(os.environ, DOPPEL_AML_BEARER_TOKEN="local-smoke-token")
    for key in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        env.pop(key, None)
    command = [
        sys.executable,
        "-m",
        "integrations.aml.service",
        "--directory",
        str(tmp_path),
        "--namespace",
        "test",
        "--bind-owner-roles",
        "--port",
        str(port),
        *(["--public-health", "--omit-search-scores"] if competition_transport else []),
    ]
    profile_id = ""
    for run in range(2):
        invocation = command + (["--expected-profile-id", profile_id] if run else [])
        process = await asyncio.to_thread(
            subprocess.Popen,
            invocation,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{port}",
                headers={"Authorization": "Bearer local-smoke-token"},
                timeout=1,
                trust_env=False,
            ) as c:
                for _ in range(100):
                    if process.poll() is not None:
                        pytest.fail("local service exited during startup")
                    try:
                        response = await c.post(
                            "/search",
                            json={"user_id": " u ", "query": "telescope", "top_k": 10},
                        )
                        break
                    except httpx.TransportError:
                        await asyncio.sleep(0.1)
                else:
                    pytest.fail("local service startup timeout")
                assert response.status_code == 200
                health = await c.get("/healthz")
                ready = await c.get("/readyz")
                assert health.json() == {"status": "alive"}
                assert (
                    await c.get("/healthz", headers={"Authorization": ""})
                ).status_code == (200 if competition_transport else 401)
                assert (
                    await c.get("/readyz", headers={"Authorization": ""})
                ).status_code == 401
                assert ready.status_code == 200 and ready.json()["status"] == "ready"
                assert len(ready.json()["profile_id"]) == 64
                if run == 0:
                    profile_id = ready.json()["profile_id"]
                    assert (await c.post("/add", json=payload())).status_code == 200
                else:
                    assert ready.json()["profile_id"] == profile_id
                    assert len(response.json()["data"]) == 2
                    assert all(
                        ("score" not in row) == competition_transport
                        for row in response.json()["data"]
                    )
                    assert (await c.post("/add", json=payload())).status_code == 200
        finally:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait, timeout=5)
