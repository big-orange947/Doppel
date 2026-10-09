"""Real query-engine composition with synthetic backends; no quality claims."""

from datetime import UTC, datetime

import pytest

from doppel_memory.high_config import HighConfigRetrieval
from doppel_memory.in_memory_store import InMemoryStore
from doppel_memory.models import (
    Actor,
    ChatMessage,
    FactAuthority,
    MemoryIsolationError,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    RecallResult,
)
from doppel_memory.query import PersonalMemoryQueryPlanningError
from doppel_memory.query_path import PersonalMemoryRelationPathDraftV4
from doppel_memory.relation import (
    RelationPathCandidate,
    RelationPathHop,
    RelationTypeDefinition,
)

NOW = datetime(2026, 10, 9, tzinfo=UTC)
SCOPE = MemoryScope(user_id="owner", agent_id="agent")
OTHER = MemoryScope(user_id="other", agent_id="agent")


class Planner:
    name, version = "synthetic-path-planner", "1"

    def __init__(self, **updates):
        self.calls = []
        self.updates = updates

    async def plan(self, request):
        self.calls.append(request)
        return PersonalMemoryRelationPathDraftV4(
            **{
                "operation": "lookup",
                "temporal_view": "unbounded",
                "search_text": request.query,
                "entity_mentions": ["camera"],
                "subject": request.default_subject,
                "subject_id": request.default_subject_id,
                "path_decision": "abstain",
                "path_reason": "nonrelation",
                **self.updates,
            }
        )


class Scorer:
    name, version = "synthetic-scorer", "1"

    def __init__(self, broken=False):
        self.broken = broken

    async def rerank(self, request):
        if self.broken:
            raise RuntimeError("SECRET")
        return [{"item_id": item.item_id, "score": 0.9} for item in request.items]


class Index:
    def __init__(self, store):
        self.store = store
        self.paths = []
        self.exploration = []
        self.calls = []
        self.foreign_raw = False

    async def search(self, query, scopes, *, filters=None, limit=10):
        self.calls.append(("vector", scopes, filters))
        records = []
        for scope in scopes:
            page = await self.store.scan(scope, filters=filters, limit=200)
            records.extend(page.records)
        result = [
            RecallResult(
                memory_id=r.memory_id,
                scope=r.scope,
                fact="UNTRUSTED INDEX TEXT",
                similarity=0.9,
            )
            for r in records
        ][:limit]
        if self.foreign_raw and filters.kinds:
            return [
                RecallResult(
                    scope=OTHER, memory_id="foreign", fact="foreign", similarity=0.9
                )
            ]
        return result

    async def search_relations(self, request, scopes, *, filters=None, limit=10):
        self.calls.append(("relation", request))
        return []

    async def search_relation_paths(self, request, scopes, *, filters=None, limit=10):
        self.calls.append(("path", request))
        return self.paths

    async def explore_relation_paths(self, request, scopes, *, filters=None, limit=10):
        self.calls.append(("explore", request))
        return self.exploration


class Resolver:
    def __init__(self, store, mapping):
        self.store, self.mapping = store, mapping

    async def resolve_event(self, scope, evidence_id):
        return (
            await self.store.get(scope, self.mapping[evidence_id])
            if evidence_id in self.mapping
            else None
        )


def path(memory_id="memory", scope=SCOPE):
    return RelationPathCandidate(
        scope=scope,
        source="synthetic",
        score=0.9,
        path_id="path",
        start_entity_id="camera",
        end_entity_id="owner",
        supporting_memory_ids=[memory_id],
        hops=[
            RelationPathHop(
                position=0,
                relation_type="OWNS",
                direction="outbound",
                source_entity_id="camera",
                target_entity_id="owner",
                edge_id="edge",
                episode_ids=["episode"],
                memory_ids=[memory_id],
                fact="camera owned by owner",
            )
        ],
    )


async def setup(**planner_updates):
    store = InMemoryStore()
    mapping = {}
    for actor, event in [(Actor.OWNER, "user-event"), (Actor.AGENT, "agent-event")]:
        written = await store.write_event(
            SCOPE,
            ChatMessage(
                event_id=event,
                actor=actor,
                text="camera source " + actor,
                sender_id=actor,
                at=NOW,
            ),
        )
        mapping[event] = written.memory_id
    await store.put(
        MemoryRecord(
            memory_id="memory",
            scope=SCOPE,
            content="camera owned by owner",
            actor=Actor.OWNER,
            authority=FactAuthority.HUMAN_SELF,
            state=MemoryState.CONFIRMED,
            tags={"personal-memory"},
            created_at=NOW,
            metadata={
                "subject": Actor.OWNER,
                "subject_id": SCOPE.user_id,
                "personal_memory_type": "profile",
                "temporal_status": "current",
                "evidence": [{"evidence_id": "user-event"}],
            },
        )
    )
    planner, index, scorer = Planner(**planner_updates), Index(store), Scorer()
    host = HighConfigRetrieval(
        store,
        semantic_index=index,
        relation_index=index,
        path_index=index,
        exploration_index=index,
        planner=planner,
        memory_reranker=scorer,
        path_reranker=scorer,
        source_resolver=Resolver(store, mapping),
        relation_definitions=[
            RelationTypeDefinition(
                name="OWNS",
                description="An entity owns an object",
                source_description="owner",
                target_description="object",
            )
        ],
    )
    return host, planner, index, store, mapping


@pytest.mark.asyncio
async def test_real_engine_plan_once_raw_assistant_and_source_backing():
    host, planner, _index, store, _ = await setup()
    before = store._records.copy()
    result = await host.query("camera", [SCOPE], now=NOW, trace_limit=100)
    assert len(planner.calls) == 1
    assert result.base.plan.planner == planner.name
    assert [h.record.memory_id for h in result.base.hits] == ["memory"]
    assert {r.actor for r in result.raw_dialogue} == {Actor.OWNER, Actor.AGENT}
    assert (
        next(r for r in result.raw_dialogue if r.actor == Actor.AGENT).authority
        == FactAuthority.AGENT_OUTPUT
    )
    assert [r.source_event_id for r in result.backing_sources] == ["user-event"]
    assert "UNTRUSTED INDEX TEXT" not in result.model_dump_json()
    assert result.graph_exploration_searches == 1
    assert not result.index_coverage_certified
    assert store._records == before


@pytest.mark.asyncio
async def test_current_time_sent_to_graph_and_stale_path_removed():
    host, _, index, store, _ = await setup(temporal_view="current")
    index.exploration = [path()]
    result = await host.query("camera", [SCOPE], now=NOW)
    assert next(call[1] for call in index.calls if call[0] == "explore").valid_at == NOW
    assert result.hybrid.assembly.relation_paths
    old = await store.get(SCOPE, "memory")
    store._records["memory"] = old.model_copy(
        update={
            "metadata": {**old.metadata, "valid_to": "2026-01-01T00:00:00Z"},
        }
    )
    result = await host.query("camera", [SCOPE], now=NOW)
    assert result.rejected_paths == 1
    assert not result.hybrid.assembly.candidates


@pytest.mark.asyncio
@pytest.mark.parametrize("view", ["current", "unbounded", "as_of"])
async def test_future_observation_cannot_enter_via_graph_exploration(view):
    from datetime import timedelta

    updates = {"temporal_view": view}
    if view == "as_of":
        updates["as_of"] = datetime(2026, 1, 1, tzinfo=UTC)
    host, _, index, store, _ = await setup(**updates)
    old = await store.get(SCOPE, "memory")
    store._records["memory"] = old.model_copy(
        update={
            "created_at": NOW + timedelta(seconds=1),
            "metadata": {**old.metadata, "valid_from": "2025-01-01T00:00:00Z"},
        }
    )
    # A stale graph deliberately ignores the coarse observed-time filter.
    index.exploration = [path()]
    result = await host.query("camera", [SCOPE], now=NOW)
    assert not result.base.hits
    assert result.rejected_paths == 1
    assert not result.hybrid.assembly.candidates
    assert not result.hybrid.promoted_path_hits
    assert not result.backing_sources
    assert result.source_failures == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["raw", "path"])
async def test_cross_scope_candidates_fail_closed(channel):
    host, _, index, _, _ = await setup()
    index.foreign_raw = channel == "raw"
    index.exploration = [path(scope=OTHER)] if channel == "path" else []
    with pytest.raises(MemoryIsolationError):
        await host.query("camera", [SCOPE], now=NOW)


@pytest.mark.asyncio
async def test_wrong_subject_path_not_promoted_to_owner():
    host, _, index, store, _ = await setup()
    old = await store.get(SCOPE, "memory")
    store._records["memory"] = old.model_copy(
        update={
            "metadata": {**old.metadata, "subject_id": "someone-else"},
        }
    )
    index.exploration = [path()]
    result = await host.query("camera", [SCOPE], now=NOW)
    assert result.rejected_paths == 1
    assert not result.hybrid.assembly.candidates


@pytest.mark.asyncio
async def test_exact_path_and_exploration_are_consumed_once():
    host, _, index, _, _ = await setup(
        path_decision="execute",
        path_reason="exact",
        path_confidence=0.9,
        path_steps=[{"relation_types": ["OWNS"], "direction": "outbound"}],
    )
    index.paths = index.exploration = [path()]
    result = await host.query("camera", [SCOPE], now=NOW)
    assert result.graph_path_searches == result.graph_exploration_searches == 1
    assert len(result.hybrid.promoted_path_hits) == 1


@pytest.mark.asyncio
async def test_source_mapping_is_not_an_authority():
    host, _, _, _, mapping = await setup()
    mapping["user-event"] = mapping["agent-event"]
    result = await host.query("camera", [SCOPE], now=NOW)
    assert result.source_failures == 1
    assert not result.backing_sources
    assert "source_backing_incomplete" in result.warnings


@pytest.mark.asyncio
async def test_degradation_visible_and_secret_redacted():
    host, _, index, _, _ = await setup()
    host.memory_reranker = Scorer(broken=True)
    host.path_reranker = Scorer(broken=True)
    index.exploration = [path()]
    result = await host.query("camera", [SCOPE], now=NOW)
    assert "raw_reranker_degraded" in result.warnings
    assert "path_reranker_degraded" in result.warnings
    assert "SECRET" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_count_preserves_engine_count_without_top_k_graph():
    host, _, index, _, _ = await setup(operation="count")
    result = await host.query("camera", [SCOPE], now=NOW)
    assert result.base.count.status != "not_requested"
    assert result.hybrid is None
    assert result.graph_exploration_searches == result.graph_path_searches == 0
    assert not any(call[0] in {"path", "explore"} for call in index.calls)


@pytest.mark.asyncio
async def test_invalid_planner_subject_cannot_widen_authority():
    host, _, index, _, _ = await setup(subject_id="another-owner")
    with pytest.raises(PersonalMemoryQueryPlanningError):
        await host.query("camera", [SCOPE], now=NOW)
    assert not index.calls


@pytest.mark.asyncio
async def test_graph_edge_validity_rechecked_even_when_memory_is_current():
    host, _, index, _, _ = await setup(temporal_view="current")
    candidate = path()
    index.exploration = [
        candidate.model_copy(
            update={
                "hops": [
                    candidate.hops[0].model_copy(
                        update={"invalid_at": datetime(2025, 1, 1, tzinfo=UTC)}
                    )
                ]
            }
        )
    ]
    result = await host.query("camera", [SCOPE], now=NOW)
    assert result.rejected_paths == 1
    assert not result.hybrid.assembly.relation_paths


@pytest.mark.asyncio
async def test_missing_graph_backend_is_not_silently_a_high_config_run():
    host, _, index, _, _ = await setup()

    async def unavailable(*args, **kwargs):
        raise RuntimeError("graph unavailable")

    index.explore_relation_paths = unavailable
    with pytest.raises(RuntimeError, match="graph unavailable"):
        await host.query("camera", [SCOPE], now=NOW)
