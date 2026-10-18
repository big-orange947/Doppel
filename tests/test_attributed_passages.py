from __future__ import annotations

import pytest

from doppel_memory.models import (
    FactAuthority,
    MemoryIsolationError,
    MemoryScope,
    MemoryState,
    RecallResult,
)
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.passages import AttributedPassageRetriever, PassageRetrievalConfig
from tests.test_public_context_baseline import Candidates, setup


async def make(tmp_path, reranker=None, *, max_chars=12, max_passages=80):
    store, host, _, scope, records, candidates = await setup(tmp_path)
    parent = AttributedContextRetriever(
        store, strategy=Candidates(candidates), resolve_event=host.resolve_event
    )
    retriever = AttributedPassageRetriever(
        parent,
        config=PassageRetrievalConfig(
            source_limit=3,
            max_chars=max_chars,
            overlap_chars=3,
            max_passages=max_passages,
        ),
        reranker=reranker,
    )
    return store, host, scope, records, parent, retriever


@pytest.mark.asyncio
async def test_offsets_original_role_time_and_deterministic_ids(tmp_path):
    store, _, scope, _, parent, retriever = await make(tmp_path)
    try:
        result = await retriever.search(scope, "query", limit=30)
        again = await retriever.search(scope, "query", limit=30)
        assert result == again and not result.candidate_budget_exhausted
        assert result.source_count == 3 and result.candidates_seen > 3
        assert len({p.passage_id for p in result.passages}) == len(result.passages)
        assert len({p.memory_id for p in result.passages}) == 3
        for p in result.passages:
            original = await retriever.resolve_original(scope, p)
            assert original[p.start : p.end] == p.text
            assert p.offset_unit == "unicode-codepoint"
            source = await store.get(scope, p.memory_id)
            assert source.created_at == p.at and source.source_event_id == p.evidence_id
            assert p.authority == (
                FactAuthority.AGENT_OUTPUT
                if p.role == "assistant"
                else FactAuthority.HUMAN_SELF
            )
        assert (await parent.search(scope, "query")).snippets[
            0
        ].text == " raw 0 source "
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_budget_is_bounded_breadth_first_and_reported(tmp_path):
    store, _, scope, _, _, retriever = await make(tmp_path, max_passages=3)
    try:
        result = await retriever.search(scope, "query", limit=3)
        assert result.candidates_seen == 3 and result.candidate_budget_exhausted
        assert len({p.memory_id for p in result.passages}) == 3
        with pytest.raises(ValueError):
            await retriever.search(scope, "query", limit=4)
    finally:
        await store.close()


@pytest.mark.parametrize("attack", ["text", "offset", "digest", "authority", "foreign"])
@pytest.mark.asyncio
async def test_resolve_rejects_forged_or_foreign_spans(tmp_path, attack):
    store, _, scope, _, _, retriever = await make(tmp_path)
    try:
        p = (await retriever.search(scope, "query")).passages[0]
        changes = {
            "text": {"text": "forged"},
            "offset": {"start": p.start + 1},
            "digest": {"source_text_sha256": "0" * 64},
            "authority": {"authority": FactAuthority.AGENT_OUTPUT},
            "foreign": {"scope_key": "alien"},
        }[attack]
        with pytest.raises((ValueError, MemoryIsolationError)):
            await retriever.resolve_original(scope, p.model_copy(update=changes))
        if attack == "foreign":
            with pytest.raises(MemoryIsolationError):
                await retriever.resolve_original(
                    MemoryScope(user_id="alien", agent_id="x"), p
                )
    finally:
        await store.close()


@pytest.mark.parametrize("attack", ["invent", "foreign", "poison"])
@pytest.mark.asyncio
async def test_reranker_controls_order_not_source_identity_or_text(tmp_path, attack):
    class Reranker:
        async def rerank(self, query, items, *, limit):
            item = items[-1]
            changes = {
                "invent": {"memory_id": "invented"},
                "foreign": {"scope": MemoryScope(user_id="alien", agent_id="x")},
                "poison": {
                    "fact": "POISON",
                    "raw_text": "POISON",
                    "authority": FactAuthority.HUMAN_SELF,
                },
            }[attack]
            return [item.model_copy(update=changes)]

    store, _, scope, _, _, retriever = await make(tmp_path, Reranker())
    try:
        if attack == "poison":
            result = await retriever.search(scope, "query")
            assert all("POISON" not in p.text for p in result.passages)
            for p in result.passages:
                await retriever.resolve_original(scope, p)
        else:
            with pytest.raises((ValueError, MemoryIsolationError)):
                await retriever.search(scope, "query")
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_revocation_during_slow_ordering_blocks_all_source_fragments(tmp_path):
    store, _, scope, records, _, retriever = await make(tmp_path)

    class Revoker:
        async def rerank(self, query, items, *, limit):
            await store.transition(scope, records[0].memory_id, MemoryState.EXPIRED)
            return items

    retriever.reranker = Revoker()
    try:
        result = await retriever.search(scope, "query", limit=30)
        assert all(p.memory_id != records[0].memory_id for p in result.passages)
        assert result.rejected["source_changed_after_passage_ordering"] > 0
        old = (await retriever.search(scope, "query")).passages[0]
        await store.transition(scope, old.memory_id, MemoryState.EXPIRED)
        with pytest.raises(ValueError):
            await retriever.resolve_original(scope, old)
    finally:
        await store.close()


def test_config_overlap_and_strict_types():
    with pytest.raises(ValueError):
        AttributedPassageRetriever(None, config=PassageRetrievalConfig(max_chars=5))
    with pytest.raises(ValueError):
        PassageRetrievalConfig(source_limit=True)


@pytest.mark.asyncio
async def test_long_source_tail_can_be_ranked_without_changing_original(tmp_path):
    class TailRanker:
        async def rerank(self, query, items, *, limit):
            return sorted(items, key=lambda p: query not in p.fact)[:limit]

    store, host, scope, records, parent, retriever = await make(
        tmp_path, TailRanker(), max_chars=1200
    )
    text = "Generic unrelated opening. " * 300 + "\nTAIL_CONTROL\n"
    record = records[0]
    changed = record.model_copy(
        update={
            "memory_id": "long-raw",
            "source_event_id": "long-event",
            "idempotency_key": "",
            "content": text.strip(),
            "metadata": {
                **record.metadata,
                "raw": {**record.metadata["raw"], "source_text": text},
            },
        }
    )
    await store.put(changed)
    host.sources[(scope.scope_key, changed.source_event_id)] = changed.memory_id
    parent.strategy = Candidates(
        [
            RecallResult(
                scope=scope,
                memory_id=changed.memory_id,
                fact="untrusted",
                similarity=0.9,
            )
        ]
    )
    try:
        result = await retriever.search(scope, "TAIL_CONTROL", limit=1)
        passage = result.passages[0]
        assert "TAIL_CONTROL" in passage.text and passage.start > 0
        assert await retriever.resolve_original(scope, passage) == text
        assert (await store.get(scope, changed.memory_id)).content == text.strip()
    finally:
        await store.close()
