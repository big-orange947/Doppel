"""Journal link controls independent of opened benchmark topics and answers."""

from datetime import UTC, datetime

import pytest

from benchmarks.public_memory_comparison import SourceBinding
from benchmarks.public_memory_source_window import (
    JournalContextResolver,
    validate_parent,
)
from doppel_memory.in_memory_store import InMemoryStore
from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryIsolationError,
    MemoryRecord,
    MemoryScope,
)

NOW = datetime(2026, 10, 1, tzinfo=UTC)
SCOPE = MemoryScope(user_id="owner", agent_id="helper")


def entry(identity, session, turn, *, chunk="same-chunk", local_turn=0):
    event = "event-" + identity
    text = "literal source " + identity
    source = SourceBinding(
        identity,
        (session, turn),
        "user",
        text,
        int(NOW.timestamp() * 1000),
        chunk,
        local_turn,
    )
    record = MemoryRecord(
        memory_id=identity,
        scope=SCOPE,
        content=text,
        actor=Actor.OWNER,
        authority=FactAuthority.HUMAN_SELF,
        source_event_id=event,
        created_at=NOW,
        extractor="ingestor",
        metadata={
            "raw": {
                "source_text": text,
                "transport_role": "user",
                "session_id": chunk,
                "turn_index": local_turn,
            }
        },
    )
    return (SCOPE.scope_key, event), source, record


@pytest.mark.asyncio
async def test_original_session_window_crosses_chunks_not_sessions():
    entries = [
        entry("before", 1, 8, chunk="chunk-a"),
        entry("anchor", 1, 9, chunk="chunk-b"),
        entry("after", 1, 10, chunk="chunk-c"),
        entry("different-session", 2, 10, chunk="chunk-b"),
    ]
    store = InMemoryStore()
    for _, _, record in entries:
        await store.put(record)
    resolver = JournalContextResolver(store, {k: s for k, s, _ in entries})
    neighbors = await resolver.resolve_context(
        SCOPE, entries[1][2], observed_until=NOW, limit=2
    )
    assert [r.memory_id for r in neighbors] == ["before", "after"]
    assert (
        len(
            await resolver.resolve_context(
                SCOPE, entries[1][2], observed_until=NOW, limit=1
            )
        )
        == 1
    )


@pytest.mark.asyncio
async def test_session_edge_does_not_wrap_into_adjacent_session():
    one, other = entry("anchor", 1, 0), entry("unrelated", 0, 1)
    store = InMemoryStore()
    await store.put(one[2])
    await store.put(other[2])
    resolver = JournalContextResolver(store, {k: s for k, s, _ in [one, other]})
    assert not await resolver.resolve_context(
        SCOPE, one[2], observed_until=NOW, limit=2
    )


@pytest.mark.asyncio
async def test_journal_mapping_not_authority_for_tampered_source():
    anchor, neighbor = entry("anchor", 0, 1), entry("neighbor", 0, 2)
    store = InMemoryStore()
    await store.put(anchor[2])
    await store.put(neighbor[2].model_copy(update={"content": "tampered"}))
    resolver = JournalContextResolver(store, {k: s for k, s, _ in [anchor, neighbor]})
    with pytest.raises(ValueError, match="binding invalid"):
        await resolver.resolve_context(SCOPE, anchor[2], observed_until=NOW, limit=2)
    with pytest.raises(MemoryIsolationError):
        await resolver.resolve_context(
            MemoryScope(user_id="foreign", agent_id="helper"),
            anchor[2],
            observed_until=NOW,
            limit=2,
        )


def test_source_position_collision_rejected():
    one, other = entry("one", 0, 1), entry("other", 0, 1)
    with pytest.raises(ValueError, match="collision"):
        JournalContextResolver(None, {k: s for k, s, _ in [one, other]})


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "ready"},
        {"scope_ordinal": 4},
        {"clock_policy": "strict-reference-v1"},
        {"corpus_unchanged": False},
        {"vectors_unchanged": False},
        {"graph_unchanged": False},
        {"runner": "untrusted"},
    ],
)
def test_invalid_parent_cannot_launch_paid_comparison(changes):
    parent = {
        "status": "complete",
        "scope_ordinal": 7,
        "runner": "doppel.public-memory-consecutive-high-config-query.v3",
        "clock_policy": "provided-history-v1",
        "corpus_unchanged": True,
        "vectors_unchanged": True,
        "graph_unchanged": True,
        **changes,
    }
    with pytest.raises(ValueError, match="immutable opened parent"):
        validate_parent(parent)
