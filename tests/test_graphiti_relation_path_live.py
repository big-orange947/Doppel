"""Opt-in live Neo4j contract tests for bounded Graphiti relation paths."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

neo4j = pytest.importorskip("neo4j")

from doppel_memory import InMemoryStore, MemoryFilter, MemoryRecord, MemoryScope
from doppel_memory.graphiti_store import (
    GraphitiRelationIndex,
    _graph_query_records,
    _graphiti_episode_name,
)
from doppel_memory.relation import RelationPathQuery, RelationPathStep

pytestmark = pytest.mark.skipif(
    os.environ.get("DOPPEL_LIVE_NEO4J") != "1",
    reason="set DOPPEL_LIVE_NEO4J=1 for the disposable live Neo4j fixture",
)


class _LiveGraphClient:
    """Minimal Graphiti-shaped client; no LLM or embedding provider is constructed."""

    def __init__(self, driver) -> None:
        self.driver = driver

    async def get_episodes_by_uuids(self, episode_ids):
        result = await self.driver.execute_query(
            "MATCH (episode) WHERE episode.uuid IN $episode_ids "
            "RETURN episode.uuid AS uuid, episode.name AS name, "
            "episode.group_id AS group_id",
            episode_ids=list(episode_ids),
        )
        return [
            SimpleNamespace(
                uuid=str(row["uuid"] or ""),
                name=str(row["name"] or ""),
                group_id=str(row["group_id"] or ""),
            )
            for row in _graph_query_records(result)
        ]


async def test_live_neo4j_bounded_paths_revalidate_every_hop() -> None:
    uri = os.environ.get("DOPPEL_NEO4J_URI", "bolt://127.0.0.1:7687")
    user = os.environ.get("DOPPEL_NEO4J_USER", "neo4j")
    password = os.environ.get("DOPPEL_NEO4J_PASSWORD", "")
    if not password:
        pytest.fail("DOPPEL_NEO4J_PASSWORD is required for the live test")

    run_id = f"doppel-path-live-{uuid4().hex}"
    scope = MemoryScope(user_id=f"{run_id}-owner", agent_id="test-agent")
    foreign_scope = MemoryScope(
        user_id=f"{run_id}-foreign-owner", agent_id="test-agent"
    )
    fixture_groups = [scope.scope_key, foreign_scope.scope_key]
    driver = neo4j.AsyncGraphDatabase.driver(uri, auth=(user, password))
    store = InMemoryStore()
    client = _LiveGraphClient(driver)
    relation = GraphitiRelationIndex(store, graphiti_client=client)
    cleaned = False

    async def put_record(
        memory_id: str,
        content: str,
        *,
        record_scope: MemoryScope = scope,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
    ) -> str:
        metadata: dict[str, object] = {
            "subject": "owner",
            "subject_id": record_scope.user_id,
            "evidence": [{"evidence_id": f"evidence-{memory_id}"}],
        }
        if valid_from is not None:
            metadata["valid_from"] = valid_from.isoformat()
        if valid_to is not None:
            metadata["valid_to"] = valid_to.isoformat()
        record = MemoryRecord(
            memory_id=memory_id,
            scope=record_scope,
            content=content,
            tags=["personal-memory"],
            metadata=metadata,
        )
        assert (await store.put(record)).accepted
        return _graphiti_episode_name(memory_id, "a" * 64, record.version)

    january = datetime(2026, 1, 1, tzinfo=UTC)
    july = datetime(2026, 7, 1, tzinfo=UTC)
    august = datetime(2026, 8, 1, tzinfo=UTC)
    march = datetime(2026, 3, 1, tzinfo=UTC)
    held_name = await put_record("live-held", "相机由小王保管。", valid_from=january)
    location_name = await put_record(
        "live-location", "小王目前在上海。", valid_from=july
    )
    foreign_held_name = await put_record(
        "foreign-held",
        "相机由另一位小王保管。",
        record_scope=foreign_scope,
        valid_from=january,
    )
    foreign_location_name = await put_record(
        "foreign-location",
        "另一位小王目前在广州。",
        record_scope=foreign_scope,
        valid_from=january,
    )
    episode_ids = {
        "held": f"{run_id}-episode-held",
        "location": f"{run_id}-episode-location",
        "foreign-held": f"{run_id}-episode-foreign-held",
        "foreign-location": f"{run_id}-episode-foreign-location",
    }
    nodes = [
        {
            "uuid": f"{run_id}-camera",
            "name": "相机",
            "group_id": scope.scope_key,
        },
        {
            "uuid": f"{run_id}-wang",
            "name": "小王",
            "group_id": scope.scope_key,
        },
        {
            "uuid": f"{run_id}-shanghai",
            "name": "上海",
            "group_id": scope.scope_key,
        },
        {
            "uuid": f"{run_id}-passport",
            "name": "护照",
            "group_id": scope.scope_key,
        },
        {
            "uuid": f"{run_id}-li",
            "name": "小李",
            "group_id": scope.scope_key,
        },
        {
            "uuid": f"{run_id}-beijing",
            "name": "北京",
            "group_id": scope.scope_key,
        },
        {
            "uuid": f"{run_id}-foreign-camera",
            "name": "相机",
            "group_id": foreign_scope.scope_key,
        },
        {
            "uuid": f"{run_id}-foreign-wang",
            "name": "另一位小王",
            "group_id": foreign_scope.scope_key,
        },
        {
            "uuid": f"{run_id}-guangzhou",
            "name": "广州",
            "group_id": foreign_scope.scope_key,
        },
    ]
    episodes = [
        {
            "uuid": episode_ids["held"],
            "name": held_name,
            "group_id": scope.scope_key,
        },
        {
            "uuid": episode_ids["location"],
            "name": location_name,
            "group_id": scope.scope_key,
        },
        {
            "uuid": episode_ids["foreign-held"],
            "name": foreign_held_name,
            "group_id": foreign_scope.scope_key,
        },
        {
            "uuid": episode_ids["foreign-location"],
            "name": foreign_location_name,
            "group_id": foreign_scope.scope_key,
        },
    ]
    edges = [
        {
            "source_uuid": f"{run_id}-camera",
            "target_uuid": f"{run_id}-wang",
            "group_id": scope.scope_key,
            "uuid": f"{run_id}-edge-held",
            "name": "HELD_BY",
            "fact": "相机由小王保管。",
            "episodes": [episode_ids["held"]],
            "valid_at": january,
            "invalid_at": None,
            "created_at": january,
        },
        {
            "source_uuid": f"{run_id}-wang",
            "target_uuid": f"{run_id}-shanghai",
            "group_id": scope.scope_key,
            "uuid": f"{run_id}-edge-location",
            "name": "LOCATED_AT",
            "fact": "小王目前在上海。",
            "episodes": [episode_ids["location"]],
            "valid_at": july,
            "invalid_at": None,
            "created_at": july,
        },
        {
            "source_uuid": f"{run_id}-passport",
            "target_uuid": f"{run_id}-li",
            "group_id": scope.scope_key,
            "uuid": f"{run_id}-edge-orphan-held",
            "name": "HELD_BY",
            "fact": "护照由小李保管。",
            "episodes": [f"{run_id}-missing-held"],
            "valid_at": january,
            "invalid_at": None,
            "created_at": january,
        },
        {
            "source_uuid": f"{run_id}-li",
            "target_uuid": f"{run_id}-beijing",
            "group_id": scope.scope_key,
            "uuid": f"{run_id}-edge-orphan-location",
            "name": "LOCATED_AT",
            "fact": "小李目前在北京。",
            "episodes": [f"{run_id}-missing-location"],
            "valid_at": january,
            "invalid_at": None,
            "created_at": january,
        },
        {
            "source_uuid": f"{run_id}-foreign-camera",
            "target_uuid": f"{run_id}-foreign-wang",
            "group_id": foreign_scope.scope_key,
            "uuid": f"{run_id}-edge-foreign-held",
            "name": "HELD_BY",
            "fact": "相机由另一位小王保管。",
            "episodes": [episode_ids["foreign-held"]],
            "valid_at": january,
            "invalid_at": None,
            "created_at": january,
        },
        {
            "source_uuid": f"{run_id}-foreign-wang",
            "target_uuid": f"{run_id}-guangzhou",
            "group_id": foreign_scope.scope_key,
            "uuid": f"{run_id}-edge-foreign-location",
            "name": "LOCATED_AT",
            "fact": "另一位小王目前在广州。",
            "episodes": [episode_ids["foreign-location"]],
            "valid_at": january,
            "invalid_at": None,
            "created_at": january,
        },
    ]

    try:
        await driver.verify_connectivity()
        await driver.execute_query(
            "UNWIND $nodes AS item CREATE (:Entity {uuid: item.uuid, "
            "name: item.name, group_id: item.group_id})",
            nodes=nodes,
        )
        await driver.execute_query(
            "UNWIND $episodes AS item CREATE (:Episodic {uuid: item.uuid, "
            "name: item.name, group_id: item.group_id})",
            episodes=episodes,
        )
        await driver.execute_query(
            "UNWIND $edges AS item "
            "MATCH (source:Entity {uuid: item.source_uuid, group_id: item.group_id}) "
            "MATCH (target:Entity {uuid: item.target_uuid, group_id: item.group_id}) "
            "CREATE (source)-[edge:RELATES_TO]->(target) "
            "SET edge.group_id = item.group_id, edge.uuid = item.uuid, "
            "edge.name = item.name, edge.fact = item.fact, "
            "edge.episodes = item.episodes, edge.valid_at = item.valid_at, "
            "edge.invalid_at = item.invalid_at, edge.created_at = item.created_at",
            edges=edges,
        )
        two_hop = RelationPathQuery(
            query_text="相机现在在哪里？",
            entity_mentions=["相机"],
            steps=[
                RelationPathStep(relation_types=["HELD_BY"]),
                RelationPathStep(relation_types=["LOCATED_AT"]),
            ],
            subject="owner",
            subject_id=scope.user_id,
            valid_at=august,
        )
        candidates = await relation.search_relation_paths(
            two_hop,
            [scope],
            filters=MemoryFilter(tags={"personal-memory"}),
            limit=10,
        )
        assert len(candidates) == 1
        assert candidates[0].start_entity_name == "相机"
        assert candidates[0].end_entity_name == "上海"
        assert candidates[0].supporting_memory_ids == ["live-held", "live-location"]
        assert [hop.direction for hop in candidates[0].hops] == [
            "outbound",
            "outbound",
        ]

        one_hop = two_hop.model_copy(update={"steps": two_hop.steps[:1]})
        one_hop_candidates = await relation.search_relation_paths(
            one_hop,
            [scope],
            filters=MemoryFilter(tags={"personal-memory"}),
            limit=10,
        )
        assert len(one_hop_candidates) == 1
        assert one_hop_candidates[0].end_entity_name == "小王"
        assert one_hop_candidates[0].supporting_memory_ids == ["live-held"]

        wrong_direction = two_hop.model_copy(
            update={
                "steps": [
                    RelationPathStep(relation_types=["HELD_BY"]),
                    RelationPathStep(
                        relation_types=["LOCATED_AT"], direction="inbound"
                    ),
                ]
            }
        )
        assert (
            await relation.search_relation_paths(wrong_direction, [scope], limit=10)
            == []
        )

        before_location_started = two_hop.model_copy(update={"valid_at": march})
        assert (
            await relation.search_relation_paths(
                before_location_started, [scope], limit=10
            )
            == []
        )

        orphan = two_hop.model_copy(
            update={"query_text": "护照现在在哪里？", "entity_mentions": ["护照"]}
        )
        assert await relation.search_relation_paths(orphan, [scope], limit=10) == []
        assert all(
            candidate.scope.scope_key == scope.scope_key for candidate in candidates
        )
        assert all(candidate.end_entity_name != "广州" for candidate in candidates)
    finally:
        try:
            await driver.execute_query(
                "MATCH (node) WHERE node.group_id IN $group_ids DETACH DELETE node",
                group_ids=fixture_groups,
            )
            remaining = await driver.execute_query(
                "MATCH (node) WHERE node.group_id IN $group_ids "
                "RETURN count(node) AS remaining",
                group_ids=fixture_groups,
            )
            rows = _graph_query_records(remaining)
            cleaned = bool(rows and int(rows[0]["remaining"] or 0) == 0)
        finally:
            await driver.close()

    assert cleaned is True
