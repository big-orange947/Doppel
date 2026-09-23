"""Contracts for exact-plus-candidate relation path union retrieval."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from doppel_memory.models import MemoryFilter, MemoryScope
from doppel_memory.query_path import PersonalMemoryRelationPathDraftV4
from doppel_memory.relation import (
    RelationPathCandidate,
    RelationPathHop,
    RelationPathQuery,
    RelationPathStep,
)
from doppel_memory.relation_path_retrieval import (
    CandidateRelationAtom,
    CandidateRelationTopology,
    RelationPathCandidateLimitError,
    RelationPathCandidateOntologyError,
    build_relation_path_retrieval_plan,
    search_relation_path_routes,
)

ALLOWED = ["LOCATED_AT", "STORED_IN", "HELD_BY", "EMPLOYED_BY"]


def _draft(*, execute: bool = True) -> PersonalMemoryRelationPathDraftV4:
    return PersonalMemoryRelationPathDraftV4(
        operation="lookup",
        temporal_view="as_of",
        search_text="物品在哪里",
        entity_mentions=["相机"],
        subject="owner",
        subject_id="owner-1",
        as_of=datetime(2026, 9, 23, tzinfo=UTC),
        path_decision="execute" if execute else "abstain",
        path_reason="exact" if execute else "ambiguous",
        path_steps=(
            [RelationPathStep(relation_types=["LOCATED_AT"], direction="outbound")]
            if execute
            else []
        ),
        path_confidence=0.9 if execute else 0,
    )


def _topology(
    atoms: list[CandidateRelationAtom], *, confidence: float = 0.6
) -> CandidateRelationTopology:
    return CandidateRelationTopology(atoms=atoms, confidence=confidence)


def test_candidate_plan_keeps_exact_and_widened_routes_nonexclusive() -> None:
    plan = build_relation_path_retrieval_plan(
        _draft(),
        candidate_topologies=[
            _topology(
                [
                    CandidateRelationAtom(
                        relation_types=["located_at", "stored_in"],
                        source_ref="anchor",
                        target_ref="answer",
                    )
                ]
            )
        ],
        allowed_relation_types=ALLOWED,
    )

    assert [route.mode for route in plan.routes] == ["exact", "candidate"]
    assert plan.routes[1].steps == [
        RelationPathStep(
            relation_types=["LOCATED_AT", "STORED_IN"], direction="outbound"
        )
    ]
    assert plan.semantic_fallback_required is True
    assert plan.global_relation_gate is False
    assert plan.compilation.model_dump() == {
        "observations": 1,
        "compiled": 1,
        "ambiguous": 0,
        "over_bound": 0,
        "duplicates": 0,
    }


def test_abstention_can_still_carry_a_retrieval_only_candidate_route() -> None:
    plan = build_relation_path_retrieval_plan(
        _draft(execute=False),
        candidate_topologies=[
            _topology(
                [
                    CandidateRelationAtom(
                        relation_types=["HELD_BY"],
                        source_ref="answer",
                        target_ref="anchor",
                    )
                ]
            )
        ],
        allowed_relation_types=ALLOWED,
    )

    assert len(plan.routes) == 1
    assert plan.routes[0].mode == "candidate"
    assert plan.routes[0].steps[0].direction == "inbound"
    assert plan.global_relation_gate is False


def test_candidate_compiler_accounts_for_invalid_topology_without_guessing() -> None:
    plan = build_relation_path_retrieval_plan(
        _draft(execute=False),
        candidate_topologies=[
            _topology(
                [
                    CandidateRelationAtom(
                        relation_types=["HELD_BY"],
                        source_ref="other",
                        target_ref="answer",
                    )
                ]
            ),
            _topology(
                [
                    CandidateRelationAtom(
                        relation_types=["HELD_BY"],
                        source_ref="anchor",
                        target_ref="a",
                    ),
                    CandidateRelationAtom(
                        relation_types=["EMPLOYED_BY"],
                        source_ref="a",
                        target_ref="b",
                    ),
                    CandidateRelationAtom(
                        relation_types=["LOCATED_AT"],
                        source_ref="b",
                        target_ref="answer",
                    ),
                ]
            ),
        ],
        allowed_relation_types=ALLOWED,
    )

    assert plan.routes == []
    assert plan.compilation.ambiguous == 1
    assert plan.compilation.over_bound == 1


def test_candidate_compiler_rejects_types_outside_host_ontology() -> None:
    with pytest.raises(
        RelationPathCandidateOntologyError, match="outside host ontology"
    ):
        build_relation_path_retrieval_plan(
            _draft(execute=False),
            candidate_topologies=[
                _topology(
                    [
                        CandidateRelationAtom(
                            relation_types=["UNKNOWN"],
                            source_ref="anchor",
                            target_ref="answer",
                        )
                    ]
                )
            ],
            allowed_relation_types=ALLOWED,
        )


def test_candidate_compiler_rejects_more_than_eight_observations_up_front() -> None:
    topology = _topology(
        [
            CandidateRelationAtom(
                relation_types=["HELD_BY"],
                source_ref="anchor",
                target_ref="answer",
            )
        ]
    )

    with pytest.raises(RelationPathCandidateLimitError, match="at most eight"):
        build_relation_path_retrieval_plan(
            _draft(execute=False),
            candidate_topologies=[topology] * 9,
            allowed_relation_types=ALLOWED,
        )


class _FakePathIndex:
    def __init__(self, results: list[list[RelationPathCandidate]]) -> None:
        self.results = results
        self.calls: list[tuple[RelationPathQuery, list[MemoryScope], Any, int]] = []

    async def search_relation_paths(
        self,
        request: RelationPathQuery,
        scopes: list[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> list[RelationPathCandidate]:
        self.calls.append((request, scopes, filters, limit))
        return self.results[len(self.calls) - 1]


def _candidate(
    scope: MemoryScope,
    *,
    path_id: str,
    edge_id: str,
    relation_type: str,
    memory_id: str,
    score: float,
) -> RelationPathCandidate:
    return RelationPathCandidate(
        scope=scope,
        source="tests.graph",
        score=score,
        path_id=path_id,
        start_entity_id="start",
        end_entity_id=f"end-{path_id}",
        hops=[
            RelationPathHop(
                position=0,
                relation_type=relation_type,
                direction="outbound",
                source_entity_id="start",
                target_entity_id=f"end-{path_id}",
                edge_id=edge_id,
                episode_ids=[f"episode-{path_id}"],
                memory_ids=[memory_id],
            )
        ],
        supporting_memory_ids=[memory_id],
    )


@pytest.mark.asyncio
async def test_route_search_rrf_fuses_and_attributes_duplicate_graph_paths() -> None:
    scope = MemoryScope(user_id="owner-1", agent_id="agent-1")
    shared = _candidate(
        scope,
        path_id="shared",
        edge_id="edge-shared",
        relation_type="LOCATED_AT",
        memory_id="m-shared",
        score=0.8,
    )
    widened = _candidate(
        scope,
        path_id="widened",
        edge_id="edge-widened",
        relation_type="STORED_IN",
        memory_id="m-widened",
        score=0.9,
    )
    index = _FakePathIndex([[shared], [widened, shared]])
    filters = MemoryFilter(tags={"personal-memory"})
    plan = build_relation_path_retrieval_plan(
        _draft(),
        candidate_topologies=[
            _topology(
                [
                    CandidateRelationAtom(
                        relation_types=["LOCATED_AT", "STORED_IN"],
                        source_ref="anchor",
                        target_ref="answer",
                    )
                ]
            )
        ],
        allowed_relation_types=ALLOWED,
    )

    hits = await search_relation_path_routes(
        index, plan, [scope], filters=filters, limit=10
    )

    assert [hit.candidate.path_id for hit in hits] == ["shared", "widened"]
    assert hits[0].route_indexes == [0, 1]
    assert hits[0].route_modes == ["exact", "candidate"]
    assert hits[0].rrf_score > hits[1].rrf_score
    assert hits[0].rrf_score == pytest.approx(0.9 / 61 + 0.6 / 62)
    assert hits[1].rrf_score == pytest.approx(0.6 / 61)
    assert len(index.calls) == 2
    assert index.calls[0][0].valid_at == datetime(2026, 9, 23, tzinfo=UTC)
    assert index.calls[1][0].steps[0].relation_types == [
        "LOCATED_AT",
        "STORED_IN",
    ]
    assert all(call[1] == [scope] for call in index.calls)
    assert all(call[2] == filters for call in index.calls)


@pytest.mark.asyncio
async def test_route_search_does_not_double_count_duplicate_within_one_route() -> None:
    scope = MemoryScope(user_id="owner-1", agent_id="agent-1")
    duplicate = _candidate(
        scope,
        path_id="duplicate",
        edge_id="edge-duplicate",
        relation_type="LOCATED_AT",
        memory_id="m-duplicate",
        score=0.8,
    )
    index = _FakePathIndex([[duplicate, duplicate]])
    plan = build_relation_path_retrieval_plan(_draft(), allowed_relation_types=ALLOWED)

    hits = await search_relation_path_routes(index, plan, [scope])

    assert len(hits) == 1
    assert hits[0].route_indexes == [0]
    assert hits[0].route_modes == ["exact"]
    assert hits[0].rrf_score == pytest.approx(0.9 / 61)


@pytest.mark.asyncio
async def test_route_search_never_queries_graph_for_empty_or_zero_limit_plan() -> None:
    scope = MemoryScope(user_id="owner-1", agent_id="agent-1")
    index = _FakePathIndex([])
    plan = build_relation_path_retrieval_plan(
        _draft(execute=False), allowed_relation_types=ALLOWED
    )

    assert await search_relation_path_routes(index, plan, [scope]) == []
    assert await search_relation_path_routes(index, plan, [scope], limit=0) == []
    assert index.calls == []


class _ConcurrentPathIndex:
    def __init__(self) -> None:
        self.active = 0
        self.peak = 0
        self.started = asyncio.Event()

    async def search_relation_paths(
        self,
        request: RelationPathQuery,
        scopes: list[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> list[RelationPathCandidate]:
        del request, scopes, filters, limit
        self.active += 1
        self.peak = max(self.peak, self.active)
        if self.active >= 2:
            self.started.set()
        await asyncio.wait_for(self.started.wait(), timeout=1)
        self.active -= 1
        return []


@pytest.mark.asyncio
async def test_route_search_executes_independent_routes_concurrently() -> None:
    scope = MemoryScope(user_id="owner-1", agent_id="agent-1")
    index = _ConcurrentPathIndex()
    plan = build_relation_path_retrieval_plan(
        _draft(),
        candidate_topologies=[
            _topology(
                [
                    CandidateRelationAtom(
                        relation_types=["LOCATED_AT", "STORED_IN"],
                        source_ref="anchor",
                        target_ref="answer",
                    )
                ]
            )
        ],
        allowed_relation_types=ALLOWED,
    )

    assert await search_relation_path_routes(index, plan, [scope]) == []
    assert index.peak == 2


class _FailingPathIndex:
    def __init__(self) -> None:
        self.candidate_started = asyncio.Event()
        self.candidate_cancelled = False

    async def search_relation_paths(
        self,
        request: RelationPathQuery,
        scopes: list[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> list[RelationPathCandidate]:
        del scopes, filters, limit
        if len(request.steps[0].relation_types) == 1:
            await asyncio.wait_for(self.candidate_started.wait(), timeout=1)
            raise RuntimeError("route failed")
        self.candidate_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.candidate_cancelled = True
            raise
        return []


@pytest.mark.asyncio
async def test_route_search_cancels_siblings_and_preserves_original_error() -> None:
    scope = MemoryScope(user_id="owner-1", agent_id="agent-1")
    index = _FailingPathIndex()
    plan = build_relation_path_retrieval_plan(
        _draft(),
        candidate_topologies=[
            _topology(
                [
                    CandidateRelationAtom(
                        relation_types=["LOCATED_AT", "STORED_IN"],
                        source_ref="anchor",
                        target_ref="answer",
                    )
                ]
            )
        ],
        allowed_relation_types=ALLOWED,
    )

    with pytest.raises(RuntimeError, match="route failed"):
        await search_relation_path_routes(index, plan, [scope])
    assert index.candidate_cancelled is True
