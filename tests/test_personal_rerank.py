"""Authorized, reorder-only personal-memory reranking."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from doppel_memory import (
    FactAuthority,
    InMemoryStore,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    PersonalMemoryQueryDraft,
    PersonalMemoryQueryEngine,
    PersonalMemoryQueryRequest,
    PersonalMemoryRerankConfig,
    PersonalMemoryRerankScore,
)

SCOPE = MemoryScope(user_id="owner", agent_id="agent")
OTHER_SCOPE = MemoryScope(user_id="other", agent_id="agent")
NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)


class _Planner:
    name = "tests.rerank-planner"
    version = "1"

    def __init__(self, *, intent: str = "lookup") -> None:
        self.intent = intent

    async def plan(self, request: PersonalMemoryQueryRequest) -> PersonalMemoryQueryDraft:
        del request
        return PersonalMemoryQueryDraft(
            intent=self.intent,
            search_text="相机",
            temporal_statuses=["current"] if self.intent != "count" else [],
        )


class _Reranker:
    name = "tests.personal-memory-reranker"
    version = "1"

    def __init__(self, *, fail: bool = False, malformed: bool = False) -> None:
        self.fail = fail
        self.malformed = malformed
        self.requests = []

    async def rerank(self, request):
        self.requests.append(request)
        if self.fail:
            raise RuntimeError("secret-from-provider")
        if self.malformed:
            return []
        return [
            PersonalMemoryRerankScore(
                item_id=item.item_id,
                score=1.0 if "更相关" in item.content else 0.0,
            )
            for item in request.items
        ]


def _record(
    memory_id: str,
    content: str,
    *,
    day: int,
    scope: MemoryScope = SCOPE,
    authority: FactAuthority = FactAuthority.HUMAN_SELF,
) -> MemoryRecord:
    at = datetime(2026, 1, day, tzinfo=UTC)
    return MemoryRecord(
        memory_id=memory_id,
        scope=scope,
        content=content,
        kind="fact",
        actor="owner",
        authority=authority,
        state=MemoryState.CONFIRMED,
        tags=["personal-memory", "state"],
        source_message_id=f"message-{memory_id}",
        extractor="tests.personal-rerank",
        created_at=at,
        updated_at=at,
        metadata={
            "personal_memory_type": "state",
            "subject": "owner",
            "subject_id": scope.user_id,
            "temporal_status": "current",
            "revision_kind": "assertion",
            "evidence": [{"evidence_id": f"message-{memory_id}"}],
        },
    )


async def _store(*records: MemoryRecord) -> InMemoryStore:
    store = InMemoryStore()
    for record in records:
        await store.put(record)
    return store


@pytest.mark.asyncio
async def test_memory_reranker_sees_only_opaque_authorized_content_and_reorders() -> None:
    store = await _store(
        _record("preferred", "相机的更相关事实。", day=1),
        _record("baseline-first", "相机的一般事实。", day=2),
        _record("foreign", "其他用户的相机事实。", day=3, scope=OTHER_SCOPE),
        _record(
            "agent-output",
            "Agent 猜测的相机事实。",
            day=4,
            authority=FactAuthority.AGENT_OUTPUT,
        ),
    )
    reranker = _Reranker()

    result = await PersonalMemoryQueryEngine(
        store, memory_reranker=reranker
    ).query(_Planner(), "这台相机的情况？", [SCOPE], now=NOW, trace_limit=100)

    assert [hit.record.memory_id for hit in result.hits] == [
        "preferred",
        "baseline-first",
    ]
    assert len(reranker.requests) == 1
    request = reranker.requests[0]
    assert request.question == "这台相机的情况？"
    assert [item.model_dump() for item in request.items] == [
        {"item_id": "item_0", "content": "相机的一般事实。"},
        {"item_id": "item_1", "content": "相机的更相关事实。"},
    ]
    serialized = request.model_dump_json()
    assert all(value not in serialized for value in ("baseline-first", "preferred", "owner"))
    assert result.memory_reranking is not None
    assert result.memory_reranking.status == "completed"
    assert result.memory_reranking.total_candidates == 2
    assert result.memory_reranking.reranked_candidates == 2
    assert result.matched_record_count == 2
    assert result.hits[0].score < result.hits[1].score
    assert result.hits[0].memory_reranker_score == 1.0
    assert result.hits[1].memory_reranker_score == 0.0
    assert "memory_reranker_score:1.000000" in result.hits[0].reasons
    assert result.trace is not None
    assert result.trace.counts["ranking:engine:memory_reranker_scored"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["fail", "malformed"])
async def test_memory_reranker_failure_preserves_baseline_order_without_leaking(mode) -> None:
    store = await _store(
        _record("older", "相机旧记录。", day=1),
        _record("newer", "相机新记录。", day=2),
    )
    reranker = _Reranker(fail=mode == "fail", malformed=mode == "malformed")

    result = await PersonalMemoryQueryEngine(
        store, memory_reranker=reranker
    ).query(_Planner(), "相机？", [SCOPE], now=NOW)

    assert [hit.record.memory_id for hit in result.hits] == ["newer", "older"]
    assert result.memory_reranking is not None
    assert result.memory_reranking.status == "unavailable"
    assert "memory_reranking_unavailable" in result.warnings
    assert "secret-from-provider" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_memory_reranker_is_bounded_and_limit_failure_preserves_order() -> None:
    store = await _store(
        _record("older", "相机旧记录。", day=1),
        _record("newer", "相机新记录。", day=2),
    )
    reranker = _Reranker()
    result = await PersonalMemoryQueryEngine(
        store,
        memory_reranker=reranker,
        rerank_config=PersonalMemoryRerankConfig(
            max_candidates=1,
            max_input_chars=1,
        ),
    ).query(_Planner(), "相机？", [SCOPE], now=NOW)

    assert reranker.requests == []
    assert [hit.record.memory_id for hit in result.hits] == ["newer", "older"]
    assert result.memory_reranking is not None
    assert result.memory_reranking.status == "limit_exceeded"
    assert result.memory_reranking.total_candidates == 2
    assert result.memory_reranking.offered_candidates == 1


@pytest.mark.asyncio
async def test_exact_count_does_not_invoke_memory_reranker() -> None:
    store = await _store(_record("one", "相机事件。", day=1))
    reranker = _Reranker()

    result = await PersonalMemoryQueryEngine(
        store, memory_reranker=reranker
    ).query(_Planner(intent="count"), "相机有几次？", [SCOPE], now=NOW)

    assert reranker.requests == []
    assert result.memory_reranking is not None
    assert result.memory_reranking.status == "not_run"


@pytest.mark.asyncio
async def test_cancellation_is_not_swallowed_by_memory_rerank_boundary() -> None:
    class CancelledReranker(_Reranker):
        async def rerank(self, request):
            del request
            raise asyncio.CancelledError

    store = await _store(_record("one", "相机记录。", day=1))
    with pytest.raises(asyncio.CancelledError):
        await PersonalMemoryQueryEngine(
            store, memory_reranker=CancelledReranker()
        ).query(_Planner(), "相机？", [SCOPE], now=NOW)
