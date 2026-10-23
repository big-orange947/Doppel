"""Real HTTP/SQLite journals; fake vector/model boundaries, no Docker or API."""

from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

import httpx
import pytest

from doppel_memory.indexing import IndexEntry, memory_index_fingerprint
from doppel_memory.models import MemoryRecord, MemoryScope, RecallResult
from integrations.aml import local_models
from integrations.aml.contract import TextualBoundary, memory_scope
from integrations.aml.retrieval import (
    create_local_hybrid_backend,
    hybrid_profile,
    local_rerank_policy,
)
from integrations.aml.service import SQLiteRawBackend, TextualASGI


class Index:
    identity = "fake-durable-index-v1"

    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS vectors (id TEXT PRIMARY KEY, record TEXT)"
        )
        self.fail = False
        self.bad_manifest = False
        self.last_limit = 0
        self.writes = 0

    async def upsert(self, record):
        if self.fail:
            raise RuntimeError("private fake index error")
        self.db.execute(
            "INSERT OR REPLACE INTO vectors VALUES (?,?)",
            (record.memory_id, record.model_dump_json()),
        )
        self.db.commit()
        self.writes += 1

    async def inspect(self, scope, memory_id):
        row = self.db.execute(
            "SELECT record FROM vectors WHERE id=?", (memory_id,)
        ).fetchone()
        if row is None:
            return None
        record = MemoryRecord.model_validate_json(row[0])
        return IndexEntry(
            memory_id=memory_id,
            scope_key=record.scope.scope_key,
            source_version=record.version,
            fingerprint="wrong"
            if self.bad_manifest
            else memory_index_fingerprint(record),
        )

    async def search(self, query, scopes, *, filters=None, limit=10):
        if self.fail:
            from doppel_memory.vector import VectorIndexUnavailableError

            raise VectorIndexUnavailableError("private fake index error")
        self.last_limit = limit
        records = [
            MemoryRecord.model_validate_json(row[0])
            for row in self.db.execute("SELECT record FROM vectors ORDER BY id")
        ]
        return [
            RecallResult(
                scope=r.scope,
                memory_id=r.memory_id,
                fact="UNTRUSTED CACHED TEXT",
                similarity=0.9,
            )
            for r in records
            if r.scope.scope_key in {s.scope_key for s in scopes}
        ][:limit]


class Ranker:
    async def rerank(self, query, candidates, *, limit):
        self.seen = list(candidates)
        return [
            c.model_copy(update={"fact": "FORGED OWNER FACT", "raw_text": "FORGED"})
            for c in reversed(candidates)
        ][:limit]


def make_host(path, index, ranker, *, identity="v1"):
    profile = hybrid_profile(
        semantic_index=index,
        writer=index,
        reranker=ranker,
        identity={"test_models": identity},
    )
    return SQLiteRawBackend(
        path,
        namespace="hybrid-test",
        role_actors={"user": "owner", "assistant": "agent"},
        retrieval=profile,
    )


def client(host):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(
            TextualASGI(
                TextualBoundary(host, namespace="hybrid-test"),
                bearer_token="test-token",
            )
        ),
        base_url="http://local",
        headers={"Authorization": "Bearer test-token"},
    )


def payload(**changes):
    return {
        "user_id": "owner",
        "request_id": "r1",
        "session_id": "s1",
        "messages": [
            {"role": "user", "content": "My telescope is with Morgan."},
            {"role": "assistant", "content": "I suggested a telescope case."},
        ],
        **changes,
    }


async def test_hybrid_http_semantic_only_query_fixed_window_attribution_and_restart(
    tmp_path,
):
    index, ranker = Index(tmp_path / "index.sqlite3"), Ranker()
    host = make_host(tmp_path / "service", index, ranker)
    async with client(host) as c:
        assert (await c.post("/add", json=payload())).status_code == 200
        result = await c.post(
            "/search",
            json={"user_id": "owner", "query": "optical instrument", "top_k": 1},
        )
        assert result.status_code == 200, result.text
        assert len(result.json()["data"]) == 1
        assert index.last_limit == 80 and len(ranker.seen) == 2
        assert "FORGED" not in result.text and "UNTRUSTED" not in result.text
        assert "telescope" in result.text
        assert (
            await c.post(
                "/search",
                json={"user_id": "other", "query": "optical instrument", "top_k": 10},
            )
        ).json() == {"data": []}
    await host.close()
    index.db.close()
    index = Index(tmp_path / "index.sqlite3")
    host = make_host(tmp_path / "service", index, ranker)
    async with client(host) as c:
        assert (await c.post("/add", json=payload())).status_code == 200
        result = await c.post(
            "/search",
            json={"user_id": "owner", "query": "optical instrument", "top_k": 10},
        )
        assert len(result.json()["data"]) == 2
        texts = [json.loads(row["content"]) for row in result.json()["data"]]
        assert any("historical_assistant" in json.dumps(text) for text in texts)
        assert host.journal.execute("SELECT count(*) FROM sources").fetchone()[0] == 2
    await host.close()
    index.db.close()


@pytest.mark.parametrize("failure", ["upsert", "manifest"])
async def test_index_failure_keeps_scope_pending_until_same_request_repairs(
    tmp_path, failure
):
    index = Index(tmp_path / "index.sqlite3")
    index.fail, index.bad_manifest = failure == "upsert", failure == "manifest"
    host = make_host(tmp_path / "service", index, Ranker())
    async with client(host) as c:
        result = await c.post("/add", json=payload())
        assert result.status_code == (500 if failure == "upsert" else 503)
        assert "private" not in result.text
        assert host.journal.execute("SELECT done FROM writes").fetchone()[0] == 0
        assert (
            await c.post(
                "/search", json={"user_id": "owner", "query": "telescope", "top_k": 10}
            )
        ).status_code == 503
        assert (
            await c.post("/add", json=payload(request_id="different"))
        ).status_code == 503
    await host.close()
    index.fail = index.bad_manifest = False
    host = make_host(tmp_path / "service", index, Ranker())
    async with client(host) as c:
        assert (await c.post("/add", json=payload())).status_code == 200
        assert host.journal.execute("SELECT count(*) FROM sources").fetchone()[0] == 2
        assert (
            await c.post(
                "/search", json={"user_id": "owner", "query": "telescope", "top_k": 10}
            )
        ).status_code == 200
    await host.close()
    index.db.close()


async def test_completed_index_repair_failure_does_not_resurrect_revoked_sources(
    tmp_path,
):
    index = Index(tmp_path / "index.sqlite3")
    host = make_host(tmp_path / "service", index, Ranker())
    async with client(host) as c:
        assert (await c.post("/add", json=payload())).status_code == 200
        index.fail = True
        assert (await c.post("/add", json=payload())).status_code == 500
        assert host.journal.execute("SELECT done FROM writes").fetchone()[0] == -1
        assert (
            await c.post(
                "/search", json={"user_id": "owner", "query": "telescope", "top_k": 10}
            )
        ).status_code == 503
        memory_id = host.journal.execute(
            "SELECT memory FROM sources LIMIT 1"
        ).fetchone()[0]
        scope = memory_scope("hybrid-test", "owner")
        assert await host.store.forget(scope, memory_id, hard=True)
        index.fail = False
        assert (await c.post("/add", json=payload())).status_code == 503
        assert await host.store.get(scope, memory_id) is None
    await host.close()
    index.db.close()


async def test_hybrid_search_does_not_hide_vector_failure_with_lexical_fallback(
    tmp_path,
):
    index = Index(tmp_path / "index.sqlite3")
    host = make_host(tmp_path / "service", index, Ranker())
    async with client(host) as c:
        assert (await c.post("/add", json=payload())).status_code == 200
        index.fail = True
        result = await c.post(
            "/search", json={"user_id": "owner", "query": "telescope", "top_k": 10}
        )
        assert result.status_code == 500 and "private" not in result.text
    await host.close()
    index.db.close()


async def test_profile_drift_fails_without_changing_saved_profile(tmp_path):
    index = Index(tmp_path / "index.sqlite3")
    host = make_host(tmp_path / "service", index, Ranker())
    old = host.journal.execute("SELECT value FROM profile").fetchone()[0]
    await host.close()
    with pytest.raises(ValueError, match="profile differs"):
        make_host(tmp_path / "service", index, Ranker(), identity="v2")
    host = make_host(tmp_path / "service", index, Ranker())
    assert host.journal.execute("SELECT value FROM profile").fetchone()[0] == old
    await host.close()
    index.db.close()


def fake_packages(monkeypatch, tmp_path, *, scores=(0.2, 0.9), dimensions=512):
    (tmp_path / "config.json").write_text("{}")
    calls = {}

    class Embedding:
        def __init__(self, *args, **kwargs):
            calls["embedding_args"] = kwargs

        def embed(self, texts, **kwargs):
            return [[0.1] * dimensions for _ in texts]

    class Encoder:
        def __init__(self, *args, **kwargs):
            calls["reranker_args"] = kwargs

        def tokenizer(self, *args, **kwargs):
            return {"length": [10, 9000]}

        def predict(self, pairs, **kwargs):
            calls["pairs"] = pairs
            return scores

    monkeypatch.setattr(local_models, "version", lambda _: "fake-package-v1")
    monkeypatch.setattr(
        local_models.importlib,
        "import_module",
        lambda _: SimpleNamespace(TextEmbedding=Embedding, CrossEncoder=Encoder),
    )
    return calls


async def test_offline_local_models_no_remote_code_content_only_and_reorder_only(
    tmp_path, monkeypatch
):
    calls = fake_packages(monkeypatch, tmp_path)
    embedding = local_models.LocalEmbedding(tmp_path)
    assert len((await embedding.embed(["hello"]))[0]) == 512
    assert calls["embedding_args"]["local_files_only"] is True
    assert calls["embedding_args"]["specific_model_path"] == str(tmp_path.resolve())
    assert calls["embedding_args"]["providers"] == ["CPUExecutionProvider"]
    ranker = local_models.LocalCrossEncoder(tmp_path)
    candidates = [
        RecallResult(
            scope=MemoryScope(user_id="SECRET_OWNER", agent_id="a"),
            memory_id=str(i),
            fact=f"text-{i}",
        )
        for i in range(2)
    ]
    ranked = await ranker.rerank("question", candidates, limit=2)
    assert [r.memory_id for r in ranked] == ["1", "0"]
    assert calls["pairs"] == [("question", "text-0"), ("question", "text-1")]
    assert calls["reranker_args"]["local_files_only"] is True
    assert calls["reranker_args"]["trust_remote_code"] is False
    assert ranker.truncated_pairs == 1
    assert ranked[0].model_dump() == candidates[1].model_dump()
    before = embedding.version
    (tmp_path / "config.json").write_text('{"changed":true}')
    assert local_models.LocalEmbedding(tmp_path).version != before


@pytest.mark.parametrize("scores", [(float("nan"), 0.1), (0.1,), ()])
async def test_local_reranker_rejects_invalid_scores_without_fallback(
    tmp_path, monkeypatch, scores
):
    fake_packages(monkeypatch, tmp_path, scores=scores)
    ranker = local_models.LocalCrossEncoder(tmp_path)
    with pytest.raises(ValueError, match="invalid local reranker"):
        await ranker.rerank(
            "q", [RecallResult(fact="a"), RecallResult(fact="b")], limit=2
        )


async def test_local_embedding_rejects_wrong_dimensions(tmp_path, monkeypatch):
    fake_packages(monkeypatch, tmp_path, dimensions=511)
    with pytest.raises(ValueError, match="invalid local embedding"):
        await local_models.LocalEmbedding(tmp_path).embed(["text"])


class ReversingRanker:
    async def rerank(self, query, candidates, *, limit):
        self.seen, self.limit = list(candidates), limit
        return list(reversed(candidates))[:limit]


def test_ordering_policy_preserves_legacy_identity_and_snapshots_metadata():
    delegate = ReversingRanker()
    original = {"model": {"version": "local-v1"}, "device": "cpu"}
    ranker, legacy = local_rerank_policy(delegate, original)
    assert ranker is delegate and legacy == original
    fused, identity = local_rerank_policy(delegate, original, policy="rank-fusion")
    assert fused.delegate is delegate
    assert identity == {
        "policy": "retrieval-neural-rrf-v1",
        "rrf_k": 60,
        "retrieval_weight": 1,
        "neural_weight": 1,
        "tie_break": "retrieval-position",
        "max_candidates": 80,
        "delegate": original,
    }
    original["model"]["version"] = "changed"
    assert legacy["model"]["version"] == "local-v1"
    assert identity["delegate"]["model"]["version"] == "local-v1"
    with pytest.raises(ValueError, match="unsupported"):
        local_rerank_policy(delegate, {}, policy="unknown")


async def test_invalid_policy_rejected_before_models_files_or_database(tmp_path):
    with pytest.raises(ValueError, match="unsupported"):
        await create_local_hybrid_backend(
            tmp_path / "not-created",
            namespace="n",
            dsn="invalid",
            schema="s",
            embedding_model_path=tmp_path / "absent-model",
            reranker_model_path=tmp_path / "absent-ranker",
            rerank_policy="unknown",
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("top_k", [1, 20, 80, 1000])
async def test_fused_service_uses_complete_neural_order_then_locked_rrf(
    tmp_path, top_k
):
    from doppel_memory.rank_fusion import rank_fusion_order

    index = Index(tmp_path / "index.sqlite3")
    delegate = ReversingRanker()
    ranker, identity = local_rerank_policy(delegate, {}, policy="rank-fusion")
    profile = hybrid_profile(
        semantic_index=index, writer=index, reranker=ranker, identity=identity
    )
    host = SQLiteRawBackend(
        tmp_path / "service",
        namespace="hybrid-test",
        role_actors={"user": "owner", "assistant": "agent"},
        retrieval=profile,
    )
    async with client(host) as c:
        write = payload()
        write["messages"] += [
            {"role": "user", "content": "Morgan returned the telescope."},
            {"role": "assistant", "content": "I recommended optical lens cleaning."},
        ]
        assert (await c.post("/add", json=write)).status_code == 200
        result = await c.post(
            "/search",
            json={"user_id": "owner", "query": "optical instrument", "top_k": top_k},
        )
        assert result.status_code == 200, result.text
        assert index.last_limit == 80 and delegate.limit == 4
        expected = [
            delegate.seen[i].fact for i in rank_fusion_order([3, 2, 1, 0])[:top_k]
        ]
        actual = [
            json.loads(r["content"])["source"]["text"] for r in result.json()["data"]
        ]
        assert actual == expected
        assert actual[0] == delegate.seen[0].fact  # not neural-only reversal
        assert "UNTRUSTED" not in result.text
    await host.close()
    index.db.close()


@pytest.mark.parametrize("original_policy", ["bge", "rank-fusion"])
async def test_rerank_policy_drift_refused_and_original_profile_reopens(
    tmp_path, original_policy
):
    index = Index(tmp_path / "index.sqlite3")
    delegate = ReversingRanker()

    def open_host(policy):
        ranker, identity = local_rerank_policy(
            delegate, {"model": "fixed"}, policy=policy
        )
        profile = hybrid_profile(
            semantic_index=index, writer=index, reranker=ranker, identity=identity
        )
        return SQLiteRawBackend(
            tmp_path / "service",
            namespace="hybrid-test",
            role_actors={"user": "owner", "assistant": "agent"},
            retrieval=profile,
        )

    host = open_host(original_policy)
    original_id = host.profile_id
    await host.close()
    with pytest.raises(ValueError, match="profile differs"):
        open_host("rank-fusion" if original_policy == "bge" else "bge")
    host = open_host(original_policy)
    assert host.profile_id == original_id
    await host.close()
    index.db.close()


async def test_fused_service_rejects_forged_delegate_payload_instead_of_fallback(
    tmp_path,
):
    index = Index(tmp_path / "index.sqlite3")
    ranker, identity = local_rerank_policy(Ranker(), {}, policy="rank-fusion")
    host = SQLiteRawBackend(
        tmp_path / "service",
        namespace="hybrid-test",
        role_actors={"user": "owner", "assistant": "agent"},
        retrieval=hybrid_profile(
            semantic_index=index, writer=index, reranker=ranker, identity=identity
        ),
    )
    async with client(host) as c:
        assert (await c.post("/add", json=payload())).status_code == 200
        result = await c.post(
            "/search", json={"user_id": "owner", "query": "telescope", "top_k": 20}
        )
        assert result.status_code == 500
        assert result.json() == {"error": "backend_failure"}
    await host.close()
    index.db.close()
