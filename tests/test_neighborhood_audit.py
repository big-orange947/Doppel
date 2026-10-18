from __future__ import annotations

import pytest

from benchmarks import public_memory_neighborhood_audit as runner
from doppel_memory.models import MemoryScope
from tests.test_public_context_baseline import setup


def test_zero_paid_plan_has_matched_count_baseline_and_explicit_caps():
    plan = runner.make_plan(
        {"dataset": "frozen"}, {"plan": {"schema": "test", "manifest": {"cases": []}}}
    )
    assert plan["config"]["before"] == plan["config"]["after"] == 1
    assert plan["config"]["max_candidates"] == 240
    assert plan["config"]["max_content_bytes"] == 300000
    assert plan["llm_calls"] == plan["qa_calls"] == plan["graph_calls"] == 0
    assert plan["local_query_embeddings_max"] == 5
    assert "same-size-native" in plan["baseline"]
    assert plan["opened_diagnostic_not_fresh"] and not plan["publication_ready"]


@pytest.mark.asyncio
async def test_reference_index_uses_original_not_chunk_local_position(tmp_path):
    store, host, _, scope, records, _ = await setup(tmp_path)
    try:
        items = {
            host.positions[(scope.scope_key, r.source_event_id)]: {
                "memory_id": r.memory_id
            }
            for r in records
        }
        index = runner.source_index(scope, {r.memory_id: r for r in records}, items)
        position = await index.locate(scope, records[1].memory_id)
        assert records[1].metadata["raw"]["turn_index"] == 0 and position.ordinal == 1
        neighbors = await index.neighbors(scope, position, before=1, after=1)
        assert [n.memory_id for n in neighbors] == [records[0].memory_id]
        assert (
            await index.locate(
                MemoryScope(user_id="other", agent_id="a"), records[1].memory_id
            )
            is None
        )
    finally:
        await store.close()
