"""Explicit two-request DashScope canary; no DB, GPU, QA or provider retry."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import httpx

from doppel_memory.aliyun_embedding import (
    ALIYUN_EMBEDDING_DIMENSIONS,
    AliyunEmbedding,
    AliyunEmbeddingError,
)


async def run_smoke(
    *,
    api_key: str,
    base_url: str,
    dimensions: int = 2048,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict:
    # Construction validates configuration without sending any request.
    provider = AliyunEmbedding(
        api_key=api_key,
        base_url=base_url,
        dimensions=dimensions,
        max_calls=2,
        transport=transport,
    )
    report = {
        "runner": "doppel.aliyun-embedding-smoke.v1",
        "passed": False,
        "provider": provider.identity,
        "attempt_cap": 2,
        "retry_enabled": False,
        "database_writes": 0,
        "quality_score_available": False,
    }
    try:
        documents = await provider.embed(
            ["A telescope is an optical instrument.", "望远镜是一种光学仪器。"]
        )
        queries = await provider.embed_queries(["optical instrument", "光学仪器"])
        report.update(
            passed=True,
            document_vectors=len(documents),
            query_vectors=len(queries),
            dimensions=provider.dimensions,
        )
    except Exception as exc:  # noqa: BLE001 - never persist arbitrary source/credential exception text
        report["error_type"] = type(exc).__name__
        if (
            isinstance(exc, AliyunEmbeddingError)
            and type(exc.status_code) is int
            and 100 <= exc.status_code <= 599
        ):
            report["http_status"] = exc.status_code
    finally:
        report["usage"] = provider.usage
        await provider.aclose()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--dimensions", type=int, choices=ALIYUN_EMBEDDING_DIMENSIONS, default=2048
    )
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required; no provider credentials or network accessed")
    if args.output.exists():
        parser.error("output already exists; use a new path, no overwrite/resume")
    key = os.environ.get("DASHSCOPE_API_KEY", "")
    url = os.environ.get("DOPPEL_ALIYUN_BASE_URL", "")
    if not key or not url:
        parser.error("DASHSCOPE_API_KEY and DOPPEL_ALIYUN_BASE_URL must be set")
    try:
        report = asyncio.run(
            run_smoke(api_key=key, base_url=url, dimensions=args.dimensions)
        )
    except ValueError:
        parser.error("invalid DashScope workspace URL or key configuration")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
