"""Real pgvector indexing, search, lifecycle, backfill, and fallback tests."""

from __future__ import annotations

import os
from collections.abc import Sequence
from uuid import uuid4

import pytest

from doppel_memory import (
    ChatMessage,
    HybridRetrievalStrategy,
    IndexMaintainer,
    IndexOperationStatus,
    IndexWriter,
    MemoryFilter,
    MemoryKind,
    MemoryScope,
    PostgreSQLStore,
    PostgreSQLVectorIndex,
    Retriever,
    VectorIndexConfig,
)

POSTGRES_DSN = os.environ.get("DOPPEL_TEST_POSTGRES_DSN", "")

pytestmark = pytest.mark.skipif(
    not POSTGRES_DSN,
    reason="DOPPEL_TEST_POSTGRES_DSN is not configured",
)


class KeywordProvider:
    name = "tests.keyword-concepts"
    version = "1"
    dimensions = 3

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [self._one(text) for text in texts]

    @staticmethod
    def _one(text: str) -> list[float]:
        lowered = text.lower()
        if any(word in lowered for word in ("mountain", "hiking", "trail", "walk")):
            return [1.0, 0.05, 0.05]
        if any(word in lowered for word in ("python", "debug", "software", "bug")):
            return [0.05, 1.0, 0.05]
        if any(word in lowered for word in ("pasta", "recipe", "cook", "dinner")):
            return [0.05, 0.05, 1.0]
        return [0.33, 0.33, 0.33]


class FailingKeywordProvider(KeywordProvider):
    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        raise TimeoutError("embedding service unavailable")


def _scope(label: str) -> MemoryScope:
    return MemoryScope(
        user_id=f"vector-{label}-{uuid4().hex}",
        agent_id="bot",
        platform="test",
        chat_type="private",
        chat_id=label,
    )


def _index(store: PostgreSQLStore, provider=None) -> PostgreSQLVectorIndex:
    return PostgreSQLVectorIndex(
        store,
        provider or KeywordProvider(),
        VectorIndexConfig(create_extension=True, create_hnsw_index=True),
    )


async def test_semantic_search_is_exact_scope_filtered_and_observable() -> None:
    store = PostgreSQLStore(POSTGRES_DSN, min_pool_size=0, max_pool_size=4)
    index = _index(store)
    scope = _scope("semantic")
    other = _scope("other")
    hiking = await store.write_background(
        scope, "Mountain hiking plans", tags=["outdoor"]
    )
    await store.write_background(scope, "Python debugging checklist", tags=["tech"])
    forbidden = await store.write_background(
        other, "Mountain hiking plans", tags=["outdoor"]
    )
    assert hiking.record is not None
    assert forbidden.record is not None

    report = await index.index_records([hiking.record, forbidden.record])
    assert report.ok and report.indexed == 2
    repeated = await index.index_record(hiking.record)
    assert repeated.ok and repeated.skipped == 1

    hits = await index.search(
        "a quiet trail walk",
        [scope],
        filters=MemoryFilter(kinds={MemoryKind.BACKGROUND}, tags={"outdoor"}),
    )
    assert [hit.memory_id for hit in hits] == [hiking.memory_id]
    assert hits[0].scope == scope
    assert hits[0].similarity > 0.9
    assert forbidden.memory_id not in {hit.memory_id for hit in hits}

    health = await index.health()
    assert health["ok"] is True
    assert health["backend"] == "pgvector"
    assert health["extension_version"]
    assert health["profile"] == index.profile
    assert health["create_hnsw_index"] is True
    await store.close()


async def test_paginated_backfill_indexes_existing_core_records() -> None:
    store = PostgreSQLStore(POSTGRES_DSN, min_pool_size=0, max_pool_size=4)
    index = _index(store)
    scope = _scope("backfill")
    for event_id, text in (
        ("one", "Mountain hiking notes"),
        ("two", "Python software notes"),
        ("three", "Pasta dinner notes"),
    ):
        await store.write_event(
            scope,
            ChatMessage.of(
                "owner",
                text,
                f"2026-01-0{len(event_id)}T00:00:00Z",
                event_id=f"{scope.user_id}-{event_id}",
            ),
        )

    first = await index.backfill(scope, page_size=2)
    assert first.report.indexed == 2
    assert first.has_more
    second = await index.backfill(scope, cursor=first.next_cursor, page_size=2)
    assert second.report.indexed == 1
    assert not second.has_more
    hits = await index.search("software bug", [scope])
    assert len(hits) == 3
    assert hits[0].fact == "Python software notes"
    await store.close()


async def test_hard_delete_cascades_vector_and_hybrid_fallback_is_explicit() -> None:
    store = PostgreSQLStore(POSTGRES_DSN, min_pool_size=0, max_pool_size=4)
    scope = _scope("lifecycle")
    created = await store.write_event(
        scope,
        ChatMessage.of(
            "owner",
            "literal fallback mountain hiking",
            "2026-01-01T00:00:00Z",
            event_id=f"{scope.user_id}-lifecycle",
        ),
    )
    working = _index(store)
    assert created.record is not None
    assert (await working.index_record(created.record)).ok

    failing = _index(store, FailingKeywordProvider())
    strategy = HybridRetrievalStrategy(failing, fallback_to_lexical=True)
    hits = await Retriever(store, strategy=strategy).recall(
        "literal fallback", [scope], limit=3
    )
    assert [hit.memory_id for hit in hits] == [created.memory_id]

    assert await store.forget(scope, created.memory_id, hard=True)
    assert await working.search("trail walk", [scope]) == []
    assert await working.inspect(scope, created.memory_id) is None
    await store.close()


async def test_vector_index_writer_reconciles_authoritative_lifecycle() -> None:
    store = PostgreSQLStore(POSTGRES_DSN, min_pool_size=0, max_pool_size=4)
    index = _index(store)
    assert isinstance(index, IndexWriter)
    scope = _scope("maintenance")
    active = await store.write_background(scope, "Mountain hiking plan")
    inactive = await store.write_background(scope, "Old pasta plan")
    assert active.record is not None
    assert inactive.record is not None
    first_write = await index.upsert(inactive.record)
    assert first_write.status == IndexOperationStatus.INDEXED
    assert await store.forget(scope, inactive.memory_id)

    maintainer = IndexMaintainer(store, index)
    records = await maintainer.reconcile(scope, page_size=10)
    assert records.ok
    assert records.indexed == 1
    assert records.deleted == 1
    assert records.committable_checkpoint is not None
    entries = await maintainer.reconcile(
        scope,
        checkpoint=records.committable_checkpoint,
        page_size=10,
    )
    assert entries.ok and entries.complete
    assert await index.inspect(scope, active.memory_id) is not None
    assert await index.inspect(scope, inactive.memory_id) is None
    await store.close()
