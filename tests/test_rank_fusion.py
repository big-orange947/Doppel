import asyncio

import pytest

from doppel_memory.models import (
    FactAuthority,
    MemoryIsolationError,
    MemoryScope,
    RecallResult,
)
from doppel_memory.rank_fusion import RankFusionReranker, rank_fusion_order


def candidates():
    return [
        RecallResult(
            scope=MemoryScope(user_id="u", agent_id="a"),
            memory_id=f"m{i}",
            fact=f"original{i}",
            raw_text=f"original{i}",
            actor="agent",
            authority=FactAuthority.AGENT_OUTPUT,
            source_event_id=f"e{i}",
            similarity=0.7,
        )
        for i in range(4)
    ]


class Reverse:
    async def rerank(self, query, items, *, limit):
        self.limit = limit
        return list(reversed(items))[:limit]


def test_formula_and_stable_ties():
    assert rank_fusion_order([3, 2, 1, 0]) == [0, 3, 1, 2]
    assert rank_fusion_order([0, 1, 2, 3]) == [0, 1, 2, 3]
    assert rank_fusion_order([]) == []


@pytest.mark.parametrize("permutation", [[0, 0], [1], [-1, 0], [False], [0.0]])
def test_incomplete_invalid_permutations_fail(permutation):
    with pytest.raises(ValueError):
        rank_fusion_order(permutation)


@pytest.mark.parametrize("k", [0, -1, 1.5, True])
def test_invalid_k(k):
    with pytest.raises(ValueError):
        rank_fusion_order([], rrf_k=k)


@pytest.mark.asyncio
async def test_full_order_requested_and_originals_preserved():
    delegate = Reverse()
    original = candidates()
    before = [c.model_dump(mode="json") for c in original]
    result = await RankFusionReranker(delegate).rerank(
        "generic query", original, limit=2
    )
    assert delegate.limit == 4
    assert [c.memory_id for c in result] == ["m0", "m3"]
    assert [c.model_dump(mode="json") for c in original] == before
    assert result[0].model_dump(mode="json") == before[0]
    result[0].fact = "caller edit"
    assert original[0].fact == "original0"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "damage",
    [
        "unknown",
        "scope",
        "text",
        "actor",
        "time",
        "duplicate",
        "filtered",
        "input_mutation",
        "nan",
    ],
)
async def test_delegate_corruption_is_not_a_fallback(damage):
    class Bad:
        async def rerank(self, query, items, *, limit):
            copied = [c.model_copy(deep=True) for c in items]
            if damage == "unknown":
                copied[0].memory_id = "unknown"
            elif damage == "scope":
                copied[0].scope = MemoryScope(user_id="other", agent_id="a")
            elif damage == "text":
                copied[0].raw_text = "made up"
            elif damage == "actor":
                copied[0].actor = "owner"
            elif damage == "time":
                copied[0].source_event_id = "other-event"
            elif damage == "duplicate":
                copied[1] = copied[0]
            elif damage == "filtered":
                copied.pop()
            elif damage == "input_mutation":
                items[0].fact = "mutation"
            else:
                copied[0].similarity = float("nan")
            return copied

    with pytest.raises((ValueError, MemoryIsolationError)):
        await RankFusionReranker(Bad()).rerank("query", candidates(), limit=2)


@pytest.mark.asyncio
async def test_empty_and_input_caps():
    ranker = RankFusionReranker(Reverse(), max_candidates=3)
    assert await ranker.rerank("query", [], limit=1) == []
    with pytest.raises(ValueError):
        await ranker.rerank("query", candidates(), limit=1)
    with pytest.raises(ValueError):
        await ranker.rerank(" ", [], limit=1)
    with pytest.raises(MemoryIsolationError):
        await ranker.rerank("query", [RecallResult(fact="unscoped")], limit=1)


@pytest.mark.asyncio
async def test_timeout_propagates_no_identity_fallback():
    class Slow:
        async def rerank(self, query, items, *, limit):
            await asyncio.sleep(1)

    with pytest.raises(TimeoutError):
        await RankFusionReranker(Slow(), timeout_seconds=0.001).rerank(
            "query", candidates(), limit=1
        )


@pytest.mark.asyncio
async def test_distinct_scopes_never_collapse_same_memory_id():
    items = candidates()[:2]
    items[1].memory_id = items[0].memory_id
    items[1].scope = MemoryScope(user_id="other-authorized", agent_id="a")
    result = await RankFusionReranker(Reverse()).rerank("query", items, limit=2)
    assert len(result) == 2
    assert result[0].scope != result[1].scope


@pytest.mark.asyncio
async def test_delegate_scores_not_exported_as_fused_probabilities():
    class Scores:
        async def rerank(self, query, items, *, limit):
            return [c.model_copy(update={"similarity": 999.0}) for c in reversed(items)]

    assert all(
        c.similarity == 0.7
        for c in await RankFusionReranker(Scores()).rerank(
            "query", candidates(), limit=4
        )
    )
