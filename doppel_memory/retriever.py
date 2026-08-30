"""Scope-guarded candidate retrieval and optional reranking."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from doppel_memory.models import (
    MemoryFilter,
    MemoryIsolationError,
    MemoryScope,
    RecallResult,
)
from doppel_memory.store import MemoryStore


@runtime_checkable
class RetrievalStrategy(Protocol):
    """Produces recall candidates; implementations may ignore the Store backend."""

    async def search(
        self,
        store: MemoryStore,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> Sequence[RecallResult]: ...


@runtime_checkable
class Reranker(Protocol):
    """Reorders or filters already scope-checked recall candidates."""

    async def rerank(
        self,
        query: str,
        candidates: Sequence[RecallResult],
        *,
        limit: int,
    ) -> Sequence[RecallResult]: ...


class StoreRetrievalStrategy:
    """Default candidate strategy backed by ``MemoryStore.search``."""

    async def search(
        self,
        store: MemoryStore,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> Sequence[RecallResult]:
        return await store.search(query, list(scopes), filters=filters, limit=limit)


class IdentityReranker:
    """Explicit no-op reranker useful for composition and tests."""

    async def rerank(
        self,
        query: str,
        candidates: Sequence[RecallResult],
        *,
        limit: int,
    ) -> Sequence[RecallResult]:
        return list(candidates)[:limit]


class Retriever:
    """Candidate/reordering coordinator with mandatory exact-scope guards."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        strategy: RetrievalStrategy | None = None,
        reranker: Reranker | None = None,
        candidate_multiplier: int = 4,
    ) -> None:
        self._store = store
        self._strategy = strategy or StoreRetrievalStrategy()
        self._reranker = reranker
        self._candidate_multiplier = max(1, candidate_multiplier)

    async def recall(
        self,
        query: str,
        scopes: list[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> list[RecallResult]:
        if not scopes:
            raise MemoryIsolationError(
                "recall requires explicit scopes (e.g. [conversation_scope, user_scope]); "
                "Doppel refuses unscoped search to prevent memory leaking across users/sessions."
            )
        if limit <= 0:
            return []

        candidate_limit = (
            limit * self._candidate_multiplier if self._reranker is not None else limit
        )
        candidates = await self._strategy.search(
            self._store,
            query,
            scopes,
            filters=filters,
            limit=candidate_limit,
        )
        guarded = _guard_and_deduplicate(candidates, scopes)
        if self._reranker is None:
            return guarded[:limit]

        reranked = await self._reranker.rerank(query, guarded, limit=limit)
        return _guard_and_deduplicate(reranked, scopes)[:limit]

    async def owner_style_samples(
        self, scope: MemoryScope, *, limit: int = 5
    ) -> list[str]:
        """Read the owner's latest exact-scope messages as style samples."""

        messages = await self._store.list_recent_owner_messages(scope, limit=limit)
        return [message.text for message in messages if message.text]


def _guard_and_deduplicate(
    candidates: Sequence[RecallResult], scopes: Sequence[MemoryScope]
) -> list[RecallResult]:
    allowed = {scope.scope_key for scope in scopes}
    seen: set[tuple[str, ...]] = set()
    guarded: list[RecallResult] = []
    for candidate in candidates:
        if candidate.scope is None or candidate.scope.scope_key not in allowed:
            continue
        identity = (
            ("id", candidate.scope.scope_key, candidate.memory_id)
            if candidate.memory_id
            else (
                "value",
                candidate.scope.scope_key,
                candidate.source_message_id,
                candidate.source_event_id,
                candidate.fact,
            )
        )
        if identity in seen:
            continue
        seen.add(identity)
        guarded.append(candidate)
    return guarded
