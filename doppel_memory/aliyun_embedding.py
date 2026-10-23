"""Explicit DashScope text-embedding-v4 provider; no SDK, retries or fallback."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from collections.abc import Sequence
from urllib.parse import urlsplit

import httpx

from doppel_memory.vector import EmbeddingProviderError

ALIYUN_EMBEDDING_DIMENSIONS = (64, 128, 256, 512, 768, 1024, 1536, 2048)


class AliyunEmbeddingError(EmbeddingProviderError):
    """Redacted failure; never expose remote bodies, histories or credentials."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _endpoint(base_url: str) -> str:
    try:
        url = urlsplit(base_url)
        host = url.hostname or ""
        workspace_host = re.fullmatch(
            r"[a-z0-9-]+\.(?:cn-beijing|cn-hongkong|ap-southeast-1)\.maas\.aliyuncs\.com",
            host,
        )
        if (
            url.scheme != "https"
            or not workspace_host
            or url.port not in {None, 443}
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or url.path.rstrip("/") != "/api/v1"
            or any(c.isspace() for c in base_url)
        ):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError(
            "explicit HTTPS DashScope workspace /api/v1 base URL required"
        ) from None
    return f"https://{host}/api/v1/services/embeddings/text-embedding/text-embedding"


class AliyunEmbedding:
    """Document/query-aware dense vectors, maximum ten unchanged texts/request.

    max_calls is a process-local attempt cap, not a durable cost/token budget.
    No cache, retry, instruction injection or input truncation. The service
    enforces the model's8192-token limit; this client does not guess token counts.
    Caller must own the instance and await aclose(). Construction makes no calls.
    """

    name = "aliyun:text-embedding-v4"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        dimensions: int = 2048,
        max_calls: int | None = None,
        timeout_seconds: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        endpoint = _endpoint(base_url)
        if not api_key or any(not 33 <= ord(c) <= 126 for c in api_key):
            raise ValueError("a nonempty visible ASCII DashScope key is required")
        if type(dimensions) is not int or dimensions not in ALIYUN_EMBEDDING_DIMENSIONS:
            raise ValueError("unsupported text-embedding-v4 dimensions")
        if max_calls is not None and (type(max_calls) is not int or max_calls < 1):
            raise ValueError("max_calls must be a positive integer or None")
        if (
            type(timeout_seconds) not in {int, float}
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 300
        ):
            raise ValueError("timeout_seconds must be finite in (0,300]")
        self.dimensions = dimensions
        self._contract = {
            "adapter": "dashscope-native-dense-v1",
            "model": "text-embedding-v4",
            "endpoint_sha256": hashlib.sha256(endpoint.encode()).hexdigest(),
            "dimensions": dimensions,
            "document_type": "document",
            "query_type": "query",
            "instruction": None,
            "normalization": "provider-output-unmodified",
        }
        self.version = hashlib.sha256(
            json.dumps(self._contract, sort_keys=True).encode()
        ).hexdigest()
        self._endpoint = endpoint
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        )
        self._lock = asyncio.Lock()
        self._max_calls = max_calls
        self._usage = {
            "attempts": 0,
            "completed": 0,
            "failed": 0,
            "total_tokens": 0,
            "missing_usage": 0,
        }
        self.verified = False

    @property
    def identity(self) -> dict:
        return {"name": self.name, "version": self.version, **self._contract}

    @property
    def usage(self) -> dict[str, int]:
        return dict(self._usage)

    @property
    def is_closed(self) -> bool:
        return self._client.is_closed

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return await self._embed(texts, text_type="document")

    async def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return await self._embed(texts, text_type="query")

    async def _embed(
        self, texts: Sequence[str], *, text_type: str
    ) -> list[list[float]]:
        if isinstance(texts, (str, bytes)):
            raise TypeError("embedding inputs must be a sequence of nonblank strings")
        bound = list(texts)
        if any(not isinstance(text, str) or not text.strip() for text in bound):
            raise ValueError("embedding inputs must be a sequence of nonblank strings")
        # Validate the entire call before sending any partial batch.
        try:
            for text in bound:
                text.encode("utf-8")
        except UnicodeError:
            raise ValueError("embedding input must be valid UTF-8 text") from None
        if self.is_closed:
            raise AliyunEmbeddingError("DashScope embedding client is closed")
        vectors = []
        for offset in range(0, len(bound), 10):
            batch = bound[offset : offset + 10]
            async with self._lock:
                if (
                    self._max_calls is not None
                    and self._usage["attempts"] >= self._max_calls
                ):
                    raise AliyunEmbeddingError(
                        "DashScope embedding attempt cap reached"
                    )
                self._usage["attempts"] += 1
            usage_recorded = False
            try:
                async with self._client.stream(
                    "POST",
                    self._endpoint,
                    json={
                        "model": "text-embedding-v4",
                        "input": {"texts": batch},
                        "parameters": {
                            "text_type": text_type,
                            "dimension": self.dimensions,
                            "output_type": "dense",
                        },
                    },
                ) as response:
                    if response.status_code != 200:
                        raise AliyunEmbeddingError(
                            f"DashScope embedding HTTP {response.status_code}",
                            status_code=response.status_code,
                        )
                    body = bytearray()
                    async for block in response.aiter_bytes(chunk_size=65536):
                        body.extend(block)
                        if len(body) > 2_000_000:
                            raise AliyunEmbeddingError(
                                "DashScope embedding response exceeds cap"
                            )
                    payload = json.loads(body)
                # Usage is recorded even when a successful HTTP body fails validation.
                usage = payload.get("usage") if isinstance(payload, dict) else None
                tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
                if type(tokens) is int and tokens >= 0:
                    self._usage["total_tokens"] += tokens
                    usage_recorded = True
                vectors.extend(self._vectors(payload, len(batch)))
                self._usage["completed"] += 1
                self.verified = True
            except asyncio.CancelledError:
                self._usage["failed"] += 1
                raise
            except AliyunEmbeddingError:
                self._usage["failed"] += 1
                raise
            except Exception:  # noqa: BLE001 - redact provider bodies and arbitrary transport errors
                self._usage["failed"] += 1
                raise AliyunEmbeddingError(
                    "DashScope embedding request or response failed"
                ) from None
            finally:
                if not usage_recorded:
                    self._usage["missing_usage"] += 1
        return vectors

    def _vectors(self, payload: object, count: int) -> list[list[float]]:
        if not isinstance(payload, dict) or payload.get("code") not in {None, ""}:
            raise ValueError()
        rows = payload["output"]["embeddings"]
        if not isinstance(rows, list) or len(rows) != count:
            raise ValueError()
        vectors: dict[int, list[float]] = {}
        for row in rows:
            index = row["text_index"]
            values = row["embedding"]
            if (
                type(index) is not int
                or not 0 <= index < count
                or index in vectors
                or not isinstance(values, list)
                or len(values) != self.dimensions
                or any(
                    type(v) not in {int, float} or not math.isfinite(v) for v in values
                )
                or not any(values)
            ):
                raise ValueError()
            vectors[index] = [float(value) for value in values]
        return [vectors[i] for i in range(count)]
