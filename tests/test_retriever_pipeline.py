"""Retrieval strategy, reranker, and post-extension scope guards."""

from __future__ import annotations

from collections.abc import Sequence

from doppel_memory import InMemoryStore, MemoryScope, RecallResult, Retriever

SCOPE = MemoryScope(user_id="u1", agent_id="bot")
OTHER_SCOPE = MemoryScope(user_id="u2", agent_id="bot")


class RecordingStrategy:
    def __init__(self) -> None:
        self.limit = 0

    async def search(
        self, store, query, scopes, *, filters=None, limit=10
    ) -> Sequence[RecallResult]:
        self.limit = limit
        return [
            RecallResult(
                memory_id="low", fact="low score", scope=SCOPE, similarity=0.1
            ),
            RecallResult(
                memory_id="high", fact="high score", scope=SCOPE, similarity=0.9
            ),
        ]


class ScoreReranker:
    async def rerank(
        self, query: str, candidates: Sequence[RecallResult], *, limit: int
    ) -> Sequence[RecallResult]:
        return sorted(candidates, key=lambda item: item.similarity, reverse=True)[
            :limit
        ]


async def test_retriever_overfetches_candidates_for_reranker() -> None:
    strategy = RecordingStrategy()
    retriever = Retriever(
        InMemoryStore(),
        strategy=strategy,
        reranker=ScoreReranker(),
        candidate_multiplier=5,
    )
    results = await retriever.recall("score", [SCOPE], limit=2)
    assert strategy.limit == 10
    assert [item.memory_id for item in results] == ["high", "low"]


class LeakingStrategy:
    async def search(
        self, store, query, scopes, *, filters=None, limit=10
    ) -> Sequence[RecallResult]:
        return [
            RecallResult(memory_id="allowed", fact="safe", scope=SCOPE),
            RecallResult(memory_id="leaked", fact="unsafe", scope=OTHER_SCOPE),
            RecallResult(memory_id="unknown", fact="unknown", scope=None),
        ]


class LeakingReranker:
    async def rerank(
        self, query: str, candidates: Sequence[RecallResult], *, limit: int
    ) -> Sequence[RecallResult]:
        return [
            RecallResult(memory_id="injected", fact="unsafe", scope=OTHER_SCOPE),
            *candidates,
        ]


async def test_scope_guard_runs_before_and_after_extensions() -> None:
    retriever = Retriever(
        InMemoryStore(), strategy=LeakingStrategy(), reranker=LeakingReranker()
    )
    results = await retriever.recall("safe", [SCOPE])
    assert [item.memory_id for item in results] == ["allowed"]


class DuplicateStrategy:
    async def search(
        self, store, query, scopes, *, filters=None, limit=10
    ) -> Sequence[RecallResult]:
        item = RecallResult(memory_id="same", fact="same", scope=SCOPE)
        return [item, item.model_copy(deep=True)]


async def test_retriever_deduplicates_strategy_results() -> None:
    results = await Retriever(InMemoryStore(), strategy=DuplicateStrategy()).recall(
        "same", [SCOPE]
    )
    assert [item.memory_id for item in results] == ["same"]
