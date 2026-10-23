"""Deployment guards/probes, no external database, models or paid services."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime

import httpx
import pytest

from integrations.aml.contract import TextualBoundary, memory_scope
from integrations.aml.retrieval import postgres_target_identity
from integrations.aml.service import (
    SQLiteRawBackend,
    TextualASGI,
    main,
    validate_service_bounds,
)


def make_host(path):
    return SQLiteRawBackend(
        path,
        namespace="deployment-test",
        role_actors={"user": "owner", "assistant": "agent"},
    )


def client(host, **kwargs):
    app = TextualASGI(
        TextualBoundary(host, namespace="deployment-test"),
        bearer_token="local-test-token",
        readiness_probe=host.ready,
        profile_id=host.profile_id,
        **kwargs,
    )
    return app, httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url="http://local",
        headers={"Authorization": "Bearer local-test-token"},
    )


async def test_authenticated_readiness_is_opaque_stable_and_does_not_ingest(tmp_path):
    host = make_host(tmp_path)
    profile_id = host.profile_id
    _, c = client(host)
    async with c:
        assert (await c.get("/healthz")).json() == {"status": "alive"}
        ready = await c.get("/readyz")
        assert ready.json() == {"status": "ready", "profile_id": profile_id}
        assert len(profile_id) == 64
        assert "deployment-test" not in ready.text
        assert (
            await c.get("/readyz", headers={"Authorization": "Bearer wrong"})
        ).status_code == 401
        assert (await c.post("/healthz")).status_code == 404
        assert host.journal.execute("SELECT count(*) FROM writes").fetchone()[0] == 0
        assert host.journal.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
    await host.close()
    host = make_host(tmp_path)
    assert host.profile_id == profile_id
    await host.ready()
    await host.close()


async def test_dependency_failure_is_not_liveness_failure_and_never_leaks(tmp_path):
    host = make_host(tmp_path)

    async def failed(*args):
        raise RuntimeError("SECRET_PASSWORD_AND_PRIVATE_TEXT")

    host.store.get = failed
    _, c = client(host)
    async with c:
        response = await c.get("/readyz")
        assert response.status_code == 503 and response.json() == {"error": "not_ready"}
        assert "SECRET" not in response.text
        assert (await c.get("/healthz")).status_code == 200
    await host.close()


async def test_readiness_is_not_an_all_users_completion_certificate(tmp_path):
    host = make_host(tmp_path)
    scope = memory_scope("deployment-test", "pending-owner")
    host.journal.execute(
        "INSERT INTO writes VALUES (?,?,?,?,0)",
        ("unfinished", "payload", scope.scope_key, datetime.now(UTC).isoformat()),
    )
    _, c = client(host)
    async with c:
        assert (await c.get("/readyz")).status_code == 200
        assert (
            await c.post(
                "/search",
                json={"user_id": "pending-owner", "query": "anything", "top_k": 1},
            )
        ).status_code == 503
        assert (
            await c.post(
                "/search",
                json={"user_id": "another-owner", "query": "anything", "top_k": 1},
            )
        ).status_code == 200
    await host.close()


async def test_readiness_timeout_capacity_and_closed_backend_fail_cleanly(tmp_path):
    host = make_host(tmp_path)
    original = host.ready

    async def slow():
        await asyncio.sleep(1)

    host.ready = slow
    app, c = client(host, timeout_seconds=0.01)
    async with c:
        assert (await c.get("/readyz")).status_code == 503
        assert app.active == 0
        app.active = app.max_concurrency
        assert (await c.get("/healthz")).status_code == 200
        assert (await c.get("/readyz")).json() == {"error": "busy"}
        app.active = 0
        app.readiness_probe = original
        await host.close()
        assert (await c.get("/readyz")).status_code == 503


async def test_custom_backend_without_a_probe_is_not_claimed_ready(tmp_path):
    host = make_host(tmp_path)
    app, c = client(host)
    app.readiness_probe = None
    async with c:
        assert (await c.get("/readyz")).status_code == 503
        assert (await c.get("/healthz")).status_code == 200
    await host.close()


async def test_explicit_message_and_result_limits_apply_before_backend(tmp_path):
    host = make_host(tmp_path)
    _, c = client(host, max_messages=1, max_results=1)
    async with c:
        payload = {
            "request_id": "r",
            "user_id": "u",
            "session_id": "s",
            "messages": [
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "two"},
            ],
        }
        assert (await c.post("/add", json=payload)).status_code == 413
        assert (
            await c.post("/search", json={"user_id": "u", "query": "one", "top_k": 2})
        ).status_code == 422
        assert host.journal.execute("SELECT count(*) FROM writes").fetchone()[0] == 0
    await host.close()


@pytest.mark.parametrize(
    "config",
    [
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": float("inf")},
        {"timeout_seconds": 0},
        {"timeout_seconds": True},
        {"max_concurrency": 0},
        {"max_concurrency": True},
        {"max_body_bytes": 0.5},
        {"max_messages": 1001},
        {"max_results": 1001},
        {"bearer_token": "line\nbreak"},
        {"bearer_token": "has space"},
    ],
)
def test_bounds_reject_invalid_values(config):
    with pytest.raises(ValueError):
        validate_service_bounds(**{"bearer_token": "local-token", **config})


@pytest.mark.parametrize(
    "flags",
    [
        ["--request-timeout-seconds", "nan"],
        ["--max-concurrency", "0"],
        ["--host", "0.0.0.0"],
        ["--port", "0"],
        ["--rerank-policy", "rank-fusion"],
        ["--rerank-policy", "bge"],
        ["--profile", "local-hybrid", "--rerank-policy", "unknown"],
        ["--expected-profile-id", "not-a-digest"],
        ["--expected-profile-id", "A" * 64],
        ["--expected-profile-id", "a" * 63],
    ],
)
def test_cli_bad_bounds_fail_before_creating_state(
    tmp_path, monkeypatch, capsys, flags
):
    directory = tmp_path / "must-not-exist"
    monkeypatch.setenv(
        "DOPPEL_AML_BEARER_TOKEN", "synthetic-secret-token-long-enough-for-remote"
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "service",
            "--directory",
            str(directory),
            "--namespace",
            "n",
            "--bind-owner-roles",
            *flags,
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2 and not directory.exists()
    assert "synthetic-secret" not in capsys.readouterr().err


@pytest.mark.parametrize("policy", [None, "bge", "rank-fusion"])
def test_cli_forwards_explicit_policy_and_keeps_legacy_default(
    tmp_path, monkeypatch, policy
):
    pytest.importorskip("uvicorn")
    from integrations.aml import retrieval

    received = {}

    async def capture(*args, **kwargs):
        received.update(kwargs)
        raise RuntimeError("factory boundary reached")

    monkeypatch.setattr(retrieval, "create_local_hybrid_backend", capture)
    monkeypatch.setenv("DOPPEL_AML_BEARER_TOKEN", "synthetic-test-token")
    monkeypatch.setenv("DOPPEL_AML_PG_DSN", "synthetic-no-db-contact")
    directory = tmp_path / "not-created"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "service",
            "--directory",
            str(directory),
            "--namespace",
            "n",
            "--bind-owner-roles",
            "--profile",
            "local-hybrid",
            "--pg-schema",
            "s",
            "--embedding-model-path",
            "absent-embedding",
            "--reranker-model-path",
            "absent-reranker",
            *(["--rerank-policy", policy] if policy else []),
        ],
    )
    with pytest.raises(RuntimeError, match="factory boundary reached"):
        main()
    assert received["rerank_policy"] == (policy or "bge")
    assert not directory.exists()


def test_postgres_identity_is_canonical_and_credential_free():
    first = postgres_target_identity(
        "postgresql://alice:SECRET_ONE@HOST:5432/books", "s"
    )
    assert first == postgres_target_identity(
        "postgres://alice:SECRET_TWO@host/books?sslmode=require", "s"
    )
    assert first != postgres_target_identity(
        "postgresql://alice:p@host/books", "other_schema"
    )
    assert first != postgres_target_identity("postgresql://alice:p@host/other_db", "s")
    assert first == postgres_target_identity("postgresql://%61lice:p@host/%62ooks", "s")
    assert "SECRET" not in json.dumps(first)


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://alice:SECRET@host/books?database=other",
        "postgresql://alice:SECRET@host/books?host=other",
        "postgresql://alice:SECRET@host/books?user=other",
        "postgresql://alice:SECRET@host/books?password=other",
        "postgresql://alice:SECRET@host/books?sslmode=require&sslmode=disable",
        "postgresql://alice:SECRET@host/books?sslmode=invalid",
        "postgresql://alice:SECRET@host/books#fragment",
        "postgresql://alice:SECRET@host:bad/books",
        "postgresql://alice:SECRET@host/",
        "postgresql://host/books",
        "postgresql://alice:SECRET@host1,host2/books",
    ],
)
def test_postgres_identity_rejects_implicit_targets_and_query_overrides(dsn):
    with pytest.raises(ValueError) as error:
        postgres_target_identity(dsn, "s")
    assert "SECRET" not in str(error.value)


async def test_opt_in_public_health_discloses_no_readiness_or_sources(tmp_path):
    host = make_host(tmp_path)
    _, c = client(host, public_health=True)
    async with c:
        for authorization in ("", "Bearer wrong"):
            headers = {"Authorization": authorization}
            health = await c.get("/healthz", headers=headers)
            assert health.status_code == 200
            assert health.json() == {"status": "alive"}
            assert health.headers["cache-control"] == "no-store"
            assert (await c.get("/readyz", headers=headers)).status_code == 401
            assert (await c.post("/healthz", headers=headers)).status_code == 401
            assert (await c.post("/add", headers=headers, json={})).status_code == 401
            assert (
                await c.post("/search", headers=headers, json={})
            ).status_code == 401
        await host.close()
        assert (
            await c.get("/healthz", headers={"Authorization": ""})
        ).status_code == 200
        assert (await c.get("/readyz")).status_code == 503


async def test_score_omission_is_transport_only_without_reordering_or_source_changes(
    tmp_path,
):
    host = make_host(tmp_path)
    _, original_client = client(host)
    _, projected_client = client(host, omit_search_scores=True)
    write = {
        "request_id": "r",
        "user_id": "u",
        "session_id": "s",
        "messages": [
            {"role": "user", "content": "My telescope is with Morgan."},
            {"role": "assistant", "content": "I suggested a telescope case."},
        ],
    }
    query = {"user_id": "u", "query": "telescope", "top_k": 100}
    async with original_client as original, projected_client as projected:
        added = await projected.post("/add", json=write)
        assert added.status_code == 200 and added.json()["success"] is True
        before = (await original.post("/search", json=query)).json()
        after = (await projected.post("/search", json=query)).json()
        assert len(before["data"]) == 2
        assert all("score" in row for row in before["data"])
        assert all("score" not in row for row in after["data"])
        assert after == {
            "data": [
                {k: v for k, v in row.items() if k != "score"} for row in before["data"]
            ]
        }
        assert (await original.post("/search", json=query)).json() == before
    await host.close()


@pytest.mark.parametrize(
    "config",
    [
        {"public_health": 1},
        {"public_health": "yes"},
        {"omit_search_scores": None},
        {"omit_search_scores": 0},
    ],
)
def test_transport_switches_are_strict_booleans(tmp_path, config):
    host = make_host(tmp_path)
    try:
        with pytest.raises(ValueError, match="boolean"):
            client(host, **config)
    finally:
        asyncio.run(host.close())


@pytest.mark.parametrize("pin", ["correct", "wrong", "none"])
def test_expected_profile_is_checked_before_listening_and_backend_is_closed(
    tmp_path, monkeypatch, pin
):
    uvicorn = pytest.importorskip("uvicorn")
    from integrations.aml import service

    host = make_host(tmp_path)
    served = []

    class FakeServer:
        def __init__(self, config):
            served.append(config.app)

        async def serve(self):
            pass

    monkeypatch.setattr(service, "SQLiteRawBackend", lambda *a, **kw: host)
    monkeypatch.setattr(uvicorn, "Server", FakeServer)
    monkeypatch.setenv("DOPPEL_AML_BEARER_TOKEN", "synthetic-test-token")
    expected = host.profile_id if pin == "correct" else "0" * 64
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "service",
            "--directory",
            str(tmp_path),
            "--namespace",
            "deployment-test",
            "--bind-owner-roles",
            "--public-health",
            "--omit-search-scores",
            *(["--expected-profile-id", expected] if pin != "none" else []),
        ],
    )
    if pin == "wrong":
        with pytest.raises(ValueError, match="does not match expected"):
            main()
        assert not served
    else:
        main()
        assert len(served) == 1
        assert served[0].public_health and served[0].omit_search_scores
        assert served[0].profile_id == host.profile_id
    assert host._closed
