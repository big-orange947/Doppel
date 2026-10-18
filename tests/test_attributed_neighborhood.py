from __future__ import annotations

import asyncio

import pytest

from doppel_memory.models import (
    FactAuthority,
    MemoryIsolationError,
    MemoryScope,
    MemoryState,
)
from doppel_memory.source_order import ExplicitSourceOrderIndex, SourcePosition
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.neighborhood import (
    AttributedNeighborhoodExpander,
    NeighborhoodConfig,
)
from tests.test_public_context_baseline import Candidates, setup


async def fixture(tmp_path):
    store, host, _, scope, records, candidates = await setup(tmp_path)
    snippets = (
        await AttributedContextRetriever(
            store, strategy=Candidates(candidates), resolve_event=host.resolve_event
        ).search(scope, "generic", limit=3)
    ).snippets
    values = [
        SourcePosition(
            scope_key=scope.scope_key,
            session_id=r.metadata["raw"]["session_id"],
            ordinal=host.positions[(scope.scope_key, r.source_event_id)][1],
            memory_id=r.memory_id,
            evidence_id=r.source_event_id,
        )
        for r in records
    ]
    index = ExplicitSourceOrderIndex(values)
    return store, host, scope, records, snippets, values, index


@pytest.mark.asyncio
async def test_neighbor_added_without_new_facts_role_changes_or_transport_index_guess(
    tmp_path,
):
    store, host, scope, records, snippets, _, index = await fixture(tmp_path)
    try:
        # The importer was chunked one message at a time, so transport indices
        # are all zero. Explicit source ordinals still connect user0/assistant1.
        assert [r.metadata["raw"]["turn_index"] for r in records] == [0, 0, 0]
        expander = AttributedNeighborhoodExpander(
            store, resolve_event=host.resolve_event, source_order=index
        )
        result = await expander.expand(scope, [snippets[1]])
        assert [s.memory_id for s in result.snippets] == [
            records[1].memory_id,
            records[0].memory_id,
        ]
        assert result.snippets[0].authority == FactAuthority.AGENT_OUTPUT
        assert result.snippets[1].authority == FactAuthority.HUMAN_SELF
        assert result.snippets[1].text == records[0].metadata["raw"]["source_text"]
        assert result.snippets[1].similarity == 0
        assert result.added_count == 1 and result.links[0].offset == -1
        assert not result.rejected
        # Same scope, different session and older time do not imply adjacency.
        isolated = await expander.expand(scope, [snippets[2]])
        assert len(isolated.snippets) == 1 and isolated.added_count == 0
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_dedup_and_assistant_neighbors_still_keep_original_authority(tmp_path):
    store, host, scope, _, snippets, _, index = await fixture(tmp_path)
    try:
        expander = AttributedNeighborhoodExpander(
            store, resolve_event=host.resolve_event, source_order=index
        )
        result = await expander.expand(scope, snippets[:2])
        assert len(result.snippets) == 2 and result.added_count == 0
        result = await expander.expand(scope, snippets[:1])
        assert (
            result.snippets[1].actor == "agent"
            and result.snippets[1].authority == FactAuthority.AGENT_OUTPUT
        )
        assert len(result.links) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_missing_positions_preserve_anchor_without_invented_neighbors(tmp_path):
    store, host, scope, _, snippets, _, _ = await fixture(tmp_path)
    try:
        result = await AttributedNeighborhoodExpander(
            store,
            resolve_event=host.resolve_event,
            source_order=ExplicitSourceOrderIndex([]),
        ).expand(scope, [snippets[0]])
        assert result.snippets == [snippets[0]]
        assert result.rejected == {"position_unavailable": 1}
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_limits_explicit_and_source_text_never_truncated(tmp_path):
    store, host, scope, _, snippets, _, index = await fixture(tmp_path)
    try:
        capped = AttributedNeighborhoodExpander(
            store,
            resolve_event=host.resolve_event,
            source_order=index,
            config=NeighborhoodConfig(max_anchors=1, max_candidates=1),
        )
        result = await capped.expand(scope, [snippets[0]])
        assert result.snippets == [snippets[0]] and result.candidate_budget_exhausted
        assert result.unvisited_anchors == 1
        with pytest.raises(ValueError, match="anchor window"):
            await capped.expand(scope, snippets[:2])
        tiny = AttributedNeighborhoodExpander(
            store,
            resolve_event=host.resolve_event,
            source_order=index,
            config=NeighborhoodConfig(max_content_bytes=1),
        )
        with pytest.raises(ValueError, match="byte budget"):
            await tiny.expand(scope, snippets[:1])
        with pytest.raises(ValueError):
            NeighborhoodConfig(max_anchors=2, max_candidates=1)
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attack",
    ["scope", "session", "offset", "oversize", "duplicate", "lookup", "mutation"],
)
async def test_bad_resolver_fails_closed(tmp_path, attack):
    store, host, scope, _, snippets, values, index = await fixture(tmp_path)

    class Bad:
        async def locate(self, supplied_scope, key):
            value = await index.locate(supplied_scope, key)
            if attack == "lookup" and key == values[0].memory_id:
                return value.model_copy(update={"ordinal": 8})
            return value

        async def neighbors(self, supplied_scope, anchor, **kwargs):
            value = values[0]
            if attack == "scope":
                value = value.model_copy(update={"scope_key": "other"})
            elif attack == "session":
                value = value.model_copy(update={"session_id": "other"})
            elif attack == "offset":
                value = value.model_copy(update={"ordinal": 9})
            elif attack == "oversize":
                return [value, value, value]
            elif attack == "duplicate":
                return [value, value]
            elif attack == "mutation":
                supplied_scope.user_id = "other"
            return [value]

    try:
        with pytest.raises((ValueError, MemoryIsolationError)):
            await AttributedNeighborhoodExpander(
                store, resolve_event=host.resolve_event, source_order=Bad()
            ).expand(scope, [snippets[1]])
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_revoked_anchor_does_not_leave_orphan_neighbor(tmp_path):
    store, host, scope, records, snippets, _, index = await fixture(tmp_path)

    class Revoking:
        async def locate(self, supplied_scope, key):
            return await index.locate(supplied_scope, key)

        async def neighbors(self, supplied_scope, anchor, **kwargs):
            await store.transition(scope, records[1].memory_id, MemoryState.EXPIRED)
            return await index.neighbors(supplied_scope, anchor, **kwargs)

    try:
        result = await AttributedNeighborhoodExpander(
            store, resolve_event=host.resolve_event, source_order=Revoking()
        ).expand(scope, [snippets[1]])
        assert result.snippets == [] and result.links == []
        assert result.rejected["orphaned_after_anchor_change"] == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_foreign_or_duplicate_anchors_and_timeout(tmp_path):
    store, host, scope, _, snippets, _, index = await fixture(tmp_path)

    class Slow:
        async def locate(self, supplied_scope, key):
            await asyncio.sleep(1)

    try:
        expander = AttributedNeighborhoodExpander(
            store, resolve_event=host.resolve_event, source_order=index
        )
        with pytest.raises(MemoryIsolationError):
            await expander.expand(
                MemoryScope(user_id="other", agent_id="a"), snippets[:1]
            )
        with pytest.raises(ValueError, match="duplicate"):
            await expander.expand(scope, [snippets[0], snippets[0]])
        with pytest.raises(TimeoutError):
            await AttributedNeighborhoodExpander(
                store,
                resolve_event=host.resolve_event,
                source_order=Slow(),
                config=NeighborhoodConfig(timeout_seconds=0.001),
            ).expand(scope, snippets[:1])
        assert (await expander.expand(scope, [])).snippets == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_byte_skips_are_explicit_without_shortening_anchor(tmp_path):
    store, host, scope, _, snippets, _, index = await fixture(tmp_path)
    try:
        expander = AttributedNeighborhoodExpander(
            store, resolve_event=host.resolve_event, source_order=index
        )
        cap = expander._size(scope, snippets[1])
        limited = AttributedNeighborhoodExpander(
            store,
            resolve_event=host.resolve_event,
            source_order=index,
            config=NeighborhoodConfig(max_content_bytes=cap),
        )
        result = await limited.expand(scope, [snippets[1]])
        assert result.snippets == [snippets[1]] and result.content_bytes == cap
        assert result.rejected == {"byte_budget_skip": 1}
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_stale_anchor_and_inactive_neighbor_are_not_returned(tmp_path):
    store, host, scope, records, snippets, _, index = await fixture(tmp_path)
    try:
        expander = AttributedNeighborhoodExpander(
            store, resolve_event=host.resolve_event, source_order=index
        )
        stale = snippets[1].model_copy(update={"text": "invented content"})
        result = await expander.expand(scope, [stale])
        assert result.snippets == [] and result.rejected == {"changed_anchor": 1}
        await store.transition(scope, records[0].memory_id, MemoryState.EXPIRED)
        result = await expander.expand(scope, [snippets[1]])
        assert result.snippets == [snippets[1]]
        assert result.rejected == {"inactive_or_unconfirmed": 1}
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_order_changes_drop_anchor_and_unsupported_neighbor(tmp_path):
    store, host, scope, records, snippets, _, index = await fixture(tmp_path)

    class Changing:
        anchor_lookups = 0

        async def locate(self, supplied_scope, key):
            value = await index.locate(supplied_scope, key)
            if key == records[1].memory_id:
                self.anchor_lookups += 1
                if self.anchor_lookups > 1:
                    return value.model_copy(update={"ordinal": 99})
            return value

        async def neighbors(self, supplied_scope, anchor, **kwargs):
            return await index.neighbors(supplied_scope, anchor, **kwargs)

    try:
        result = await AttributedNeighborhoodExpander(
            store, resolve_event=host.resolve_event, source_order=Changing()
        ).expand(scope, [snippets[1]])
        assert result.snippets == []
        assert result.rejected["source_order_changed"] == 1
        assert result.rejected["orphaned_after_anchor_change"] == 1
    finally:
        await store.close()


def test_conflicting_custom_positions_rejected_even_when_individually_consistent():
    by_id, by_order = {}, {}
    value = SourcePosition(
        scope_key="s", session_id="c", ordinal=0, memory_id="a", evidence_id="ea"
    )
    AttributedNeighborhoodExpander._remember(value, by_id, by_order)
    with pytest.raises(ValueError, match="share"):
        AttributedNeighborhoodExpander._remember(
            value.model_copy(update={"memory_id": "b"}), by_id, by_order
        )
    with pytest.raises(ValueError, match="changed position"):
        AttributedNeighborhoodExpander._remember(
            value.model_copy(update={"ordinal": 1}), by_id, by_order
        )
