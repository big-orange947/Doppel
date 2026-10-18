from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest

from doppel_memory.models import (
    FactAuthority,
    MemoryIsolationError,
    MemoryScope,
    RecallResult,
)
from doppel_memory.personal_rerank import PersonalMemoryRerankScore
from doppel_memory.source_aware_rerank import (
    SourceAwareRerankConfig,
    SourceAwareReranker,
)


def candidates():
    scope = MemoryScope(user_id="private-owner", agent_id="private-agent")
    return [
        RecallResult(
            scope=scope,
            memory_id=f"private-memory-{i}",
            source_event_id=f"private-source-{i}",
            actor="owner" if i == 0 else "agent",
            authority=FactAuthority.HUMAN_SELF
            if i == 0
            else FactAuthority.AGENT_OUTPUT,
            fact=text,
            raw_text=text,
            valid_at=datetime(2020 + i, 1, 1, tzinfo=UTC),
            similarity=0.7,
        )
        for i, text in enumerate(
            (
                "original owner statement",
                "original assistant recommendation",
                "different information",
            )
        )
    ]


class Provider:
    name, version = "test-only", "1"

    def __init__(self, values=(0.5, 0.9, 0.7)):
        self.values, self.requests = values, []

    async def rerank(self, request):
        self.requests.append(request)
        return [
            PersonalMemoryRerankScore(item_id=item.item_id, score=self.values[i])
            for i, item in enumerate(request.items)
        ]


@pytest.mark.asyncio
async def test_metadata_is_explicit_no_ids_and_original_payload_is_unchanged():
    provider = Provider()
    original = candidates()
    snapshots = [c.model_dump(mode="json") for c in original]
    ranker = SourceAwareReranker(
        provider, SourceAwareRerankConfig(diversity_weight=0.0)
    )
    result = await ranker.rerank("generic", original, limit=3)
    assert [c.memory_id for c in result] == [
        original[1].memory_id,
        original[2].memory_id,
        original[0].memory_id,
    ]
    request = provider.requests[0]
    metadata = json.loads(request.items[1].content)
    assert metadata["actor"] == "agent" and metadata["authority"] == "agent_output"
    assert metadata["candidate_time"].startswith("2021")
    assert metadata["source_text"] == original[1].raw_text
    assert "private-" not in request.model_dump_json()
    assert [c.model_dump(mode="json") for c in original] == snapshots
    assert result[0].model_dump(mode="json") == snapshots[1]


@pytest.mark.asyncio
async def test_no_metadata_no_diversity_reproduces_stable_score_order_without_recency():
    provider = Provider((0.7, 0.7, 0.7))
    original = candidates()
    result = await SourceAwareReranker(
        provider, SourceAwareRerankConfig(include_metadata=False, diversity_weight=0.0)
    ).rerank("generic", original, limit=3)
    assert [c.memory_id for c in result] == [c.memory_id for c in original]
    assert [i.content for i in provider.requests[0].items] == [
        c.raw_text for c in original
    ]


@pytest.mark.asyncio
async def test_source_mmr_defers_duplicate_but_keeps_all_roles_eligible():
    original = candidates()
    original[1] = original[0].model_copy(
        update={
            "memory_id": "second-span",
            "fact": "another span",
            "raw_text": "another span",
        }
    )
    provider = Provider((1.0, 0.99, 0.9))
    result = await SourceAwareReranker(provider).rerank("generic", original, limit=3)
    assert [c.memory_id for c in result] == [
        original[0].memory_id,
        original[2].memory_id,
        "second-span",
    ]
    assert result[1].actor == "agent"


@pytest.mark.asyncio
async def test_text_mmr_can_diversify_distinct_sources_without_role_quotas():
    original = candidates()
    for c in original:
        c.actor, c.authority = "agent", FactAuthority.AGENT_OUTPUT
    original[0].raw_text = original[1].raw_text = "same repeated source language"
    result = await SourceAwareReranker(Provider((1.0, 0.99, 0.9))).rerank(
        "generic", original, limit=3
    )
    assert [c.memory_id for c in result] == [
        original[0].memory_id,
        original[2].memory_id,
        original[1].memory_id,
    ]


@pytest.mark.parametrize(
    "attack",
    ["missing", "duplicate", "unknown", "nan", "exception", "mutate", "identity"],
)
@pytest.mark.asyncio
async def test_provider_binding_or_failure_cannot_be_misreported_as_success(attack):
    class Bad(Provider):
        async def rerank(self, request):
            if attack == "exception":
                raise RuntimeError("SECRET_PROVIDER_TEXT")
            if attack == "mutate":
                request.items.pop()
            if attack == "identity":
                self.version = "changed"
            rows = await super().rerank(request)
            if attack == "missing":
                rows.pop()
            elif attack == "duplicate":
                rows[1] = rows[0]
            elif attack == "unknown":
                rows[0] = {"item_id": "unknown", "score": 0.5}
            elif attack == "nan":
                rows[0] = {"item_id": "candidate-0", "score": float("nan")}
            return rows

    with pytest.raises(RuntimeError) as caught:
        await SourceAwareReranker(Bad()).rerank("generic", candidates(), limit=3)
    assert "SECRET_PROVIDER_TEXT" not in str(caught.value)


@pytest.mark.asyncio
async def test_candidate_limits_stop_before_provider_and_empty_input_never_calls_it():
    provider = Provider()
    ranker = SourceAwareReranker(provider, SourceAwareRerankConfig(max_candidates=2))
    with pytest.raises(RuntimeError, match="limit_exceeded"):
        await ranker.rerank("generic", candidates(), limit=2)
    assert provider.requests == []
    assert await ranker.rerank("generic", [], limit=1) == []
    assert provider.requests == []


@pytest.mark.asyncio
async def test_unscoped_duplicate_or_invalid_arguments_fail_closed():
    original = candidates()
    ranker = SourceAwareReranker(Provider())
    with pytest.raises(MemoryIsolationError):
        await ranker.rerank(
            "generic", [original[0].model_copy(update={"scope": None})], limit=1
        )
    with pytest.raises(ValueError):
        await ranker.rerank("generic", [original[0], original[0]], limit=1)
    for query, limit in ((" ", 1), ("x", 0), ("x", True)):
        with pytest.raises(ValueError):
            await ranker.rerank(query, original, limit=limit)


@pytest.mark.asyncio
async def test_timeout_explicit_not_silent_identity_fallback():
    class Slow(Provider):
        async def rerank(self, request):
            await asyncio.sleep(0.05)
            return await super().rerank(request)

    with pytest.raises(RuntimeError, match="unavailable"):
        await SourceAwareReranker(
            Slow(), SourceAwareRerankConfig(timeout_seconds=0.001)
        ).rerank("generic", candidates(), limit=3)
