"""General lexical maths/normalization/isolation; no benchmark-specific queries."""

from __future__ import annotations

import math

import pytest

from doppel_memory.in_memory_store import InMemoryStore
from doppel_memory.lexical import (
    BM25Config,
    BM25ReadLimitError,
    BM25RetrievalStrategy,
    lexical_tokens,
)
from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryFilter,
    MemoryIsolationError,
    MemoryPage,
    MemoryRecord,
    MemoryScope,
    MemoryState,
)

SCOPE = MemoryScope(user_id="a", agent_id="agent")
OTHER = MemoryScope(user_id="b", agent_id="agent")


async def put(store, content, identity="one", scope=SCOPE, **kwargs):
    result = await store.put(
        MemoryRecord(memory_id=identity, scope=scope, content=content, **kwargs)
    )
    return result.record


def test_generic_unicode_tokens_without_aliases_or_substring_matching() -> None:
    assert lexical_tokens("ＦＯＯ_bar, 2026") == ["w:foo", "w:bar", "w:2026"]
    assert lexical_tokens("上海 Beijing") == ["h:上", "h:海", "h:上海", "w:beijing"]
    assert lexical_tokens("HE") != lexical_tokens("she")
    assert lexical_tokens("!?,") == []


@pytest.mark.asyncio
async def test_exact_bm25_formula_and_query_repetition() -> None:
    store = InMemoryStore()
    await put(store, "red red blue")
    await put(store, "blue green", "two")
    strategy = BM25RetrievalStrategy()
    hits = await strategy.search(store, "RED", [SCOPE])
    score = math.log1p(1.5 / 1.5) * 2 * 2.2 / (2 + 1.2 * (0.25 + 0.75 * 3 / 2.5))
    assert len(hits) == 1 and hits[0].memory_id == "one"
    assert hits[0].similarity == pytest.approx(score / (1 + score))
    assert await strategy.search(store, "red red", [SCOPE]) == hits
    assert not await strategy.search(store, "missing-token", [SCOPE])


@pytest.mark.asyncio
async def test_other_scopes_cannot_change_term_frequencies_or_scores() -> None:
    store = InMemoryStore()
    await put(store, "rare term")
    await put(store, "common words", "two")
    strategy = BM25RetrievalStrategy()
    before = await strategy.search(store, "rare", [SCOPE])
    for i in range(10):
        await put(store, "rare rare rare", f"other-{i}", OTHER)
    assert await strategy.search(store, "rare", [SCOPE, SCOPE]) == before
    hits = await strategy.search(store, "rare", [SCOPE, OTHER], limit=20)
    assert (
        next(hit.similarity for hit in hits if hit.memory_id == "one")
        == before[0].similarity
    )


@pytest.mark.asyncio
async def test_pages_limits_and_no_silent_partial_results() -> None:
    store = InMemoryStore()
    for i in range(3):
        await put(store, "matching text", f"record-{i}")
    complete = BM25RetrievalStrategy(BM25Config(page_size=1))
    assert len(await complete.search(store, "matching", [SCOPE])) == 3
    for config in [
        BM25Config(page_size=1, max_pages_per_scope=2),
        BM25Config(page_size=1, max_records_per_scope=2),
    ]:
        with pytest.raises(BM25ReadLimitError):
            await BM25RetrievalStrategy(config).search(store, "matching", [SCOPE])


@pytest.mark.asyncio
async def test_filters_reapplied_even_if_custom_store_ignores_them() -> None:
    class UnfilteredStore(InMemoryStore):
        async def scan(self, scope, *, filters=None, cursor="", limit=100):
            return await super().scan(
                scope,
                filters=MemoryFilter(include_inactive=True),
                cursor=cursor,
                limit=limit,
            )

    store = UnfilteredStore()
    await put(
        store, "message", "owner", actor=Actor.OWNER, authority=FactAuthority.HUMAN_SELF
    )
    await put(
        store,
        "message",
        "agent",
        actor=Actor.AGENT,
        authority=FactAuthority.AGENT_OUTPUT,
    )
    await put(store, "message", "expired", state=MemoryState.EXPIRED)
    hits = await BM25RetrievalStrategy().search(
        store,
        "message",
        [SCOPE],
        filters=MemoryFilter(
            states={MemoryState.CONFIRMED},
            exclude_authorities={FactAuthority.AGENT_OUTPUT},
        ),
    )
    assert [hit.memory_id for hit in hits] == ["owner"]


@pytest.mark.asyncio
async def test_scope_escape_and_invalid_pagination_are_errors() -> None:
    class BadStore(InMemoryStore):
        mode = "scope"

        async def scan(self, scope, *, filters=None, cursor="", limit=100):
            if self.mode == "scope":
                return MemoryPage(
                    records=[
                        MemoryRecord(memory_id="wrong", scope=OTHER, content="term")
                    ]
                )
            if self.mode == "cursor":
                return MemoryPage(records=[], has_more=True, next_cursor="same")
            return MemoryPage(
                records=[MemoryRecord(memory_id="dup", scope=SCOPE, content="term")],
                has_more=True,
                next_cursor=cursor + "x",
            )

    store = BadStore()
    strategy = BM25RetrievalStrategy()
    with pytest.raises(MemoryIsolationError):
        await strategy.search(store, "term", [SCOPE])
    for mode in ["cursor", "duplicate"]:
        store.mode = mode
        with pytest.raises(BM25ReadLimitError):
            await strategy.search(store, "term", [SCOPE])
    with pytest.raises(MemoryIsolationError):
        await strategy.search(store, "term", [])


@pytest.mark.asyncio
async def test_new_writes_and_deletion_visible_without_stale_cache() -> None:
    store = InMemoryStore()
    strategy = BM25RetrievalStrategy()
    await put(store, "orange", "fruit")
    assert await strategy.search(store, "orange", [SCOPE])
    await store.forget(SCOPE, "fruit", hard=True)
    assert not await strategy.search(store, "orange", [SCOPE])
    await put(store, "purple", "new-fruit")
    assert await strategy.search(store, "purple", [SCOPE])
    await store.forget(SCOPE, "new-fruit", hard=True)
    assert not await strategy.search(store, "purple", [SCOPE])
