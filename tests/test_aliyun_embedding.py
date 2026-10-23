"""DashScope HTTP contract tests: MockTransport only, zero external calls."""

from __future__ import annotations

import asyncio
import copy
import json

import httpx
import pytest

from doppel_memory.aliyun_embedding import AliyunEmbedding, AliyunEmbeddingError
from doppel_memory.postgres_store import PostgreSQLStore
from doppel_memory.vector import (
    PostgreSQLVectorIndex,
    QueryEmbeddingProvider,
    VectorIndexConfig,
)

BASE = "https://workspace.cn-beijing.maas.aliyuncs.com/api/v1"
KEY = "synthetic-only-secret"


def payload(count=1, dimensions=64):
    return {
        "output": {
            "embeddings": [
                {"text_index": i, "embedding": [float(i + 1)] * dimensions}
                for i in reversed(range(count))
            ]
        },
        "usage": {"total_tokens": 17},
    }


def provider(handler, **kwargs):
    return AliyunEmbedding(
        api_key=KEY,
        base_url=BASE,
        dimensions=64,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


async def test_native_request_batches_order_and_asymmetric_queries():
    requests = []

    def handler(request):
        assert request.method == "POST"
        assert (
            str(request.url)
            == BASE + "/services/embeddings/text-embedding/text-embedding"
        )
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json=payload(len(body["input"]["texts"])))

    embedder = provider(handler)
    try:
        texts = [f"  original source {i}  " for i in range(23)]
        vectors = await embedder.embed(texts)
        assert [len(r["input"]["texts"]) for r in requests] == [10, 10, 3]
        assert [t for r in requests for t in r["input"]["texts"]] == texts
        assert [v[0] for v in vectors] == [float(i % 10 + 1) for i in range(23)]
        await embedder.embed_queries(["unmodified question"])
        assert requests[-1]["parameters"] == {
            "dimension": 64,
            "output_type": "dense",
            "text_type": "query",
        }
        assert requests[0]["parameters"]["text_type"] == "document"
        assert all(r["model"] == "text-embedding-v4" for r in requests)
        assert all("instruct" not in r["parameters"] for r in requests)
        assert isinstance(embedder, QueryEmbeddingProvider)
        assert embedder.verified
        assert embedder.usage == {
            "attempts": 4,
            "completed": 4,
            "failed": 0,
            "total_tokens": 68,
            "missing_usage": 0,
        }
        assert await embedder.embed([]) == []
        assert embedder.usage["attempts"] == 4
    finally:
        await embedder.aclose()


@pytest.mark.parametrize(
    "fault",
    [
        "dimension",
        "zero",
        "nan",
        "inf",
        "bool",
        "string",
        "duplicate",
        "missing",
        "foreign_index",
        "boolean_index",
        "missing_vector",
        "error_code",
        "not_object",
        "invalid_json",
    ],
)
async def test_invalid_responses_fail_without_partial_vectors_or_secret_leak(fault):
    body = payload(2)
    rows = body["output"]["embeddings"]
    if fault == "dimension":
        rows[0]["embedding"].pop()
    elif fault == "zero":
        rows[0]["embedding"] = [0] * 64
    elif fault in {"nan", "inf"}:
        rows[0]["embedding"][0] = float(fault)
    elif fault == "bool":
        rows[0]["embedding"][0] = True
    elif fault == "string":
        rows[0]["embedding"][0] = "0.1"
    elif fault == "duplicate":
        rows[1]["text_index"] = rows[0]["text_index"]
    elif fault == "missing":
        rows.pop()
    elif fault == "foreign_index":
        rows[0]["text_index"] = 99
    elif fault == "boolean_index":
        rows[0]["text_index"] = True
    elif fault == "missing_vector":
        rows[0].pop("embedding")
    elif fault == "error_code":
        body["code"] = KEY
    elif fault == "not_object":
        body = []
    encoded = f"malformed {KEY}" if fault == "invalid_json" else json.dumps(body)
    embedder = provider(lambda _: httpx.Response(200, text=encoded))
    try:
        with pytest.raises(AliyunEmbeddingError) as error:
            await embedder.embed(["PRIVATE_TEXT_1", "PRIVATE_TEXT_2"])
        assert KEY not in str(error.value) and "PRIVATE_TEXT" not in str(error.value)
        assert embedder.usage["attempts"] == embedder.usage["failed"] == 1
        assert embedder.usage["completed"] == 0
        assert not embedder.verified
        if fault not in {"not_object", "invalid_json"}:
            assert embedder.usage["total_tokens"] == 17  # no validation-failure refund
    finally:
        await embedder.aclose()


@pytest.mark.parametrize("status", [302, 400, 401, 429, 500])
async def test_http_errors_no_retry_redirect_or_private_body(status):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            status,
            text=f"PRIVATE_TEXT {KEY}",
            headers={"Location": "https://evil.invalid"},
        )

    embedder = provider(handler)
    try:
        with pytest.raises(AliyunEmbeddingError, match=f"HTTP {status}") as error:
            await embedder.embed(["PRIVATE_TEXT"])
        assert KEY not in str(error.value) and "PRIVATE_TEXT" not in str(error.value)
        assert len(seen) == 1 and embedder.usage["failed"] == 1
    finally:
        await embedder.aclose()


async def test_transport_exception_redacted_and_oversized_response_bounded():
    def broken(_):
        raise httpx.ConnectError(f"PRIVATE_TEXT {KEY}")

    for handler in (broken, lambda _: httpx.Response(200, content=b"x" * 2_000_001)):
        embedder = provider(handler)
        try:
            with pytest.raises(AliyunEmbeddingError) as error:
                await embedder.embed(["secret source"])
            assert KEY not in str(error.value) and "PRIVATE_TEXT" not in str(
                error.value
            )
            assert embedder.usage["attempts"] == embedder.usage["failed"] == 1
        finally:
            await embedder.aclose()


@pytest.mark.parametrize(
    "value", [["ok"] * 10 + [""], ["ok", 1], "not-a-sequence", ["bad\ud800"]]
)
async def test_all_inputs_validated_before_any_request(value):
    calls = []
    embedder = provider(lambda request: calls.append(request))
    try:
        with pytest.raises((ValueError, TypeError)):
            await embedder.embed(value)
        assert calls == [] and embedder.usage["attempts"] == 0
    finally:
        await embedder.aclose()


async def test_attempt_cap_is_atomic_and_counts_failed_http():
    seen = []

    async def handler(request):
        seen.append(request)
        await asyncio.sleep(0)
        return httpx.Response(500, text=KEY)

    embedder = provider(handler, max_calls=3)
    try:
        results = await asyncio.gather(
            *(embedder.embed(["input"]) for _ in range(10)), return_exceptions=True
        )
        assert all(isinstance(r, AliyunEmbeddingError) for r in results)
        assert len(seen) == embedder.usage["attempts"] == embedder.usage["failed"] == 3
        assert embedder.usage["completed"] == 0
    finally:
        await embedder.aclose()


async def test_identity_namespace_rotation_endpoint_and_dimensions():
    first = provider(lambda _: httpx.Response(200, json=payload()))
    rotated = AliyunEmbedding(api_key="rotated-key", base_url=BASE + "/", dimensions=64)
    largest = AliyunEmbedding(api_key=KEY, base_url=BASE)
    other = AliyunEmbedding(
        api_key=KEY,
        base_url=BASE.replace("cn-beijing", "ap-southeast-1"),
        dimensions=64,
    )
    try:
        assert first.identity == rotated.identity
        assert largest.dimensions == 2048
        assert first.version != other.version and first.version != largest.version
        assert KEY not in json.dumps(first.identity) and KEY not in repr(first)
        identity = first.identity
        identity["dimensions"] = 1
        assert first.identity["dimensions"] == 64
        store = PostgreSQLStore("unused", schema="synthetic")
        indexes = [PostgreSQLVectorIndex(store, e) for e in (first, other, largest)]
        assert len({i.identity for i in indexes}) == 3
        assert all(i._has_query_embedder for i in indexes)
        assert (
            not VectorIndexConfig().create_hnsw_index
        )  # 2048 exact path, not invalid vector HNSW
        await first.aclose()
        with pytest.raises(AliyunEmbeddingError, match="closed"):
            await first.embed(["closed source"])
    finally:
        for embedder in (first, rotated, largest, other):
            await embedder.aclose()


@pytest.mark.parametrize(
    "change",
    [
        {"dimensions": True},
        {"dimensions": 2000},
        {"dimensions": "2048"},
        {"max_calls": 0},
        {"max_calls": True},
        {"timeout_seconds": float("nan")},
        {"api_key": ""},
        {"api_key": "line\nbreak"},
        {"base_url": "http://workspace.cn-beijing.maas.aliyuncs.com/api/v1"},
        {"base_url": "https://evil.invalid/api/v1"},
        {"base_url": BASE + "?key=secret"},
        {"base_url": BASE + "#secret"},
        {"base_url": BASE.replace("https://", "https://key@")},
        {"base_url": BASE.replace(".com", ".com.evil.invalid")},
        {"base_url": BASE.replace("/api/v1", "/compatible-mode/v1")},
    ],
)
def test_invalid_configuration_rejected_before_client_or_network(change):
    with pytest.raises(ValueError):
        AliyunEmbedding(**{"api_key": KEY, "base_url": BASE, **change})


@pytest.mark.parametrize(
    "usage", [None, {}, {"total_tokens": True}, {"total_tokens": "17"}]
)
async def test_missing_or_invalid_usage_remains_visible_without_fabricating_tokens(
    usage,
):
    response = copy.deepcopy(payload())
    response["usage"] = usage
    embedder = provider(lambda _: httpx.Response(200, json=response))
    try:
        assert len(await embedder.embed(["a"])) == 1
        assert embedder.usage["missing_usage"] == 1
        assert embedder.usage["total_tokens"] == 0
    finally:
        await embedder.aclose()
