from contextlib import asynccontextmanager

import pytest

from benchmarks.public_memory_window_ablation import (
    CachedEmbedding,
    PointwiseOrder,
    summarize,
    union_candidates,
    vector_receipt,
)
from doppel_memory.indexing import memory_index_fingerprint
from doppel_memory.models import MemoryRecord, MemoryScope, RecallResult
from doppel_memory.personal_rerank import (
    PersonalMemoryRerankConfig,
    PersonalMemoryRerankItem,
    PersonalMemoryRerankRequest,
    PersonalMemoryRerankScore,
    score_personal_memories,
)
from doppel_memory.vector import QueryEmbeddingProvider


def candidates(ids=("a", "b", "c")):
    scope = MemoryScope(user_id="owner", agent_id="agent")
    return [
        RecallResult(
            scope=scope, memory_id=key, fact=f"text-{key}", raw_text=f"text-{key}"
        )
        for key in ids
    ]


async def test_embedding_cache_is_copy_safe_symmetric_and_does_not_change_identity():
    class Base:
        name, version, dimensions = "fake", "1", 2
        calls = 0

        async def embed(self, texts):
            self.calls += 1
            return [[1.0, 2.0] for _ in texts]

    provider = CachedEmbedding(Base())
    assert not isinstance(provider, QueryEmbeddingProvider)
    first = await provider.embed(["same query"])
    first[0][0] = 999
    assert await provider.embed(["same query"]) == [[1.0, 2.0]]
    await provider.embed(["other query"])
    assert provider.calls == 2 and provider.hits == 1 and provider.base.calls == 2
    assert (provider.name, provider.version, provider.dimensions) == ("fake", "1", 2)


async def test_pointwise_reuse_matches_direct_scoring_and_each_arms_own_tie_order():
    class Scorer:
        name, version = "fake-pointwise", "1"

        async def rerank(self, request):
            return [
                PersonalMemoryRerankScore(
                    item_id=item.item_id,
                    score=0.5 if item.content.endswith(("a", "b")) else 0.9,
                )
                for item in request.items
            ]

    arms = [candidates(("a", "b")), candidates(("c", "b", "a"))]
    union = union_candidates(arms)
    request = PersonalMemoryRerankRequest(
        question="q",
        items=[
            PersonalMemoryRerankItem(item_id=f"candidate-{i}", content=c.raw_text)
            for i, c in enumerate(union)
        ],
    )
    values, summary = await score_personal_memories(
        Scorer(), request, PersonalMemoryRerankConfig(), total_candidates=len(union)
    )
    assert summary.status == "completed" and len(union) == 3
    ranker = PointwiseOrder("q", union, values)
    assert [c.memory_id for c in await ranker.rerank("q", arms[0], limit=20)] == [
        "a",
        "b",
    ]
    assert [c.memory_id for c in await ranker.rerank("q", arms[1], limit=20)] == [
        "c",
        "b",
        "a",
    ]
    with pytest.raises(ValueError, match="query changed"):
        await ranker.rerank("changed", arms[0], limit=20)
    changed = arms[0][0].model_copy(update={"raw_text": "changed source"})
    with pytest.raises(ValueError, match="source changed"):
        await ranker.rerank("q", [changed], limit=20)


@pytest.mark.parametrize(
    "field,value",
    [
        ("raw_text", "changed"),
        ("scope", MemoryScope(user_id="other", agent_id="agent")),
    ],
)
def test_union_rejects_changed_text_or_scope_for_same_id(field, value):
    original = candidates(("a",))[0]
    with pytest.raises(ValueError, match="conflicting"):
        union_candidates([[original], [original.model_copy(update={field: value})]])


def test_summary_reports_recovery_and_displacement_and_excludes_negatives():
    def arm(ids):
        return {
            "annotated": 2,
            "packed_items": 2,
            **{
                stage + "_annotated_ids": ids
                for stage in ("candidate", "top20", "packed")
            },
        }

    rows = [
        {
            "abstention_label": False,
            "historical_context_match": False,
            "arms": {"80": arm(["old"]), "160": arm(["new"])},
        },
        {
            "abstention_label": True,
            "historical_context_match": True,
            "arms": {"80": arm(["ignore"]), "160": arm([])},
        },
    ]
    result = summarize(rows)
    assert result["80"]["annotated"] == 2 and result["160"]["packed"] == 1
    assert result["paired"]["packed"] == {
        "recovered_turns": 1,
        "displaced_turns": 1,
        "gain_questions": 0,
        "loss_questions": 0,
    }
    assert result["fresh80_historical_context_matches"] == 1


@pytest.mark.parametrize("fault", [None, "missing", "scope", "version", "fingerprint"])
async def test_vector_catalog_requires_current_exact_scope_version_and_fingerprint(
    fault,
):
    scope = MemoryScope(user_id="owner", agent_id="agent")
    record = MemoryRecord(memory_id="m", scope=scope, content="original")
    entry = {
        "memory_id": "m",
        "scope_key": scope.scope_key,
        "source_version": record.version,
        "record_fingerprint": memory_index_fingerprint(record),
    }
    if fault == "scope":
        entry["scope_key"] = "other"
    if fault == "version":
        entry["source_version"] = 99
    if fault == "fingerprint":
        entry["record_fingerprint"] = "stale"

    class Connection:
        async def fetch(self, query, *args):
            assert query.startswith("SELECT") and args == (scope.scope_key, ["m"])
            return [] if fault == "missing" else [entry]

    class Pool:
        @asynccontextmanager
        async def acquire(self):
            yield Connection()

    class Store:
        async def _ensure_pool(self):
            return Pool()

    class Index:
        _table_sql, profile = '"schema"."vectors"', "fake"

        async def initialize(self):
            pass

    if fault is None:
        receipt = await vector_receipt(Store(), Index(), scope, {"m": record})
        assert receipt["count"] == 1 and len(receipt["sha256"]) == 64
    else:
        with pytest.raises(ValueError, match="missing or stale"):
            await vector_receipt(Store(), Index(), scope, {"m": record})
