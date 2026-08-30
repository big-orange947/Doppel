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
    GRAPHITI_FALLBACK_EDGE_NAME,
    GraphitiIndexUnavailableError,
    GraphitiMemoryStore,
    GraphitiSemanticIndex,
    _ensure_graphiti_fallback_edge,
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


class _EpisodeSlotOperations:
    def __init__(self, graphiti: FakeGraphiti) -> None:
        self.graphiti = graphiti
        self.saved: list[object] = []

    async def episodic_node_save(self, node, driver):
        self.saved.append(node)
        self.graphiti.episodes[node.uuid] = SimpleNamespace(
            uuid=node.uuid,
            name=node.name,
            group_id=node.group_id,
        )


class _EpisodeSlotDriver:
    def __init__(self, graphiti: FakeGraphiti) -> None:
        self.graphiti = graphiti
        self.graph_operations_interface = _EpisodeSlotOperations(graphiti)

    async def execute_query(self, query: str):
        self.graphiti.query_calls.append(query)
        return []


class _FallbackEmbedder:
    async def create(self, value):
        return [float(len(str(value)))]


class _FallbackDriver:
    def __init__(self, *, existing_edges: int = 0) -> None:
        self.existing_edges = existing_edges
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def execute_query(self, query: str, **params):
        self.calls.append((query, params))
        if "RETURN count(edge) AS edges" in query:
            return SimpleNamespace(records=[{"edges": self.existing_edges}])
        return SimpleNamespace(records=[{"edge_uuid": params["edge_uuid"]}])


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
    assert '"entity_name": "DoppelSubject-' in str(
        fake.add_calls[0]["episode_body"]
    )
    assert "The owner likes mountain hiking" in str(fake.add_calls[0]["episode_body"])
    assert "untrusted caller content" not in str(fake.add_calls[0]["episode_body"])
    assert (await index.health())["ok"] is True
    assert fake.query_calls == ["RETURN 1 AS doppel_health"]


async def test_graphiti_first_index_precreates_stable_episode_slot() -> None:
    fake = FakeGraphiti()
    fake.driver = _EpisodeSlotDriver(fake)
    original_add = fake.add_episode

    async def require_existing_episode(**kwargs):
        assert kwargs["uuid"] in fake.episodes
        return await original_add(**kwargs)

    fake.add_episode = require_existing_episode
    store = InMemoryStore()
    index = GraphitiSemanticIndex(store, graphiti_client=fake)
    scope = MemoryScope(user_id="slot", agent_id="bot")
    record = MemoryRecord(memory_id="stable", scope=scope, content="stable slot")
    assert (await store.put(record)).accepted

    indexed = await index.index_record(record)

    saved = fake.driver.graph_operations_interface.saved
    assert len(saved) == 1
    assert saved[0].uuid == indexed.episode_id
    assert fake.add_calls[0]["uuid"] == indexed.episode_id
    assert await index.inspect(scope, record.memory_id) is not None


async def test_graphiti_failed_first_index_removes_incomplete_episode_slot() -> None:
    fake = FakeGraphiti()
    fake.driver = _EpisodeSlotDriver(fake)

    async def fail_after_precreation(**kwargs):
        assert kwargs["uuid"] in fake.episodes
        raise RuntimeError("synthetic extraction failure")

    fake.add_episode = fail_after_precreation
    store = InMemoryStore()
    index = GraphitiSemanticIndex(store, graphiti_client=fake)
    scope = MemoryScope(user_id="failed-slot", agent_id="bot")
    record = MemoryRecord(memory_id="retryable", scope=scope, content="retry me")
    assert (await store.put(record)).accepted

    with pytest.raises(GraphitiIndexUnavailableError, match="extraction failure"):
        await index.index_record(record)

    saved = fake.driver.graph_operations_interface.saved
    assert len(saved) == 1
    assert fake.remove_calls == [saved[0].uuid]
    assert saved[0].uuid not in fake.episodes
    assert await index.inspect(scope, record.memory_id) is None


async def test_graphiti_failed_slot_precreation_removes_partial_episode() -> None:
    fake = FakeGraphiti()
    fake.driver = _EpisodeSlotDriver(fake)
    operations = fake.driver.graph_operations_interface

    async def fail_after_saving(node, driver):
        operations.saved.append(node)
        fake.episodes[node.uuid] = SimpleNamespace(uuid=node.uuid)
        raise RuntimeError("synthetic slot save failure")

    operations.episodic_node_save = fail_after_saving
    store = InMemoryStore()
    index = GraphitiSemanticIndex(store, graphiti_client=fake)
    scope = MemoryScope(user_id="partial-slot", agent_id="bot")
    record = MemoryRecord(memory_id="partial", scope=scope, content="retry me")
    assert (await store.put(record)).accepted

    with pytest.raises(GraphitiIndexUnavailableError, match="slot save failure"):
        await index.index_record(record)

    assert len(operations.saved) == 1
    assert fake.remove_calls == [operations.saved[0].uuid]
    assert operations.saved[0].uuid not in fake.episodes


async def test_graphiti_empty_extraction_gets_temporal_provenance_fallback() -> None:
    driver = _FallbackDriver()
    graphiti = SimpleNamespace(driver=driver, embedder=_FallbackEmbedder())
    scope = MemoryScope(user_id="private-platform-id", agent_id="bot")
    valid_from = datetime(2025, 4, 1, tzinfo=UTC)
    valid_to = datetime(2025, 4, 30, 23, 59, 59, tzinfo=UTC)
    record = MemoryRecord(
        memory_id="fallback",
        scope=scope,
        content="A confirmed memory that the provider did not relate",
        metadata={
            "subject": "owner",
            "subject_id": scope.user_id,
            "valid_from": valid_from.isoformat(),
            "valid_to": valid_to.isoformat(),
        },
    )

    created = await _ensure_graphiti_fallback_edge(
        graphiti,
        record=record,
        episode_id="episode-id",
        fingerprint="a" * 64,
    )

    assert created is True
    assert len(driver.calls) == 2
    create_query, params = driver.calls[1]
    assert "episode.entity_edges" in create_query
    assert params["edge_name"] == GRAPHITI_FALLBACK_EDGE_NAME
    assert params["valid_at"] == valid_from
    assert params["invalid_at"] == valid_to
    assert str(params["subject_name"]).startswith("DoppelSubject-")
    assert scope.user_id not in str(params)
    assert params["reference_time"] is not None


async def test_graphiti_existing_episode_edge_skips_fallback() -> None:
    driver = _FallbackDriver(existing_edges=1)
    graphiti = SimpleNamespace(driver=driver, embedder=_FallbackEmbedder())
    record = MemoryRecord(
        memory_id="rich",
        scope=MemoryScope(user_id="u", agent_id="bot"),
        content="The provider already produced a rich relation",
    )

    created = await _ensure_graphiti_fallback_edge(
        graphiti,
        record=record,
        episode_id="episode-id",
        fingerprint="b" * 64,
    )

    assert created is False
    assert len(driver.calls) == 1


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


@pytest.mark.parametrize("legacy_version", [2, 3, 4])
async def test_graphiti_upsert_replaces_legacy_projection_episode(
    legacy_version: int,
) -> None:
    fake = FakeGraphiti()
    store = InMemoryStore()
    index = GraphitiSemanticIndex(store, graphiti_client=fake)
    scope = MemoryScope(user_id="legacy", agent_id="bot")
    record = MemoryRecord(memory_id="legacy", scope=scope, content="upgrade me")
    assert (await store.put(record)).accepted
    created = await index.index_record(record)
    fake.episodes[created.episode_id].name = (
        f"DoppelMemory:v{legacy_version}:bGVnYWN5:{created.fingerprint}:1"
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
            "subject": "owner",
            "subject_id": "person-temporal",
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
    assert '"entity_name": "DoppelSubject-' in str(call["episode_body"])
    assert '"role": "owner"' in str(call["episode_body"])
    assert "person-temporal" not in str(call["episode_body"])
    assert "trusted temporal metadata" in str(
        call["custom_extraction_instructions"]
    )
    assert "trusted subject metadata" in str(
        call["custom_extraction_instructions"]
    )
    assert "never replace a subject-object relation with a self-loop" in str(
        call["custom_extraction_instructions"]
    )
    assert "For every episode, always include its entity_name" in str(
        call["custom_extraction_instructions"]
    )
    assert "negation, cancellation, retraction" in str(
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
