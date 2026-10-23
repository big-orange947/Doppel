"""Explicit raw-history service composition, with durable vector readiness.

No benchmark imports, eager LLM extraction, implicit fallback or graph building.
This local-model profile is not an AML academic-model compliance claim.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from doppel_memory.indexing import IndexWriter, memory_index_fingerprint
from doppel_memory.lexical import BM25RetrievalStrategy
from doppel_memory.models import MemoryRecord
from doppel_memory.retriever import Reranker, RetrievalStrategy
from doppel_memory.vector import HybridRetrievalStrategy, SemanticIndex
from integrations.aml.contract import WriteNotReady


@dataclass(frozen=True)
class RawRetrievalProfile:
    identity: dict[str, Any]
    strategy: RetrievalStrategy
    prepare_records: Callable[[Sequence[MemoryRecord]], Awaitable[None]]
    reranker: Reranker
    candidate_limit: int = 80


def hybrid_profile(
    *,
    semantic_index: SemanticIndex,
    writer: IndexWriter,
    reranker: Reranker,
    identity: dict[str, Any],
    index_batch: Callable[[Sequence[MemoryRecord]], Awaitable[None]] | None = None,
) -> RawRetrievalProfile:
    """Re-use production RRF and Store guards, never fall back on index failure."""
    # Snapshot caller metadata before it is bound to the journal.
    bound_identity = json.loads(json.dumps(identity, sort_keys=True, allow_nan=False))
    bound_identity.update(
        strategy="bm25-vector-rrf60-reranked-v1",
        candidates=80,
        lexical_weight=1,
        semantic_weight=1,
        index_identity=writer.identity,
    )

    async def prepare(records: Sequence[MemoryRecord]) -> None:
        if index_batch is not None:
            await index_batch(records)
        else:
            for record in records:
                await writer.upsert(record)
        for record in records:
            entry = await writer.inspect(record.scope, record.memory_id)
            if entry is None or (
                entry.memory_id != record.memory_id
                or entry.scope_key != record.scope.scope_key
                or entry.source_version != record.version
                or entry.fingerprint != memory_index_fingerprint(record)
            ):
                raise WriteNotReady("hybrid index not ready for authoritative source")

    return RawRetrievalProfile(
        identity=bound_identity,
        strategy=HybridRetrievalStrategy(
            semantic_index,
            lexical_strategy=BM25RetrievalStrategy(),
            candidate_multiplier=1,
            fallback_to_lexical=False,
        ),
        prepare_records=prepare,
        reranker=reranker,
    )


async def create_local_hybrid_backend(
    directory: Path,
    *,
    namespace: str,
    dsn: str,
    schema: str,
    embedding_model_path: Path,
    reranker_model_path: Path,
    reranker_device: str = "cpu",
):
    """Create a PostgreSQL authority + pgvector service on one event loop.

    Uses existing model directories only. New dedicated schemas/tables may be
    created; existing schemas, sources, graph and index profiles are never reset.
    """
    from doppel_memory.postgres_store import PostgreSQLStore
    from doppel_memory.vector import PostgreSQLVectorIndex, VectorIndexConfig
    from integrations.aml.local_models import LocalCrossEncoder, LocalEmbedding
    from integrations.aml.service import SQLiteRawBackend

    target = urlsplit(dsn)
    if target.scheme not in {"postgres", "postgresql"} or not target.hostname:
        raise ValueError("a PostgreSQL URI is required")
    # Passwords/URI query parameters never enter the persistent profile.
    target_id = hashlib.sha256(
        json.dumps(
            [
                target.hostname,
                target.port or 5432,
                target.path,
                target.username,
                schema,
            ]
        ).encode()
    ).hexdigest()
    embedding = LocalEmbedding(embedding_model_path)
    reranker = LocalCrossEncoder(reranker_model_path, device=reranker_device)
    store = PostgreSQLStore(dsn, schema=schema, create_schema=True)
    backend = None
    try:
        index = PostgreSQLVectorIndex(store, embedding, VectorIndexConfig())

        async def index_batch(records):
            report = await index.index_records(records)
            if not report.ok:
                raise WriteNotReady("vector batch indexing failed")

        profile = hybrid_profile(
            semantic_index=index,
            writer=index,
            reranker=reranker,
            index_batch=index_batch,
            identity={
                "store_target": target_id,
                "embedding": embedding.identity,
                "reranker": reranker.identity,
            },
        )
        backend = SQLiteRawBackend(
            directory,
            namespace=namespace,
            role_actors={"user": "owner", "assistant": "agent"},
            store=store,
            retrieval=profile,
        )
        # Provision pgvector separately; startup must fail if it is unavailable.
        await index.initialize()
        await embedding.embed(["service model readiness"])
        await reranker.warmup()
        return backend
    except BaseException:
        if backend is not None:
            await backend.close()
        else:
            await store.close()
        raise
