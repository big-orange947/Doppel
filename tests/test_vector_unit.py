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
