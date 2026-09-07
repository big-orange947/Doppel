"""Candidate union is an opt-in recall experiment, not an evidence judge."""
import pytest

from doppel_memory import InMemoryStore, MemoryState, RecallResult, RelationCandidate
from doppel_memory.query import PersonalMemoryQueryConfig, PersonalMemoryQueryEngine
from doppel_memory.relation import RelationIndexUnavailableError
from tests.test_query import (
    NOW,
    OTHER_SCOPE,
    SCOPE,
    _DraftPlanner,
    _FailingRelationIndex,
    _put,
    _record,
    _RelationIndex,
)


class Vector:
    async def search(self, query, scopes, *, filters=None, limit=10):
        return [RecallResult(fact="untrusted", memory_id=name, scope=scope, similarity=.95)
                for name, scope in [("vector", SCOPE), ("foreign", OTHER_SCOPE),
                                    ("orphan", SCOPE), ("rejected", SCOPE)]]


class RecordingVector:
    def __init__(self):
        self.queries = []

    async def search(self, query, scopes, *, filters=None, limit=10):
        del filters, limit
        self.queries.append(query)
        return [RecallResult(
            fact="untrusted", memory_id="vector", scope=scopes[0], similarity=.95,
        )]


async def setup():
    store = InMemoryStore()
    for name in ["vector", "relation", "rejected"]:
        await _put(store, _record(
            name, "unrelated wording", memory_type="fact", temporal_status="current",
            day=1, state=MemoryState.REJECTED if name == "rejected" else MemoryState.CONFIRMED,
        ))
    relation = _RelationIndex([RelationCandidate(
        scope=SCOPE, memory_id="relation", source="graphiti_relation", score=.9,
        relation_type="HELD_BY", match_kind="lexical", edge_id="e", episode_ids=["ep"],
    )])
    return store, relation


@pytest.mark.asyncio
async def test_union_still_applies_explicit_time_and_deduplicates():
    from datetime import UTC, datetime
    store = InMemoryStore()
    await _put(store, _record("vector", "sensor", memory_type="fact",
                             temporal_status="current", day=1,
                             state=MemoryState.CONFIRMED,
                             valid_to=datetime(2026, 2, 1, tzinfo=UTC)))
    engine = PersonalMemoryQueryEngine(
        store, PersonalMemoryQueryConfig(candidate_fusion="union"),
        semantic_index=Vector(), relation_index=_RelationIndex([]),
    )
    result = await engine.query(_DraftPlanner(intent="current", search_text="sensor",
                                            relation_hints=["held"]),
                                "sensor", [SCOPE], now=NOW)
    assert not result.hits
    store, relation = await setup()
    relation.candidates.append(RelationCandidate(
        scope=SCOPE, memory_id="vector", source="graphiti_relation", score=.9,
        relation_type="HELD_BY", match_kind="lexical", edge_id="e2", episode_ids=["ep2"],
    ))
    engine = PersonalMemoryQueryEngine(store, PersonalMemoryQueryConfig(candidate_fusion="union"),
                                       semantic_index=Vector(), relation_index=relation)
    result = await engine.query(_DraftPlanner(search_text="sensor", relation_hints=["held"]),
                                "sensor", [SCOPE], now=NOW)
    assert sorted(h.record.memory_id for h in result.hits) == ["relation", "vector"]


@pytest.mark.asyncio
async def test_union_hard_constraint_without_index_fails_before_search():
    engine = PersonalMemoryQueryEngine(InMemoryStore(),
                                       PersonalMemoryQueryConfig(candidate_fusion="union"))
    with pytest.raises(NotImplementedError):
        await engine.query(_DraftPlanner(), "sensor", [SCOPE], now=NOW,
                           available_relation_types=["HELD_BY"],
                           required_relation_types=["HELD_BY"])


@pytest.mark.asyncio
async def test_union_recovers_independent_vector_without_unsafe_candidates():
    store, relation = await setup()
    results = {}
    for mode in ["relation_gate", "union"]:
        engine = PersonalMemoryQueryEngine(
            store, PersonalMemoryQueryConfig(candidate_fusion=mode),
            semantic_index=Vector(), relation_index=relation,
        )
        results[mode] = await engine.query(
            _DraftPlanner(search_text="sensor", relation_hints=["held"]),
            "sensor", [SCOPE], now=NOW, trace_limit=100,
        )
    assert {h.record.memory_id for h in results["relation_gate"].hits} == {"relation"}
    assert {h.record.memory_id for h in results["union"].hits} == {"vector", "relation"}
    assert results["union"].trace.counts[
        "relation_gate:engine:independent_candidate_retained"
    ] == 1


@pytest.mark.asyncio
async def test_union_uses_raw_query_for_candidates_when_planner_search_is_empty():
    store, _ = await setup()
    vector = RecordingVector()
    engine = PersonalMemoryQueryEngine(
        store, PersonalMemoryQueryConfig(candidate_fusion="union"),
        semantic_index=vector, relation_index=_RelationIndex([]),
    )

    result = await engine.query(
        _DraftPlanner(
            intent="lookup",
            search_text="",
            entity_mentions=["camera"],
            relation_hints=["where"],
        ),
        "Where was the camera last year?",
        [SCOPE],
        now=NOW,
        trace_limit=100,
    )

    assert vector.queries == ["Where was the camera last year?"]
    assert [hit.record.memory_id for hit in result.hits] == ["vector"]
    assert result.plan.search_text == ""
    assert any("raw query" in warning for warning in result.warnings)
    assert result.trace is not None
    assert result.trace.counts[
        "discovery:engine:raw_query_candidate_fallback"
    ] == 1


@pytest.mark.asyncio
async def test_default_fusion_preserves_empty_search_without_vector_call():
    store, _ = await setup()
    vector = RecordingVector()
    result = await PersonalMemoryQueryEngine(
        store, semantic_index=vector, relation_index=_RelationIndex([]),
    ).query(
        _DraftPlanner(search_text="", entity_mentions=["camera"]),
        "Where is the camera?",
        [SCOPE],
        now=NOW,
    )

    assert vector.queries == []
    assert not result.hits


@pytest.mark.asyncio
async def test_union_host_constraints_still_filter_even_with_legacy_gate_disabled():
    store, relation = await setup()
    engine = PersonalMemoryQueryEngine(
        store, PersonalMemoryQueryConfig(candidate_fusion="union", relation_hints_require_match=False),
        semantic_index=Vector(), relation_index=relation,
    )
    result = await engine.query(_DraftPlanner(search_text="sensor"), "sensor", [SCOPE],
                                now=NOW, required_relation_types=["HELD_BY"],
                                available_relation_types=["HELD_BY"])
    assert [h.record.memory_id for h in result.hits] == ["relation"]


@pytest.mark.asyncio
async def test_hard_constraints_cannot_silently_fall_back_on_outage():
    store, _ = await setup()
    engine = PersonalMemoryQueryEngine(
        store, PersonalMemoryQueryConfig(candidate_fusion="union"),
        semantic_index=Vector(), relation_index=_FailingRelationIndex(),
    )
    with pytest.raises(RelationIndexUnavailableError):
        await engine.query(_DraftPlanner(search_text="sensor"), "sensor", [SCOPE],
                           now=NOW, required_relation_types=["HELD_BY"],
                           available_relation_types=["HELD_BY"])
    soft = await engine.query(_DraftPlanner(search_text="sensor", relation_hints=["held"]),
                              "sensor", [SCOPE], now=NOW)
    assert [h.record.memory_id for h in soft.hits] == ["vector"]


def test_default_fingerprint_stays_compatible_and_union_is_distinct():
    from doppel_memory.query import _fingerprint
    default = PersonalMemoryQueryConfig()
    legacy = default.model_dump(mode="json")
    legacy.pop("candidate_fusion")
    assert default.fingerprint == _fingerprint(legacy)
    assert default.fingerprint != PersonalMemoryQueryConfig(candidate_fusion="union").fingerprint
