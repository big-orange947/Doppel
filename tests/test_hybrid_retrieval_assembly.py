"""Contracts for bounded independent-plus-path candidate assembly."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from doppel_memory.in_memory_store import InMemoryStore
from doppel_memory.models import (
    FactAuthority,
    MemoryFilter,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    WriteStatus,
)
from doppel_memory.query import PersonalMemoryCandidateEvidence, PersonalMemoryQueryHit
from doppel_memory.relation import RelationPathCandidate, RelationPathHop
from doppel_memory.relation_path_retrieval import (
    RelationPathRetrievalHit,
    assemble_hybrid_retrieval_candidates,
)

NOW = datetime(2026, 9, 23, tzinfo=UTC)
SCOPE = MemoryScope(user_id="owner-1", agent_id="agent-1")
OTHER_SCOPE = MemoryScope(user_id="owner-2", agent_id="agent-1")
FILTERS = MemoryFilter(
    tags={"personal-memory"},
    states={MemoryState.CONFIRMED},
    exclude_authorities={FactAuthority.AGENT_OUTPUT},
)


def _record(
    memory_id: str,
    *,
    scope: MemoryScope = SCOPE,
    state: MemoryState = MemoryState.CONFIRMED,
    authority: FactAuthority = FactAuthority.HUMAN_SELF,
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        scope=scope,
        kind="fact",
        content=f"fact {memory_id}",
        actor="owner",
        authority=authority,
        state=state,
        tags=["personal-memory"],
        created_at=NOW,
        updated_at=NOW,
    )


def _base_hit(record: MemoryRecord, *, sources: list[str] | None = None) -> PersonalMemoryQueryHit:
    return PersonalMemoryQueryHit(
        record=record,
        score=0.8,
        lexical_score=0.4,
        semantic_score=0.7,
        effective_at=NOW,
        candidate_evidence=PersonalMemoryCandidateEvidence(
            sources=sources or ["semantic"],
            store_revalidated=True,
        ),
    )


def _path_hit(
    memory_ids: list[str],
    *,
    path_id: str,
    scope: MemoryScope = SCOPE,
    rrf_score: float = 0.02,
) -> RelationPathRetrievalHit:
    return RelationPathRetrievalHit(
        candidate=RelationPathCandidate(
            scope=scope,
            source="tests.graph",
            score=0.8,
            path_id=path_id,
            start_entity_id=f"start-{path_id}",
            end_entity_id=f"end-{path_id}",
            hops=[
                RelationPathHop(
                    position=0,
                    relation_type="RELATED_TO",
                    direction="outbound",
                    source_entity_id=f"start-{path_id}",
                    target_entity_id=f"end-{path_id}",
                    edge_id=f"edge-{path_id}",
                    episode_ids=[f"episode-{path_id}"],
                    memory_ids=memory_ids,
                )
            ],
            supporting_memory_ids=memory_ids,
        ),
        route_indexes=[0],
        route_modes=["candidate"],
        rrf_score=rrf_score,
    )


async def _put(store: InMemoryStore, *records: MemoryRecord) -> None:
    for record in records:
        result = await store.put(record)
        assert result.status is WriteStatus.CREATED


@pytest.mark.asyncio
async def test_assembly_reserves_independent_candidate_and_keeps_path_atomic() -> None:
    store = InMemoryStore()
    independent = _record("m-independent")
    path_record = _record("m-path")
    await _put(store, independent, path_record)

    result = await assemble_hybrid_retrieval_candidates(
        store,
        [_base_hit(independent, sources=["semantic", "vector"])],
        [_path_hit(["m-path"], path_id="p1", rrf_score=0.5)],
        [SCOPE],
        filters=FILTERS,
        limit=2,
        base_reserve=1,
    )

    assert {item.record.memory_id for item in result.candidates} == {
        "m-independent",
        "m-path",
    }
    by_id = {item.record.memory_id: item for item in result.candidates}
    assert by_id["m-independent"].discovery_sources == [
        "independent",
        "semantic",
        "vector",
    ]
    assert by_id["m-path"].discovery_sources == ["relation_path"]
    assert by_id["m-path"].answer_support == "unassessed"
    assert by_id["m-path"].store_revalidated is True
    assert [path.hit.candidate.path_id for path in result.relation_paths] == ["p1"]


@pytest.mark.asyncio
async def test_assembly_caps_overlapping_path_rank_instead_of_stacking_it() -> None:
    store = InMemoryStore()
    record = _record("m-shared")
    await _put(store, record)

    result = await assemble_hybrid_retrieval_candidates(
        store,
        [],
        [
            _path_hit(["m-shared"], path_id="p-low", rrf_score=0.02),
            _path_hit(["m-shared"], path_id="p-high", rrf_score=0.03),
        ],
        [SCOPE],
        filters=FILTERS,
        path_weight=0.8,
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].rrf_score == pytest.approx(0.8 * 0.03)
    assert result.candidates[0].path_ids == ["p-low", "p-high"]
    assert result.candidates[0].path_ranks == [1, 2]
    assert len(result.relation_paths) == 2


@pytest.mark.asyncio
async def test_assembly_attributes_exploration_without_granting_answer_support() -> None:
    store = InMemoryStore()
    record = _record("m-explored")
    await _put(store, record)
    explored = _path_hit(["m-explored"], path_id="p-explored").model_copy(
        update={"route_modes": ["exploration"]}
    )

    result = await assemble_hybrid_retrieval_candidates(
        store,
        [],
        [explored],
        [SCOPE],
        filters=FILTERS,
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].discovery_sources == [
        "relation_path",
        "relation_path:exploration",
    ]
    assert result.candidates[0].answer_support == "unassessed"


@pytest.mark.asyncio
async def test_assembly_rejects_whole_path_when_one_support_is_ineligible() -> None:
    store = InMemoryStore()
    confirmed = _record("m-confirmed")
    expired = _record("m-expired", state=MemoryState.EXPIRED)
    await _put(store, confirmed, expired)

    result = await assemble_hybrid_retrieval_candidates(
        store,
        [],
        [_path_hit(["m-confirmed", "m-expired"], path_id="p-invalid")],
        [SCOPE],
        filters=FILTERS,
    )

    assert result.candidates == []
    assert result.relation_paths == []
    assert result.rejected_path_hits == 1
    assert result.truncated is True


@pytest.mark.asyncio
async def test_assembly_revalidates_base_authority_and_exact_scope() -> None:
    store = InMemoryStore()
    agent_output = _record(
        "m-agent", authority=FactAuthority.AGENT_OUTPUT
    )
    foreign = _record("m-foreign", scope=OTHER_SCOPE)
    await _put(store, agent_output, foreign)

    result = await assemble_hybrid_retrieval_candidates(
        store,
        [_base_hit(agent_output), _base_hit(foreign)],
        [_path_hit(["m-foreign"], path_id="p-foreign", scope=OTHER_SCOPE)],
        [SCOPE],
        filters=FILTERS,
    )

    assert result.candidates == []
    assert result.rejected_base_hits == 2
    assert result.rejected_path_hits == 1


@pytest.mark.asyncio
async def test_assembly_omits_path_atomically_when_budget_cannot_fit_support() -> None:
    store = InMemoryStore()
    base = _record("m-base")
    first = _record("m-first")
    second = _record("m-second")
    await _put(store, base, first, second)

    result = await assemble_hybrid_retrieval_candidates(
        store,
        [_base_hit(base)],
        [_path_hit(["m-first", "m-second"], path_id="p-too-large")],
        [SCOPE],
        filters=FILTERS,
        limit=2,
        base_reserve=1,
    )

    assert [item.record.memory_id for item in result.candidates] == ["m-base"]
    assert result.relation_paths == []
    assert result.omitted_path_hits == 1
    assert result.truncated is True


@pytest.mark.asyncio
async def test_assembly_zero_limit_performs_no_candidate_exposure() -> None:
    store = InMemoryStore()
    record = _record("m-base")
    await _put(store, record)

    result = await assemble_hybrid_retrieval_candidates(
        store,
        [_base_hit(record)],
        [_path_hit(["m-base"], path_id="p1")],
        [SCOPE],
        filters=FILTERS,
        limit=0,
    )

    assert result.candidates == []
    assert result.omitted_path_hits == 1
    assert result.truncated is True
