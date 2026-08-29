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


async def test_graphiti_upsert_replaces_pre_temporal_projection_episode() -> None:
    fake = FakeGraphiti()
    store = InMemoryStore()
    index = GraphitiSemanticIndex(store, graphiti_client=fake)
    scope = MemoryScope(user_id="legacy", agent_id="bot")
    record = MemoryRecord(memory_id="legacy", scope=scope, content="upgrade me")
    assert (await store.put(record)).accepted
    created = await index.index_record(record)
    fake.episodes[created.episode_id].name = (
        f"DoppelMemory:v2:bGVnYWN5:{created.fingerprint}:1"
    )

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

    assert [hit.memory_id for hit in hits] == ["source-active"]
    assert hits[0].scope == scope
    assert hits[0].fact == active.content
    assert hits[0].raw_text == "The owner enjoys hiking"
    assert hits[0].source_episode == active_episode.episode_id
    assert hits[0].extractor == "graphiti"
    assert hits[0].derived_chain == [
        "graphiti:0.29",
        "graphiti-edge:edge-1",
    ]
    assert hits[0].similarity == 1.0
    assert fake.search_calls[0]["group_ids"] == [scope.scope_key]


async def test_semantic_index_revalidates_all_filters_against_core_records() -> None:
    scope = MemoryScope(user_id="u", agent_id="bot")
    store = InMemoryStore()
    fake = FakeGraphiti()
    index = GraphitiSemanticIndex(store, graphiti_client=fake)
    private = MemoryRecord(
        memory_id="private",
        scope=scope,
        content="private source",
        tags=["private"],
        importance=0.9,
    )
    public = MemoryRecord(
        memory_id="public",
        scope=scope,
        content="public source",
        tags=["public"],
        importance=0.2,
    )
    for record in (private, public):
        assert (await store.put(record)).accepted
    private_episode = await index.index_record(private)
    public_episode = await index.index_record(public)
    fake.edges = [
        SimpleNamespace(
            fact="private graph fact",
            group_id=scope.scope_key,
            uuid="private-edge",
            episodes=[private_episode.episode_id],
        ),
        SimpleNamespace(
            fact="public graph fact",
            group_id=scope.scope_key,
            uuid="public-edge",
            episodes=[public_episode.episode_id],
        ),
    ]

    hits = await index.search(
        "query",
        [scope],
        filters=MemoryFilter(tags={"private"}, importance_min=0.8),
    )

    assert [hit.memory_id for hit in hits] == ["private"]


async def test_graphiti_projection_and_search_at_preserve_temporal_coordinates() -> (
    None
):
    scope = MemoryScope(user_id="temporal", agent_id="bot")
    store = InMemoryStore()
    fake = FakeGraphiti()
    index = GraphitiSemanticIndex(store, graphiti_client=fake)
    observed_at = datetime(2026, 3, 1, 8, tzinfo=UTC)
    valid_from = datetime(2026, 3, 2, tzinfo=UTC)
    valid_to = datetime(2026, 5, 2, tzinfo=UTC)
    record = MemoryRecord(
        memory_id="temporary-state",
        scope=scope,
        content="用户临时在异地居住两个月。",
        tags=["personal-memory", "state"],
        created_at=observed_at,
        updated_at=observed_at,
        metadata={
            "temporal_status": "current",
            "valid_from": valid_from.isoformat(),
            "valid_to": valid_to.isoformat(),
            "evidence": [{"evidence_id": "m1", "at": observed_at.isoformat()}],
        },
    )
    assert (await store.put(record)).accepted

    indexed = await index.index_record(record)

    call = fake.add_calls[0]
    assert call["reference_time"] == observed_at
    assert '"temporal_status": "current"' in str(call["episode_body"])
    assert f'"valid_from": "{valid_from.isoformat()}"' in str(
        call["episode_body"]
    )
    assert f'"valid_to": "{valid_to.isoformat()}"' in str(call["episode_body"])
    assert "trusted temporal metadata" in str(
        call["custom_extraction_instructions"]
    )

    fake.edges = [
        SimpleNamespace(
            fact="temporary graph fact",
            group_id=scope.scope_key,
            uuid="temporal-edge",
            episodes=[indexed.episode_id],
            valid_at=valid_from,
        )
    ]
    as_of = datetime(2026, 4, 1, tzinfo=UTC)
    hits = await index.search_at("当时住哪", [scope], valid_at=as_of)

    assert [hit.memory_id for hit in hits] == [record.memory_id]
    assert hits[0].valid_at == valid_from
    search_filter = fake.search_calls[0]["search_filter"]
    assert search_filter.valid_at[0][0].date == as_of
    assert search_filter.invalid_at[0][0].date == as_of
    assert search_filter.expired_at[0][0].date == as_of

    expired_hits = await index.search_at(
        "后来还住那里吗",
        [scope],
        valid_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    assert expired_hits == []


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
