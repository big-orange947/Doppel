"""Experimental union retrieval for exact and candidate relation paths.

The models in this module are additive and are not wired into the stable query engine.
They make one boundary explicit: a typed graph path may contribute candidates, but it
must never suppress independent semantic retrieval.  Exact and widened candidate paths
remain bounded, ontology-governed, scope-bound, time-filtered, and Store-revalidated by
the supplied :class:`~doppel_memory.relation.RelationPathIndex`.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from doppel_memory.models import MemoryFilter, MemoryScope
from doppel_memory.query_path import PersonalMemoryRelationPathDraftV4
from doppel_memory.relation import (
    RelationPathCandidate,
    RelationPathIndex,
    RelationPathQuery,
    RelationPathStep,
)


class RelationPathCandidateOntologyError(ValueError):
    """A candidate path selected a relation type outside the host ontology."""


class RelationPathCandidateLimitError(ValueError):
    """Candidate observations exceeded the fixed retrieval-plan resource bound."""


class CandidateRelationAtom(BaseModel):
    """One non-authoritative edge with bounded alternative host relation types."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    relation_types: list[str] = Field(min_length=1, max_length=4)
    source_ref: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    target_ref: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")

    @field_validator("relation_types", mode="before")
    @classmethod
    def _normalize_relation_types(cls, value: object) -> list[str]:
        items = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
        normalized = [str(item or "").strip().upper() for item in items]
        return list(dict.fromkeys(item for item in normalized if item))

    @model_validator(mode="after")
    def _validate_endpoints(self) -> CandidateRelationAtom:
        if self.source_ref == self.target_ref:
            raise ValueError("candidate relation atom endpoints must differ")
        return self


class CandidateRelationTopology(BaseModel):
    """A retrieval-only atom graph from fixed ``anchor`` to fixed ``answer``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    atoms: list[CandidateRelationAtom] = Field(min_length=1, max_length=8)
    confidence: float = Field(default=0.5, gt=0.0, le=1.0)


class RelationPathRetrievalRoute(BaseModel):
    """One bounded graph route; candidate routes never become factual proof."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["exact", "candidate"]
    steps: list[RelationPathStep] = Field(min_length=1, max_length=2)
    confidence: float = Field(gt=0.0, le=1.0)


class RelationPathCompilationStats(BaseModel):
    """Content-free accounting for candidate topology compilation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observations: int = Field(ge=0)
    compiled: int = Field(ge=0)
    ambiguous: int = Field(ge=0)
    over_bound: int = Field(ge=0)
    duplicates: int = Field(ge=0)


class RelationPathRetrievalPlan(BaseModel):
    """Graph routes that must be unioned with independent semantic candidates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    query_text: str = ""
    entity_mentions: list[str] = Field(default_factory=list)
    subject: str
    subject_id: str
    valid_at: datetime | None = None
    time_from: datetime | None = None
    time_to: datetime | None = None
    routes: list[RelationPathRetrievalRoute] = Field(default_factory=list, max_length=9)
    semantic_fallback_required: Literal[True] = True
    global_relation_gate: Literal[False] = False
    compilation: RelationPathCompilationStats

    @field_validator("valid_at", "time_from", "time_to")
    @classmethod
    def _normalize_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("relation path retrieval times must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_routes(self) -> RelationPathRetrievalPlan:
        if sum(route.mode == "exact" for route in self.routes) > 1:
            raise ValueError("a retrieval plan may contain at most one exact route")
        if self.valid_at is not None and (
            self.time_from is not None or self.time_to is not None
        ):
            raise ValueError("valid_at cannot be combined with a relation time range")
        if self.time_from and self.time_to and self.time_to < self.time_from:
            raise ValueError("relation path retrieval time range is reversed")
        return self


class RelationPathRetrievalHit(BaseModel):
    """One deduplicated graph candidate with route-level RRF attribution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate: RelationPathCandidate
    route_indexes: list[int] = Field(min_length=1)
    route_modes: list[Literal["exact", "candidate"]] = Field(min_length=1)
    rrf_score: float = Field(gt=0.0)


def build_relation_path_retrieval_plan(
    draft: PersonalMemoryRelationPathDraftV4,
    *,
    candidate_topologies: Sequence[CandidateRelationTopology] = (),
    allowed_relation_types: Sequence[str],
) -> RelationPathRetrievalPlan:
    """Compile trusted exact output and retrieval-only alternatives without guessing."""

    if len(candidate_topologies) > 8:
        raise RelationPathCandidateLimitError(
            "a retrieval plan accepts at most eight candidate topology observations"
        )
    bound = PersonalMemoryRelationPathDraftV4.model_validate(draft)
    allowed = {str(item or "").strip().upper() for item in allowed_relation_types}
    routes: list[RelationPathRetrievalRoute] = []
    signatures: set[tuple[tuple[tuple[str, ...], str], ...]] = set()
    if bound.path_decision == "execute":
        exact = RelationPathRetrievalRoute(
            mode="exact",
            steps=bound.path_steps,
            confidence=bound.path_confidence,
        )
        _validate_route_ontology(exact, allowed)
        routes.append(exact)
        signatures.add(_route_signature(exact.steps))

    ambiguous = 0
    over_bound = 0
    duplicates = 0
    compiled = 0
    for raw in candidate_topologies:
        topology = CandidateRelationTopology.model_validate(raw)
        selected = {
            relation_type
            for atom in topology.atoms
            for relation_type in atom.relation_types
        }
        unknown = sorted(selected.difference(allowed))
        if unknown:
            raise RelationPathCandidateOntologyError(
                f"candidate path relation types outside host ontology: {unknown}"
            )
        status, steps = _compile_candidate_atoms(topology.atoms)
        if status == "ambiguous":
            ambiguous += 1
            continue
        if status == "over_bound":
            over_bound += 1
            continue
        route = RelationPathRetrievalRoute(
            mode="candidate", steps=steps, confidence=topology.confidence
        )
        signature = _route_signature(route.steps)
        if signature in signatures:
            duplicates += 1
            continue
        signatures.add(signature)
        routes.append(route)
        compiled += 1

    return RelationPathRetrievalPlan(
        query_text=bound.search_text,
        entity_mentions=bound.entity_mentions,
        subject=bound.subject,
        subject_id=bound.subject_id,
        valid_at=bound.as_of,
        time_from=bound.time_from,
        time_to=bound.time_to,
        routes=routes,
        compilation=RelationPathCompilationStats(
            observations=len(candidate_topologies),
            compiled=compiled,
            ambiguous=ambiguous,
            over_bound=over_bound,
            duplicates=duplicates,
        ),
    )


async def search_relation_path_routes(
    index: RelationPathIndex,
    plan: RelationPathRetrievalPlan,
    scopes: Sequence[MemoryScope],
    *,
    filters: MemoryFilter | None = None,
    limit: int = 10,
    rrf_k: int = 60,
) -> list[RelationPathRetrievalHit]:
    """Search every route and fuse graph candidates without suppressing other sources."""

    bound = RelationPathRetrievalPlan.model_validate(plan)
    if limit <= 0 or not bound.routes:
        return []
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")

    candidates: dict[
        tuple[str, tuple[str, ...], tuple[str, ...]], RelationPathCandidate
    ] = {}
    route_indexes: defaultdict[
        tuple[str, tuple[str, ...], tuple[str, ...]], list[int]
    ] = defaultdict(list)
    route_modes: defaultdict[
        tuple[str, tuple[str, ...], tuple[str, ...]],
        list[Literal["exact", "candidate"]],
    ] = defaultdict(list)
    scores_by_mode: defaultdict[
        tuple[str, tuple[str, ...], tuple[str, ...]],
        dict[Literal["exact", "candidate"], float],
    ] = defaultdict(dict)

    async def search_route(
        route: RelationPathRetrievalRoute,
    ) -> Sequence[RelationPathCandidate]:
        query = RelationPathQuery(
            query_text=bound.query_text,
            entity_mentions=bound.entity_mentions,
            steps=route.steps,
            subject=bound.subject,
            subject_id=bound.subject_id,
            valid_at=bound.valid_at,
            time_from=bound.time_from,
            time_to=bound.time_to,
        )
        return await index.search_relation_paths(
            query, scopes, filters=filters, limit=limit
        )

    route_tasks = [asyncio.create_task(search_route(route)) for route in bound.routes]
    try:
        route_results = await asyncio.gather(*route_tasks)
    except BaseException:
        for task in route_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*route_tasks, return_exceptions=True)
        raise
    for route_index, (route, found) in enumerate(
        zip(bound.routes, route_results, strict=True)
    ):
        seen_in_route: set[tuple[str, tuple[str, ...], tuple[str, ...]]] = set()
        unique_rank = 0
        for candidate in found:
            key = _candidate_key(candidate)
            if key in seen_in_route:
                continue
            seen_in_route.add(key)
            existing = candidates.get(key)
            if existing is None or candidate.score > existing.score:
                candidates[key] = candidate
            contribution = route.confidence / (rrf_k + unique_rank + 1)
            unique_rank += 1
            scores_by_mode[key][route.mode] = max(
                scores_by_mode[key].get(route.mode, 0.0), contribution
            )
            route_indexes[key].append(route_index)
            if route.mode not in route_modes[key]:
                route_modes[key].append(route.mode)

    ordered = sorted(
        candidates,
        key=lambda key: (
            -sum(scores_by_mode[key].values()),
            -candidates[key].score,
            candidates[key].scope.scope_key,
            candidates[key].path_id,
        ),
    )[:limit]
    return [
        RelationPathRetrievalHit(
            candidate=candidates[key],
            route_indexes=route_indexes[key],
            route_modes=route_modes[key],
            rrf_score=sum(scores_by_mode[key].values()),
        )
        for key in ordered
    ]


def _compile_candidate_atoms(
    atoms: Sequence[CandidateRelationAtom],
) -> tuple[Literal["compiled", "ambiguous", "over_bound"], list[RelationPathStep]]:
    if len(atoms) > 2:
        return "over_bound", []
    adjacency: dict[str, list[tuple[int, str]]] = {}
    for index, atom in enumerate(atoms):
        adjacency.setdefault(atom.source_ref, []).append((index, atom.target_ref))
        adjacency.setdefault(atom.target_ref, []).append((index, atom.source_ref))
    if (
        "anchor" not in adjacency
        or "answer" not in adjacency
        or any(len(edges) > 2 for edges in adjacency.values())
    ):
        return "ambiguous", []

    current = "anchor"
    used: set[int] = set()
    steps: list[RelationPathStep] = []
    while current != "answer":
        options = [item for item in adjacency[current] if item[0] not in used]
        if len(options) != 1:
            return "ambiguous", []
        index, next_ref = options[0]
        atom = atoms[index]
        steps.append(
            RelationPathStep(
                relation_types=atom.relation_types,
                direction="outbound" if current == atom.source_ref else "inbound",
            )
        )
        used.add(index)
        current = next_ref
        if len(steps) > len(atoms):
            return "ambiguous", []
    if len(used) != len(atoms):
        return "ambiguous", []
    return "compiled", steps


def _validate_route_ontology(
    route: RelationPathRetrievalRoute, allowed: set[str]
) -> None:
    selected = {
        relation_type for step in route.steps for relation_type in step.relation_types
    }
    unknown = sorted(selected.difference(allowed))
    if unknown:
        raise RelationPathCandidateOntologyError(
            f"exact path relation types outside host ontology: {unknown}"
        )


def _route_signature(
    steps: Sequence[RelationPathStep],
) -> tuple[tuple[tuple[str, ...], str], ...]:
    return tuple((tuple(sorted(step.relation_types)), step.direction) for step in steps)


def _candidate_key(
    candidate: RelationPathCandidate,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    return (
        candidate.scope.scope_key,
        tuple(hop.edge_id for hop in candidate.hops),
        tuple(hop.direction for hop in candidate.hops),
    )
