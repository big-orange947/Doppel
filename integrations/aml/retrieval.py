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
from urllib.parse import parse_qs, unquote, urlsplit

from doppel_memory.indexing import IndexWriter, memory_index_fingerprint
from doppel_memory.lexical import BM25RetrievalStrategy
from doppel_memory.models import MemoryRecord
from doppel_memory.rank_fusion import RankFusionReranker
from doppel_memory.retriever import Reranker, RetrievalStrategy
from doppel_memory.vector import HybridRetrievalStrategy, SemanticIndex
from integrations.aml.contract import WriteNotReady

LOCAL_RERANK_POLICIES = ("bge", "rank-fusion")


def local_rerank_policy(
    delegate: Reranker, identity: dict[str, Any], *, policy: str = "bge"
) -> tuple[Reranker, dict[str, Any]]:
    """Select a locked ordering policy; preserve the legacy BGE identity exactly."""
    if policy not in LOCAL_RERANK_POLICIES:
        raise ValueError("unsupported local rerank policy")
    bound = json.loads(json.dumps(identity, sort_keys=True, allow_nan=False))
    if policy == "bge":
        return delegate, bound
    return RankFusionReranker(delegate, rrf_k=60, max_candidates=80), {
        "policy": "retrieval-neural-rrf-v1",
        "rrf_k": 60,
        "retrieval_weight": 1,
        "neural_weight": 1,
        "tie_break": "retrieval-position",
        "max_candidates": 80,
        "delegate": bound,
    }


@dataclass(frozen=True)
class RawRetrievalProfile:
    identity: dict[str, Any]
    strategy: RetrievalStrategy
    prepare_records: Callable[[Sequence[MemoryRecord]], Awaitable[None]]
    reranker: Reranker
    candidate_limit: int = 80
    probe: Callable[[], Awaitable[None]] | None = None


def postgres_target_identity(dsn: str, schema: str) -> str:
    """Bind a single explicit DB target without persisting URI credentials.

    URI query overrides such as host/user/database must not bypass the profile
    binding. Only sslmode is accepted; password rotation does not change target.
    """
    try:
        target = urlsplit(dsn)
        query = parse_qs(target.query, keep_blank_values=True, strict_parsing=True)
        if (
            target.scheme not in {"postgres", "postgresql"}
            or not target.hostname
            or "," in target.hostname
            or not target.username
            or target.path in {"", "/"}
            or target.fragment
            or set(query) - {"sslmode"}
            or (
                "sslmode" in query
                and (
                    len(query["sslmode"]) != 1
                    or query["sslmode"][0]
                    not in {
                        "disable",
                        "allow",
                        "prefer",
                        "require",
                        "verify-ca",
                        "verify-full",
                    }
                )
            )
        ):
            raise ValueError()
        identity = [
            target.hostname,
            target.port or 5432,
            unquote(target.path),
            unquote(target.username),
            schema,
        ]
    except (ValueError, TypeError):
        raise ValueError(
            "explicit single-target PostgreSQL URI required; only sslmode query is supported"
        ) from None
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()


def hybrid_profile(
    *,
    semantic_index: SemanticIndex,
    writer: IndexWriter,
    reranker: Reranker,
    identity: dict[str, Any],
    index_batch: Callable[[Sequence[MemoryRecord]], Awaitable[None]] | None = None,
    probe: Callable[[], Awaitable[None]] | None = None,
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
        probe=probe,
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
    rerank_policy: str = "bge",
):
    """Create a PostgreSQL authority + pgvector service on one event loop.

    Uses existing model directories only. New dedicated schemas/tables may be
    created; existing schemas, sources, graph and index profiles are never reset.
    """
    if rerank_policy not in LOCAL_RERANK_POLICIES:
        raise ValueError("unsupported local rerank policy")

    from doppel_memory.postgres_store import PostgreSQLStore
    from doppel_memory.vector import PostgreSQLVectorIndex, VectorIndexConfig
    from integrations.aml.local_models import LocalCrossEncoder, LocalEmbedding
    from integrations.aml.service import SQLiteRawBackend

    target_id = postgres_target_identity(dsn, schema)
    embedding = LocalEmbedding(embedding_model_path)
    reranker = LocalCrossEncoder(reranker_model_path, device=reranker_device)
    ordering, ordering_identity = local_rerank_policy(
        reranker, reranker.identity, policy=rerank_policy
    )
    store = PostgreSQLStore(dsn, schema=schema, create_schema=True)
    backend = None
    try:
        index = PostgreSQLVectorIndex(store, embedding, VectorIndexConfig())

        async def index_batch(records):
            report = await index.index_records(records)
            if not report.ok:
                raise WriteNotReady("vector batch indexing failed")

        async def probe():
            if embedding._model is None or reranker._model is None:
                raise WriteNotReady("local models are not loaded")
            pool = await store._ensure_pool()
            async with pool.acquire() as connection:
                # No history scan, counts, embedding or neural scoring on probes.
                await connection.execute(
                    f"SELECT memory_id,scope_key,record_fingerprint,source_version,embedding FROM {index._table_sql} LIMIT 0"
                )
                stored = await connection.fetchval(
                    f"SELECT value FROM {store._meta_sql} WHERE key=$1",
                    f"vector_profile:{index.profile}",
                )
                if str(stored) != index._identity_json:
                    raise WriteNotReady("vector profile metadata differs")

        profile = hybrid_profile(
            semantic_index=index,
            writer=index,
            reranker=ordering,
            index_batch=index_batch,
            probe=probe,
            identity={
                "store_target": target_id,
                "embedding": embedding.identity,
                "reranker": ordering_identity,
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
