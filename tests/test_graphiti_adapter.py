"""Optional Graphiti adapter construction contract."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("graphiti_core")

from graphiti_core import Graphiti

from doppel_memory import (
    HybridRetrievalStrategy,
    IndexMaintainer,
    IndexMaintenancePhase,
    IndexOperationStatus,
    IndexWriter,
    InMemoryStore,
    MemoryFilter,
    MemoryRecord,
    MemoryScope,
    Retriever,
    SemanticIndex,
)
from doppel_memory.graphiti_store import (
    GraphitiFilterUnsupportedError,
    GraphitiIndexUnavailableError,
    GraphitiMemoryStore,
    GraphitiSemanticIndex,
)


class FakeGraphiti:
    def __init__(self, *, edges=None, error: Exception | None = None) -> None:
        self.edges = list(edges or [])
        self.error = error
        self.add_calls: list[dict[str, object]] = []
        self.search_calls: list[dict[str, object]] = []
        self.query_calls: list[str] = []
        self.remove_calls: list[str] = []
        self.episodes: dict[str, object] = {}
        self.driver = self

    async def add_episode(self, **kwargs):
        if self.error is not None:
            raise self.error
        self.add_calls.append(kwargs)
        episode = SimpleNamespace(
            uuid=kwargs["uuid"],
            name=kwargs["name"],
            group_id=kwargs["group_id"],
        )
        self.episodes[str(episode.uuid)] = episode
        return SimpleNamespace(episode=episode)

    async def search(self, **kwargs):
        if self.error is not None:
            raise self.error
        self.search_calls.append(kwargs)
        return self.edges

    async def execute_query(self, query: str):
        if self.error is not None:
            raise self.error
        self.query_calls.append(query)
        return []

    async def get_episodes_by_uuids(self, episode_ids):
        if self.error is not None:
            raise self.error
        return [self.episodes[value] for value in episode_ids if value in self.episodes]

    async def get_episodes_by_group_ids(
        self, group_ids, *, limit=None, uuid_cursor=None
    ):
        if self.error is not None:
            raise self.error
        episodes = sorted(
            (
                episode
                for episode in self.episodes.values()
                if episode.group_id in group_ids
                and (uuid_cursor is None or episode.uuid < uuid_cursor)
            ),
            key=lambda episode: episode.uuid,
            reverse=True,
        )
        return episodes[:limit]

    async def remove_episode(self, episode_id):
        if self.error is not None:
            raise self.error
        self.remove_calls.append(episode_id)
        self.episodes.pop(episode_id, None)


async def test_graphiti_029_adapter_constructs_without_connecting() -> None:
    with pytest.warns(DeprecationWarning, match="GraphitiSemanticIndex"):
        store = GraphitiMemoryStore(llm_api_key="test-key")
    graphiti = store._build_graphiti()
    assert isinstance(graphiti, Graphiti)
    await graphiti.close()


async def test_graphiti_unsupported_lifecycle_is_explicit() -> None:
    with pytest.warns(DeprecationWarning, match="GraphitiSemanticIndex"):
        store = GraphitiMemoryStore(llm_api_key="test-key")
    scope = MemoryScope(user_id="u", agent_id="bot")
    with pytest.raises(NotImplementedError):
        await store.get(scope, "memory-id")
    with pytest.raises(NotImplementedError):
        await store.forget(scope, "memory-id")


async def test_semantic_index_uses_stable_episode_and_exact_scope_group() -> None:
    fake = FakeGraphiti()
    store = InMemoryStore()
    index = GraphitiSemanticIndex(store, graphiti_client=fake)
    assert isinstance(index, SemanticIndex)
    assert isinstance(index, IndexWriter)
    scope = MemoryScope(
        user_id="u",
        agent_id="bot",
        platform="test",
        chat_type="private",
        chat_id="room",
    )
    record = MemoryRecord(
        memory_id="memory-1",
        scope=scope,
        content="The owner likes mountain hiking",
        extractor="test",
    )
    assert (await store.put(record)).accepted

    first = await index.index_record(
        record.model_copy(update={"content": "untrusted caller content"})
    )
    second = await index.index_record(record)

    assert first.memory_id == second.memory_id
    assert first.episode_id == second.episode_id
    assert first.scope_key == second.scope_key
    assert first.fingerprint == second.fingerprint
    assert first.memory_id == record.memory_id
    assert first.scope_key == scope.scope_key
    assert len(fake.add_calls) == 1
    assert first.status == IndexOperationStatus.INDEXED
    assert second.status == IndexOperationStatus.SKIPPED
    assert fake.add_calls[0]["group_id"] == scope.scope_key
    assert "memory_id=memory-1" in str(fake.add_calls[0]["episode_body"])
    assert "The owner likes mountain hiking" in str(fake.add_calls[0]["episode_body"])
    assert "untrusted caller content" not in str(fake.add_calls[0]["episode_body"])
    assert (await index.health())["ok"] is True
    assert fake.query_calls == ["RETURN 1 AS doppel_health"]


async def test_graphiti_writer_reconciles_transition_and_hard_delete() -> None:
    fake = FakeGraphiti()
    store = InMemoryStore()
    index = GraphitiSemanticIndex(store, graphiti_client=fake)
    scope = MemoryScope(user_id="maintenance", agent_id="bot")
    active = MemoryRecord(memory_id="active", scope=scope, content="keep me")
    inactive = MemoryRecord(memory_id="inactive", scope=scope, content="expire me")
    orphan = MemoryRecord(memory_id="orphan", scope=scope, content="delete me")
    for record in (active, inactive, orphan):
        assert (await store.put(record)).accepted
        assert (await index.index_record(record)).status == IndexOperationStatus.INDEXED
    await store.forget(scope, inactive.memory_id)
    await store.forget(scope, orphan.memory_id, hard=True)

    maintainer = IndexMaintainer(store, index)
    first = await maintainer.reconcile(scope, page_size=10)
    assert first.ok
    assert first.phase == IndexMaintenancePhase.RECORDS
    assert first.deleted == 1
    assert first.committable_checkpoint is not None

    second = await maintainer.reconcile(
        scope, checkpoint=first.committable_checkpoint, page_size=10
    )
    assert second.ok and second.complete
    assert second.phase == IndexMaintenancePhase.ENTRIES
    assert second.deleted == 1
    assert await index.inspect(scope, active.memory_id) is not None
    assert await index.inspect(scope, inactive.memory_id) is None
    assert await index.inspect(scope, orphan.memory_id) is None


async def test_graphiti_upsert_replaces_legacy_fingerprintless_episode() -> None:
    fake = FakeGraphiti()
    store = InMemoryStore()
    index = GraphitiSemanticIndex(store, graphiti_client=fake)
    scope = MemoryScope(user_id="legacy", agent_id="bot")
    record = MemoryRecord(memory_id="legacy", scope=scope, content="upgrade me")
    assert (await store.put(record)).accepted
    created = await index.index_record(record)
    fake.episodes[created.episode_id].name = "DoppelMemory:v1:bGVnYWN5"

    upgraded = await index.index_record(record)

    assert upgraded.status == IndexOperationStatus.INDEXED
    assert fake.remove_calls == [created.episode_id]
    assert len(fake.add_calls) == 2
    inspected = await index.inspect(scope, record.memory_id)
    assert inspected is not None
    assert inspected.fingerprint == upgraded.fingerprint


async def test_semantic_search_drops_unknown_scopes_and_maps_provenance() -> None:
    scope = MemoryScope(
        user_id="u",
        agent_id="bot",
        platform="test",
        chat_type="private",
        chat_id="allowed",
    )
    now = datetime.now(UTC)
    fake = FakeGraphiti()
    store = InMemoryStore()
    index = GraphitiSemanticIndex(store, graphiti_client=fake)
    active = MemoryRecord(
        memory_id="source-active",
        scope=scope,
        content="The owner enjoys hiking",
    )
    stale = MemoryRecord(
        memory_id="source-inactive",
        scope=scope,
        content="An inactive graph source",
    )
    deleted = MemoryRecord(
        memory_id="source-deleted",
        scope=scope,
        content="A deleted graph source",
    )
    assert (await store.put(active)).accepted
    assert (await store.put(stale)).accepted
    assert (await store.put(deleted)).accepted
    active_episode = await index.index_record(active)
    stale_episode = await index.index_record(stale)
    deleted_episode = await index.index_record(deleted)
    assert await store.forget(scope, stale.memory_id)
    assert await store.forget(scope, deleted.memory_id, hard=True)
    fake.edges = [
        SimpleNamespace(
            fact="The owner enjoys hiking",
            group_id=scope.scope_key,
            uuid="edge-1",
            episodes=[active_episode.episode_id],
            created_at=now,
            valid_at=now - timedelta(days=1),
            reference_time=None,
            invalid_at=None,
            expired_at=None,
        ),
        SimpleNamespace(
            fact="must never leak",
            group_id="different-scope",
            uuid="edge-leak",
            episodes=[active_episode.episode_id],
            created_at=now,
            valid_at=now,
            reference_time=None,
            invalid_at=None,
            expired_at=None,
        ),
        SimpleNamespace(
            fact="an invalidated fact",
            group_id=scope.scope_key,
            uuid="edge-expired",
            episodes=[active_episode.episode_id],
            created_at=now,
            valid_at=now - timedelta(days=2),
            reference_time=None,
            invalid_at=now - timedelta(hours=1),
            expired_at=None,
        ),
        SimpleNamespace(
            fact="must disappear after authoritative expiration",
            group_id=scope.scope_key,
            uuid="edge-stale",
            episodes=[stale_episode.episode_id],
            created_at=now,
            valid_at=now,
            reference_time=None,
            invalid_at=None,
            expired_at=None,
        ),
        SimpleNamespace(
            fact="must disappear after authoritative deletion",
            group_id=scope.scope_key,
            uuid="edge-deleted",
            episodes=[deleted_episode.episode_id],
            created_at=now,
            valid_at=now,
            reference_time=None,
            invalid_at=None,
            expired_at=None,
        ),
    ]

    hits = await index.search("outdoor activity", [scope])

    assert [hit.memory_id for hit in hits] == ["edge-1"]
    assert hits[0].scope == scope
    assert hits[0].source_episode == active_episode.episode_id
    assert hits[0].extractor == "graphiti"
    assert hits[0].derived_chain == ["graphiti:0.29"]
    assert fake.search_calls[0]["group_ids"] == [scope.scope_key]


async def test_semantic_index_rejects_filters_it_cannot_prove() -> None:
    scope = MemoryScope(user_id="u", agent_id="bot")
    index = GraphitiSemanticIndex(InMemoryStore(), graphiti_client=FakeGraphiti())

    with pytest.raises(GraphitiFilterUnsupportedError, match="tags"):
        await index.search("query", [scope], filters=MemoryFilter(tags={"private"}))


async def test_graphiti_outage_can_explicitly_fall_back_to_core_store() -> None:
    scope = MemoryScope(user_id="u", agent_id="bot")
    store = InMemoryStore()
    await store.write_background(scope, "literal fallback memory")
    index = GraphitiSemanticIndex(
        store,
        graphiti_client=FakeGraphiti(error=TimeoutError("neo4j unavailable")),
    )
    strategy = HybridRetrievalStrategy(index, fallback_to_lexical=True)

    hits = await Retriever(store, strategy=strategy).recall("literal fallback", [scope])

    assert [hit.fact for hit in hits] == ["literal fallback memory"]
    with pytest.raises(GraphitiIndexUnavailableError, match="neo4j unavailable"):
        await index.search("query", [scope])
