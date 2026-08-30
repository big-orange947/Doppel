"""Provider contracts and hybrid retrieval without a PostgreSQL server."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from doppel_memory import (
    ChatMessage,
    IndexWriter,
    InMemoryStore,
    MemoryScope,
    RecallResult,
    Retriever,
)
from doppel_memory.vector import (
    CompositeRecallResult,
    CompositeSemanticIndex,
    EmbeddingProviderError,
    HybridRetrievalStrategy,
    PostgreSQLVectorIndex,
    SemanticIndexUnavailableError,
    VectorIndexConfig,
    VectorIndexFailure,
    VectorIndexReport,
    VectorIndexUnavailableError,
)

SCOPE = MemoryScope(user_id="vector-unit", agent_id="bot")
OTHER_SCOPE = MemoryScope(user_id="vector-unit-other", agent_id="bot")


class TinyProvider:
    name = "tests.tiny"
    version = "1"
    dimensions = 3

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


class FakeSemanticIndex:
    def __init__(self, results=None, error: Exception | None = None) -> None:
        self.results = list(results or [])
        self.error = error

    async def search(self, query, scopes, *, filters=None, limit=10):
        if self.error is not None:
            raise self.error
        return self.results[:limit]


class FakeTemporalSemanticIndex(FakeSemanticIndex):
    def __init__(self, results=None, error: Exception | None = None) -> None:
        super().__init__(results, error)
        self.search_calls = 0
        self.search_at_calls = []

    async def search(self, query, scopes, *, filters=None, limit=10):
        self.search_calls += 1
        return await super().search(
            query, scopes, filters=filters, limit=limit
        )

    async def search_at(
        self, query, scopes, *, valid_at, filters=None, limit=10
    ):
        self.search_at_calls.append(valid_at)
        return await super().search(
            query, scopes, filters=filters, limit=limit
        )


def _recall(memory_id: str, fact: str, scope: MemoryScope = SCOPE) -> RecallResult:
    return RecallResult(memory_id=memory_id, fact=fact, scope=scope)


@pytest.mark.parametrize(
    ("provider", "error", "message"),
    [
        (
            type("P", (), {"name": "", "version": "1", "dimensions": 3})(),
            ValueError,
            "name",
        ),
        (
            type("P", (), {"name": "p", "version": "", "dimensions": 3})(),
            ValueError,
            "version",
        ),
        (
            type("P", (), {"name": "p", "version": "1", "dimensions": True})(),
            TypeError,
            "integer",
        ),
        (
            type("P", (), {"name": "p", "version": "1", "dimensions": 0})(),
            ValueError,
            "between",
        ),
    ],
)
def test_vector_index_rejects_unstable_provider_identity(
    provider, error, message
) -> None:
    from doppel_memory import PostgreSQLStore

    with pytest.raises(error, match=message):
        PostgreSQLVectorIndex(PostgreSQLStore("postgresql://unused"), provider)


def test_hnsw_dimension_limit_is_explicit() -> None:
    from doppel_memory import PostgreSQLStore

    provider = type(
        "WideProvider",
        (),
        {"name": "wide", "version": "1", "dimensions": 3072},
    )()
    index = PostgreSQLVectorIndex(PostgreSQLStore("postgresql://unused"), provider)
    assert index.dimensions == 3072
    with pytest.raises(ValueError, match="at most 2000"):
        PostgreSQLVectorIndex(
            PostgreSQLStore("postgresql://unused"),
            provider,
            VectorIndexConfig(create_hnsw_index=True),
        )


def test_profile_identity_and_vector_validation_are_deterministic() -> None:
    from doppel_memory import PostgreSQLStore

    first = PostgreSQLVectorIndex(
        PostgreSQLStore("postgresql://unused"), TinyProvider()
    )
    second = PostgreSQLVectorIndex(
        PostgreSQLStore("postgresql://unused"), TinyProvider()
    )
    changed = type(
        "ChangedProvider",
        (),
        {"name": "tests.tiny", "version": "2", "dimensions": 3},
    )()
    third = PostgreSQLVectorIndex(PostgreSQLStore("postgresql://unused"), changed)
    assert isinstance(first, IndexWriter)
    assert first.profile == second.profile
    assert first.profile != third.profile
    assert first._validate_vector([1, 0, 0]) == [1.0, 0.0, 0.0]
    with pytest.raises(EmbeddingProviderError, match="declared 3"):
        first._validate_vector([1, 0])
    with pytest.raises(EmbeddingProviderError, match="finite"):
        first._validate_vector([1, float("nan"), 0])
    with pytest.raises(EmbeddingProviderError, match="non-zero"):
        first._validate_vector([0, 0, 0])


def test_vector_report_rejects_inconsistent_counts() -> None:
    with pytest.raises(ValueError, match="counts"):
        VectorIndexReport(
            profile="p",
            attempted=2,
            indexed=1,
            skipped=0,
            failed=0,
        )
    with pytest.raises(ValueError, match="failures"):
        VectorIndexReport(
            profile="p",
            attempted=1,
            indexed=0,
            skipped=0,
            failed=1,
            failures=[],
        )
    report = VectorIndexReport(
        profile="p",
        attempted=1,
        indexed=0,
        skipped=0,
        failed=1,
        failures=[
            VectorIndexFailure(
                memory_id="m", stage="embed", error_type="Error", message="failed"
            )
        ],
    )
    assert not report.ok


async def test_hybrid_rrf_fuses_ranks_and_drops_scope_leaks() -> None:
    store = InMemoryStore()
    older = await store.write_event(
        SCOPE,
        ChatMessage.of("owner", "literal older", "2026-01-01T00:00:00Z", event_id="a"),
    )
    common = await store.write_event(
        SCOPE,
        ChatMessage.of("owner", "literal common", "2026-01-02T00:00:00Z", event_id="c"),
    )
    semantic_only = _recall("semantic", "conceptually related")
    strategy = HybridRetrievalStrategy(
        FakeSemanticIndex(
            [
                _recall(common.memory_id, "literal common"),
                semantic_only,
                _recall("leak", "forbidden", OTHER_SCOPE),
            ]
        ),
        rrf_k=10,
    )
    hits = await Retriever(store, strategy=strategy).recall("literal", [SCOPE], limit=5)

    assert hits[0].memory_id == common.memory_id
    assert {hit.memory_id for hit in hits[1:]} == {
        older.memory_id,
        semantic_only.memory_id,
    }
    assert hits[0].similarity == 1.0
    assert all(0 < hit.similarity <= 1 for hit in hits)
    assert "leak" not in {hit.memory_id for hit in hits}


@pytest.mark.parametrize(
    "error",
    [
        EmbeddingProviderError("offline"),
        VectorIndexUnavailableError("missing"),
        SemanticIndexUnavailableError("unsupported semantic request"),
    ],
)
async def test_hybrid_can_degrade_to_lexical_for_known_semantic_failures(error) -> None:
    store = InMemoryStore()
    created = await store.write_event(
        SCOPE,
        ChatMessage.of(
            "owner", "literal fallback", "2026-01-01T00:00:00Z", event_id="f"
        ),
    )
    strategy = HybridRetrievalStrategy(FakeSemanticIndex(error=error))
    hits = await Retriever(store, strategy=strategy).recall(
        "literal fallback", [SCOPE], limit=3
    )
    assert [hit.memory_id for hit in hits] == [created.memory_id]


async def test_hybrid_does_not_hide_unexpected_database_errors() -> None:
    strategy = HybridRetrievalStrategy(FakeSemanticIndex(error=RuntimeError("db down")))
    with pytest.raises(RuntimeError, match="db down"):
        await strategy.search(InMemoryStore(), "query", [SCOPE])


async def test_composite_semantic_index_fuses_sources_and_explains_contributions() -> (
    None
):
    common = _recall("common", "shared candidate")
    common.similarity = 0.8
    vector_only = _recall("vector-only", "vector candidate")
    vector_only.similarity = 0.9
    graph_only = _recall("graph-only", "graph candidate")
    graph_only.similarity = 0.7
    index = CompositeSemanticIndex(
        {
            "vector": FakeSemanticIndex([common, vector_only]),
            "graph": FakeSemanticIndex(
                [graph_only, common, _recall("leak", "forbidden", OTHER_SCOPE)]
            ),
        },
        rrf_k=10,
    )

    hits = await index.search("query", [SCOPE], limit=5)

    assert [hit.memory_id for hit in hits] == [
        "common",
        "graph-only",
        "vector-only",
    ]
    assert all(isinstance(hit, CompositeRecallResult) for hit in hits)
    common_hit = hits[0]
    assert [item.source for item in common_hit.contributions] == ["vector", "graph"]
    assert [item.rank for item in common_hit.contributions] == [1, 2]
    assert 0 < common_hit.similarity <= 1
    assert "leak" not in {hit.memory_id for hit in hits}


async def test_composite_semantic_index_degrades_per_source_but_not_on_total_failure() -> (
    None
):
    available = FakeSemanticIndex([_recall("available", "available")])
    partial = CompositeSemanticIndex(
        {
            "vector": available,
            "graph": FakeSemanticIndex(
                error=SemanticIndexUnavailableError("offline")
            ),
        },
        rrf_k=10,
    )

    hits = await partial.search("query", [SCOPE])
    assert [hit.memory_id for hit in hits] == ["available"]
    assert hits[0].similarity == 1
    assert [item.source for item in hits[0].contributions] == ["vector"]

    unavailable = CompositeSemanticIndex(
        {
            "vector": FakeSemanticIndex(error=EmbeddingProviderError("offline")),
            "graph": FakeSemanticIndex(
                error=SemanticIndexUnavailableError("offline")
            ),
        }
    )
    with pytest.raises(SemanticIndexUnavailableError, match="all composite"):
        await unavailable.search("query", [SCOPE])

    unexpected = CompositeSemanticIndex(
        {
            "vector": available,
            "graph": FakeSemanticIndex(error=RuntimeError("database corruption")),
        }
    )
    with pytest.raises(RuntimeError, match="database corruption"):
        await unexpected.search("query", [SCOPE])


@pytest.mark.parametrize(
    ("indexes", "weights", "message"),
    [
        ({}, None, "at least one source"),
        ({"Graph Source": FakeSemanticIndex()}, None, "source names"),
        ({"vector": FakeSemanticIndex()}, {"graph": 1.0}, "unknown"),
        ({"vector": FakeSemanticIndex()}, {"vector": -1.0}, "non-negative"),
        ({"vector": FakeSemanticIndex()}, {"vector": 0.0}, "must be positive"),
    ],
)
def test_composite_semantic_index_rejects_ambiguous_configuration(
    indexes, weights, message
) -> None:
    with pytest.raises(ValueError, match=message):
        CompositeSemanticIndex(indexes, weights=weights)


async def test_composite_semantic_index_forwards_time_only_to_temporal_sources() -> (
    None
):
    from datetime import UTC, datetime

    temporal = FakeTemporalSemanticIndex([_recall("graph", "graph")])
    vector = FakeSemanticIndex([_recall("vector", "vector")])
    index = CompositeSemanticIndex({"vector": vector, "graph": temporal})
    valid_at = datetime(2026, 8, 30, tzinfo=UTC)

    await index.search_at("query", [SCOPE], valid_at=valid_at)

    assert temporal.search_calls == 0
    assert temporal.search_at_calls == [valid_at]


async def test_retriever_keeps_same_memory_id_in_two_authorized_scopes() -> None:
    class SameIdStrategy:
        async def search(self, store, query, scopes, *, filters=None, limit=10):
            del store, query, filters, limit
            return [
                _recall("shared-id", "first", scopes[0]),
                _recall("shared-id", "second", scopes[1]),
            ]

    hits = await Retriever(
        InMemoryStore(), strategy=SameIdStrategy()
    ).recall("query", [SCOPE, OTHER_SCOPE], limit=2)

    assert [(hit.scope.scope_key, hit.fact) for hit in hits if hit.scope] == [
        (SCOPE.scope_key, "first"),
        (OTHER_SCOPE.scope_key, "second"),
    ]
