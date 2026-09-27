"""Contracts for bounded independent-plus-path candidate assembly."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

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
from doppel_memory.relation import (
    RelationPathCandidate,
    RelationPathHop,
    RelationRerankRequest,
    RelationRerankScore,
)
from doppel_memory.relation_path_retrieval import (
    RelationPathRetrievalHit,
    assemble_hybrid_retrieval_candidates,
    promote_semantic_path_completions,
    rank_explored_relation_paths,
    rerank_explored_relation_paths,
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


def _base_hit(
    record: MemoryRecord,
    *,
    sources: list[str] | None = None,
    entity_binding: Literal[
        "not_requested", "literal", "relation", "unverified"
    ] = "not_requested",
) -> PersonalMemoryQueryHit:
    return PersonalMemoryQueryHit(
        record=record,
        score=0.8,
        lexical_score=0.4,
        semantic_score=0.7,
        effective_at=NOW,
        candidate_evidence=PersonalMemoryCandidateEvidence(
            sources=sources or ["semantic"],
            entity_binding=entity_binding,
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


def _two_hop_path_hit(
    first_memory_id: str, second_memory_id: str
) -> RelationPathRetrievalHit:
    candidate = RelationPathCandidate(
        scope=SCOPE,
        source="tests.graph",
        score=0.8,
        path_id="p-two-hop",
        start_entity_id="entity-start",
        end_entity_id="entity-end",
        hops=[
            RelationPathHop(
                position=0,
                relation_type="FIRST_HOP",
                direction="outbound",
                source_entity_id="entity-start",
                target_entity_id="entity-middle",
                edge_id="edge-first",
                fact="first fact",
                episode_ids=["episode-first"],
                memory_ids=[first_memory_id],
            ),
            RelationPathHop(
                position=1,
                relation_type="SECOND_HOP",
                direction="outbound",
                source_entity_id="entity-middle",
                target_entity_id="entity-end",
                edge_id="edge-second",
                fact="second fact",
                episode_ids=["episode-second"],
                memory_ids=[second_memory_id],
            ),
        ],
        supporting_memory_ids=[first_memory_id, second_memory_id],
    )
    return RelationPathRetrievalHit(
        candidate=candidate,
        route_indexes=[0],
        route_modes=["exploration"],
        rrf_score=0.02,
    )


class _PathReranker:
    name = "tests.path-reranker"
    version = "1"

    def __init__(self, scores: list[RelationRerankScore]) -> None:
        self.scores = scores
        self.requests: list[RelationRerankRequest] = []

    async def rerank(self, request: RelationRerankRequest) -> list[RelationRerankScore]:
        self.requests.append(request)
        return self.scores


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
async def test_assembly_can_reserve_literal_entity_context_without_judging_support() -> (
    None
):
    store = InMemoryStore()
    higher_ranked = _record("m-higher-ranked")
    literal_anchor = _record("m-literal-anchor")
    await _put(store, higher_ranked, literal_anchor)

    result = await assemble_hybrid_retrieval_candidates(
        store,
        [
            _base_hit(higher_ranked),
            _base_hit(literal_anchor, entity_binding="literal"),
        ],
        [],
        [SCOPE],
        filters=FILTERS,
        limit=2,
        base_reserve=1,
        literal_entity_reserve=1,
    )

    assert [item.record.memory_id for item in result.candidates] == [
        "m-literal-anchor",
        "m-higher-ranked",
    ]
    assert result.candidates[0].discovery_sources == [
        "independent",
        "semantic",
        "entity_anchor_reserve",
    ]
    assert result.candidates[0].answer_support == "unassessed"


@pytest.mark.asyncio
async def test_literal_entity_reserve_is_bounded_by_base_reserve() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        await assemble_hybrid_retrieval_candidates(
            InMemoryStore(),
            [],
            [],
            [SCOPE],
            filters=FILTERS,
            base_reserve=0,
            literal_entity_reserve=1,
        )


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
async def test_assembly_attributes_exploration_without_granting_answer_support() -> (
    None
):
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


def test_exploration_can_prefer_a_bounded_complete_path_over_its_prefix() -> None:
    complete = _two_hop_path_hit("m-first", "m-second").candidate
    prefix = RelationPathCandidate(
        scope=SCOPE,
        source="tests.graph",
        score=complete.score,
        path_id="p-one-hop",
        start_entity_id=complete.start_entity_id,
        end_entity_id="entity-middle",
        hops=[complete.hops[0]],
        supporting_memory_ids=["m-first"],
    )

    default = rank_explored_relation_paths([prefix, complete])
    recall_oriented = rank_explored_relation_paths(
        [prefix, complete], prefer_complete_paths=True
    )

    assert [len(hit.candidate.hops) for hit in default] == [1, 2]
    assert [len(hit.candidate.hops) for hit in recall_oriented] == [2, 1]


@pytest.mark.asyncio
async def test_path_reranker_sees_only_text_and_preserves_membership() -> None:
    complete = _two_hop_path_hit("m-first", "m-second").candidate
    prefix = RelationPathCandidate(
        scope=SCOPE,
        source="tests.graph",
        score=complete.score,
        path_id="p-one-hop",
        start_entity_id=complete.start_entity_id,
        end_entity_id="entity-middle",
        hops=[complete.hops[0]],
        supporting_memory_ids=["m-first"],
    )
    reranker = _PathReranker(
        [
            RelationRerankScore(item_id="path-000", score=0.1),
            RelationRerankScore(item_id="path-001", score=0.9),
        ]
    )

    result = await rerank_explored_relation_paths(
        [prefix, complete],
        query_text="Where is the item?",
        reranker=reranker,
    )

    assert result.status == "completed"
    assert result.error_type == ""
    assert [hit.candidate.path_id for hit in result.hits] == [
        "p-two-hop",
        "p-one-hop",
    ]
    assert {hit.candidate.path_id for hit in result.hits} == {
        prefix.path_id,
        complete.path_id,
    }
    request = reranker.requests[0].model_dump(mode="json")
    assert set(request) == {"query_text", "relation_hints", "items"}
    assert set(request["items"][0]) == {"item_id", "relation_type", "fact"}
    assert request["items"][1]["relation_type"] == "FIRST_HOP -> SECOND_HOP"
    assert request["items"][1]["fact"] == "first fact\nsecond fact"
    serialized = str(request)
    assert "owner-1" not in serialized
    assert "m-first" not in serialized
    assert "p-two-hop" not in serialized


@pytest.mark.asyncio
async def test_path_reranker_malformed_output_falls_back_deterministically() -> None:
    prefix = _path_hit(["m-first"], path_id="p-one-hop").candidate
    complete = _two_hop_path_hit("m-first", "m-second").candidate
    reranker = _PathReranker([RelationRerankScore(item_id="path-999", score=1.0)])

    result = await rerank_explored_relation_paths(
        [prefix, complete],
        query_text="Where is the item?",
        reranker=reranker,
        prefer_complete_paths=False,
    )

    expected = rank_explored_relation_paths(
        [prefix, complete], prefer_complete_paths=False
    )
    assert result.status == "fallback"
    assert result.error_type == "ValueError"
    assert [hit.candidate.path_id for hit in result.hits] == [
        hit.candidate.path_id for hit in expected
    ]


@pytest.mark.asyncio
async def test_path_reranker_does_not_call_provider_without_paths() -> None:
    reranker = _PathReranker([])

    result = await rerank_explored_relation_paths(
        [],
        query_text="Where is the item?",
        reranker=reranker,
    )

    assert result.status == "not_run"
    assert result.hits == []
    assert reranker.requests == []


def test_semantic_path_completion_moves_only_its_best_extension() -> None:
    complete = _two_hop_path_hit("m-first", "m-second")
    prefix = RelationPathRetrievalHit(
        candidate=RelationPathCandidate(
            scope=SCOPE,
            source="tests.graph",
            score=complete.candidate.score,
            path_id="p-one-hop",
            start_entity_id=complete.candidate.start_entity_id,
            end_entity_id="entity-middle",
            hops=[complete.candidate.hops[0]],
            supporting_memory_ids=["m-first"],
        ),
        route_indexes=[0],
        route_modes=["exploration"],
        rrf_score=1 / 61,
    )
    unrelated = _path_hit(["m-unrelated"], path_id="p-unrelated")
    lower_extension = complete.model_copy(
        update={
            "candidate": complete.candidate.model_copy(
                update={"path_id": "p-lower-extension"}
            )
        }
    )

    result = promote_semantic_path_completions(
        [prefix, unrelated, complete, lower_extension]
    )

    assert [hit.candidate.path_id for hit in result] == [
        "p-two-hop",
        "p-one-hop",
        "p-unrelated",
        "p-lower-extension",
    ]
    assert {hit.candidate.path_id for hit in result} == {
        "p-one-hop",
        "p-unrelated",
        "p-two-hop",
        "p-lower-extension",
    }


def test_semantic_path_completion_never_links_prefixes_across_scopes() -> None:
    complete = _two_hop_path_hit("m-first", "m-second")
    prefix = RelationPathRetrievalHit(
        candidate=RelationPathCandidate(
            scope=SCOPE,
            source="tests.graph",
            score=complete.candidate.score,
            path_id="p-prefix",
            start_entity_id=complete.candidate.start_entity_id,
            end_entity_id="entity-middle",
            hops=[complete.candidate.hops[0]],
            supporting_memory_ids=["m-first"],
        ),
        route_indexes=[0],
        route_modes=["exploration"],
        rrf_score=1 / 61,
    )
    other_scope = MemoryScope(user_id="owner-2", agent_id="agent-1")
    cross_scope_complete = complete.model_copy(
        update={
            "candidate": complete.candidate.model_copy(
                update={"scope": other_scope, "path_id": "p-other-scope"}
            )
        }
    )

    result = promote_semantic_path_completions([prefix, cross_scope_complete])

    assert [hit.candidate.path_id for hit in result] == [
        "p-prefix",
        "p-other-scope",
    ]


@pytest.mark.asyncio
async def test_assembly_can_prioritize_one_complete_path_without_hiding_base() -> None:
    store = InMemoryStore()
    base_records = [_record(f"m-base-{index}") for index in range(5)]
    first = _record("m-first")
    second = _record("m-second")
    await _put(store, *base_records, first, second)

    result = await assemble_hybrid_retrieval_candidates(
        store,
        [_base_hit(record) for record in base_records],
        [_two_hop_path_hit(first.memory_id, second.memory_id)],
        [SCOPE],
        filters=FILTERS,
        limit=7,
        base_reserve=5,
        path_evidence_reserve=1,
    )

    ids = [candidate.record.memory_id for candidate in result.candidates]
    assert ids[:2] == ["m-first", "m-second"]
    assert set(ids[2:]) == {record.memory_id for record in base_records}
    assert all(
        "path_evidence_reserve" in candidate.discovery_sources
        for candidate in result.candidates[:2]
    )


@pytest.mark.asyncio
async def test_assembly_can_keep_base_reserve_ahead_of_complete_path() -> None:
    store = InMemoryStore()
    base_records = [_record(f"m-base-{index}") for index in range(5)]
    terminal = _record("m-terminal")
    await _put(store, *base_records, terminal)
    path = _two_hop_path_hit(base_records[0].memory_id, terminal.memory_id)

    result = await assemble_hybrid_retrieval_candidates(
        store,
        [_base_hit(record) for record in base_records],
        [path],
        [SCOPE],
        filters=FILTERS,
        limit=6,
        base_reserve=5,
        path_evidence_reserve=1,
        preserve_base_reserve_order=True,
    )

    assert [candidate.record.memory_id for candidate in result.candidates] == [
        *(record.memory_id for record in base_records),
        terminal.memory_id,
    ]
    by_id = {candidate.record.memory_id: candidate for candidate in result.candidates}
    assert "path_evidence_reserve" in by_id[base_records[0].memory_id].discovery_sources
    assert "path_evidence_reserve" in by_id[terminal.memory_id].discovery_sources


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
    assert result.rejected_path_reasons == {"filter_mismatch": 1}
    assert result.truncated is True


@pytest.mark.asyncio
async def test_assembly_revalidates_base_authority_and_exact_scope() -> None:
    store = InMemoryStore()
    agent_output = _record("m-agent", authority=FactAuthority.AGENT_OUTPUT)
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
    assert result.rejected_base_reasons == {
        "filter_mismatch": 1,
        "unauthorized_scope": 1,
    }
    assert result.rejected_path_reasons == {"unauthorized_scope": 1}


@pytest.mark.asyncio
async def test_assembly_reports_stale_store_candidate_separately() -> None:
    store = InMemoryStore()
    stale = _record("m-stale")

    result = await assemble_hybrid_retrieval_candidates(
        store,
        [_base_hit(stale)],
        [],
        [SCOPE],
        filters=FILTERS,
    )

    assert result.candidates == []
    assert result.rejected_base_hits == 1
    assert result.rejected_base_reasons == {"store_missing": 1}


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
