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

from doppel_memory.models import (
    ACTIVE_MEMORY_STATES,
    MemoryFilter,
    MemoryIsolationError,
    MemoryRecord,
    MemoryScope,
)
from doppel_memory.query import PersonalMemoryQueryHit
from doppel_memory.query_path import PersonalMemoryRelationPathDraftV4
from doppel_memory.relation import (
    RelationPathCandidate,
    RelationPathIndex,
    RelationPathQuery,
    RelationPathStep,
)
from doppel_memory.store import MemoryStore


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
    route_modes: list[Literal["exact", "candidate", "exploration"]] = Field(
        min_length=1
    )
    rrf_score: float = Field(gt=0.0)


class HybridRetrievalCandidate(BaseModel):
    """One Store-revalidated memory exposed to the answer/context layer.

    Discovery attribution is deliberately separate from answer support.  A relation
    path can make a record easier to discover, but neither the path nor this assembly
    function claims that the record answers the user's question.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    record: MemoryRecord
    rrf_score: float = Field(gt=0.0)
    discovery_sources: list[str] = Field(min_length=1)
    base_rank: int | None = Field(default=None, ge=1)
    path_ranks: list[int] = Field(default_factory=list)
    path_ids: list[str] = Field(default_factory=list)
    answer_support: Literal["unassessed"] = "unassessed"
    store_revalidated: Literal[True] = True

    @field_validator("discovery_sources", "path_ids", mode="before")
    @classmethod
    def _normalize_attribution(cls, value: object) -> list[str]:
        items = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
        normalized = [str(item or "").strip() for item in items]
        return list(dict.fromkeys(item for item in normalized if item))

    @field_validator("path_ranks", mode="before")
    @classmethod
    def _normalize_path_ranks(cls, value: object) -> list[int]:
        items = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
        return sorted({int(str(item)) for item in items})


class HybridRelationPathEvidence(BaseModel):
    """A retained path whose complete provenance is present in ``candidates``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hit: RelationPathRetrievalHit
    supporting_memory_ids: list[str] = Field(min_length=1)
    answer_support: Literal["unassessed"] = "unassessed"
    store_revalidated: Literal[True] = True


class HybridRetrievalAssembly(BaseModel):
    """Bounded, auditable union of independent and typed-path candidates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: list[HybridRetrievalCandidate] = Field(default_factory=list)
    relation_paths: list[HybridRelationPathEvidence] = Field(default_factory=list)
    input_base_hits: int = Field(ge=0)
    input_path_hits: int = Field(ge=0)
    rejected_base_hits: int = Field(ge=0)
    rejected_path_hits: int = Field(ge=0)
    omitted_path_hits: int = Field(ge=0)
    truncated: bool = False


async def assemble_hybrid_retrieval_candidates(
    store: MemoryStore,
    base_hits: Sequence[PersonalMemoryQueryHit],
    path_hits: Sequence[RelationPathRetrievalHit],
    scopes: Sequence[MemoryScope],
    *,
    filters: MemoryFilter,
    limit: int = 10,
    base_reserve: int = 5,
    rrf_k: int = 60,
    base_weight: float = 1.0,
    path_weight: float = 0.8,
    max_path_support: int = 8,
) -> HybridRetrievalAssembly:
    """Revalidate and assemble independent retrieval with typed graph paths.

    The function is intentionally downstream of both retrieval systems.  It does not
    plan paths, search an index, or judge factual sufficiency.  Independent candidates
    receive a configurable reservation so a noisy graph branch cannot erase semantic
    recall.  Path contributions are capped to the best path per record, preventing
    overlapping graph routes from manufacturing rank through repetition.
    """

    if not scopes:
        raise MemoryIsolationError("hybrid retrieval assembly requires exact scopes")
    if limit < 0 or base_reserve < 0:
        raise ValueError("hybrid retrieval limits must not be negative")
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")
    if base_weight <= 0 or path_weight <= 0:
        raise ValueError("hybrid retrieval weights must be positive")
    if max_path_support < 1:
        raise ValueError("max_path_support must be positive")

    allowed_scopes = {scope.scope_key: scope for scope in scopes}
    if len(allowed_scopes) != len(scopes):
        raise MemoryIsolationError("hybrid retrieval scopes must be unique")
    if limit == 0:
        return HybridRetrievalAssembly(
            input_base_hits=len(base_hits),
            input_path_hits=len(path_hits),
            rejected_base_hits=0,
            rejected_path_hits=0,
            omitted_path_hits=len(path_hits),
            truncated=bool(base_hits or path_hits),
        )

    records: dict[tuple[str, str], MemoryRecord] = {}
    base_ranks: dict[tuple[str, str], int] = {}
    base_scores: dict[tuple[str, str], float] = {}
    path_scores: dict[tuple[str, str], float] = {}
    path_ranks: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
    path_ids: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    discovery_sources: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    rejected_base_hits = 0

    async def reload(scope: MemoryScope, memory_id: str) -> MemoryRecord | None:
        if scope.scope_key not in allowed_scopes:
            return None
        record = await store.get(allowed_scopes[scope.scope_key], memory_id)
        if record is None or record.scope.scope_key != scope.scope_key:
            return None
        if not _record_matches_filter(record, filters):
            return None
        return record

    for rank, hit in enumerate(base_hits, start=1):
        record = await reload(hit.record.scope, hit.record.memory_id)
        if record is None:
            rejected_base_hits += 1
            continue
        key = (record.scope.scope_key, record.memory_id)
        records[key] = record
        if key not in base_ranks or rank < base_ranks[key]:
            base_ranks[key] = rank
            base_scores[key] = base_weight / (rrf_k + rank)
        _extend_unique(discovery_sources[key], ["independent"])
        _extend_unique(discovery_sources[key], hit.candidate_evidence.sources)

    valid_paths: list[
        tuple[int, RelationPathRetrievalHit, list[tuple[str, str]]]
    ] = []
    rejected_path_hits = 0
    for rank, hit in enumerate(path_hits, start=1):
        candidate = hit.candidate
        support_ids = candidate.supporting_memory_ids
        if (
            candidate.scope.scope_key not in allowed_scopes
            or len(support_ids) > max_path_support
        ):
            rejected_path_hits += 1
            continue
        loaded: list[MemoryRecord] = []
        for memory_id in support_ids:
            record = await reload(candidate.scope, memory_id)
            if record is None:
                loaded = []
                break
            loaded.append(record)
        if len(loaded) != len(support_ids):
            rejected_path_hits += 1
            continue

        keys: list[tuple[str, str]] = []
        contribution = path_weight * hit.rrf_score
        for record in loaded:
            key = (record.scope.scope_key, record.memory_id)
            keys.append(key)
            records[key] = record
            path_scores[key] = max(path_scores.get(key, 0.0), contribution)
            path_ranks[key].append(rank)
            path_ids[key].append(candidate.path_id)
            _extend_unique(discovery_sources[key], ["relation_path"])
            if "exploration" in hit.route_modes:
                _extend_unique(discovery_sources[key], ["relation_path:exploration"])
        valid_paths.append((rank, hit, keys))

    def combined_score(key: tuple[str, str]) -> float:
        return base_scores.get(key, 0.0) + path_scores.get(key, 0.0)

    selected: set[tuple[str, str]] = set()
    reserved_base_keys = sorted(
        base_ranks, key=lambda key: (base_ranks[key], key)
    )[: min(base_reserve, limit)]
    selected.update(reserved_base_keys)

    retained_paths: list[HybridRelationPathEvidence] = []
    retained_path_keys: set[tuple[str, str]] = set()
    omitted_path_hits = 0
    for _, hit, keys in valid_paths:
        missing = [key for key in keys if key not in selected]
        if len(selected) + len(missing) > limit:
            omitted_path_hits += 1
            continue
        selected.update(missing)
        retained_path_keys.update(keys)
        retained_paths.append(
            HybridRelationPathEvidence(
                hit=hit,
                supporting_memory_ids=list(hit.candidate.supporting_memory_ids),
            )
        )

    remaining = sorted(
        (
            key
            for key in set(base_ranks).union(retained_path_keys)
            if key not in selected
        ),
        key=lambda key: (-combined_score(key), key),
    )
    selected.update(remaining[: max(limit - len(selected), 0)])
    ordered = sorted(selected, key=lambda key: (-combined_score(key), key))
    candidates = [
        HybridRetrievalCandidate(
            record=records[key],
            rrf_score=combined_score(key),
            discovery_sources=discovery_sources[key],
            base_rank=base_ranks.get(key),
            path_ranks=path_ranks[key],
            path_ids=path_ids[key],
        )
        for key in ordered
    ]
    return HybridRetrievalAssembly(
        candidates=candidates,
        relation_paths=retained_paths,
        input_base_hits=len(base_hits),
        input_path_hits=len(path_hits),
        rejected_base_hits=rejected_base_hits,
        rejected_path_hits=rejected_path_hits,
        omitted_path_hits=omitted_path_hits,
        truncated=(
            len(selected) < len(records)
            or omitted_path_hits > 0
            or rejected_base_hits > 0
            or rejected_path_hits > 0
        ),
    )


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
        list[Literal["exact", "candidate", "exploration"]],
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


def rank_explored_relation_paths(
    candidates: Sequence[RelationPathCandidate],
    *,
    limit: int = 10,
    rrf_k: int = 60,
) -> list[RelationPathRetrievalHit]:
    """Wrap Store-revalidated exploration results for bounded hybrid assembly."""

    if limit <= 0:
        return []
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")
    unique: dict[
        tuple[str, tuple[str, ...], tuple[str, ...]], RelationPathCandidate
    ] = {}
    for candidate in candidates:
        key = _candidate_key(candidate)
        existing = unique.get(key)
        if existing is None or candidate.score > existing.score:
            unique[key] = candidate
    ordered = sorted(
        unique.values(),
        key=lambda item: (-item.score, item.scope.scope_key, item.path_id),
    )[:limit]
    return [
        RelationPathRetrievalHit(
            candidate=candidate,
            route_indexes=[0],
            route_modes=["exploration"],
            rrf_score=1.0 / (rrf_k + rank),
        )
        for rank, candidate in enumerate(ordered, start=1)
    ]


def merge_relation_path_hits(
    *groups: Sequence[RelationPathRetrievalHit],
    limit: int = 10,
) -> list[RelationPathRetrievalHit]:
    """Merge typed and explored paths without duplicate-source score inflation."""

    if limit <= 0:
        return []
    candidates: dict[
        tuple[str, tuple[str, ...], tuple[str, ...]], RelationPathCandidate
    ] = {}
    scores: defaultdict[
        tuple[str, tuple[str, ...], tuple[str, ...]],
        dict[Literal["exact", "candidate", "exploration"], float],
    ] = defaultdict(dict)
    indexes: defaultdict[
        tuple[str, tuple[str, ...], tuple[str, ...]], list[int]
    ] = defaultdict(list)
    modes: defaultdict[
        tuple[str, tuple[str, ...], tuple[str, ...]],
        list[Literal["exact", "candidate", "exploration"]],
    ] = defaultdict(list)
    for group in groups:
        for hit in group:
            key = _candidate_key(hit.candidate)
            existing = candidates.get(key)
            if existing is None or hit.candidate.score > existing.score:
                candidates[key] = hit.candidate
            for route_index in hit.route_indexes:
                if route_index not in indexes[key]:
                    indexes[key].append(route_index)
            for mode in hit.route_modes:
                scores[key][mode] = max(scores[key].get(mode, 0.0), hit.rrf_score)
                if mode not in modes[key]:
                    modes[key].append(mode)
    ordered = sorted(
        candidates,
        key=lambda key: (
            -sum(scores[key].values()),
            -candidates[key].score,
            candidates[key].scope.scope_key,
            candidates[key].path_id,
        ),
    )[:limit]
    return [
        RelationPathRetrievalHit(
            candidate=candidates[key],
            route_indexes=indexes[key] or [0],
            route_modes=modes[key],
            rrf_score=sum(scores[key].values()),
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


def _record_matches_filter(record: MemoryRecord, filters: MemoryFilter) -> bool:
    """Mirror the backend-neutral ``MemoryFilter`` contract after Store reload."""

    if filters.states is not None:
        if record.state not in filters.states:
            return False
    elif not filters.include_inactive and record.state not in ACTIVE_MEMORY_STATES:
        return False
    if filters.kinds is not None and record.kind not in filters.kinds:
        return False
    if filters.actors is not None and record.actor not in filters.actors:
        return False
    if filters.exclude_actors is not None and record.actor in filters.exclude_actors:
        return False
    if filters.authorities is not None and record.authority not in filters.authorities:
        return False
    if (
        filters.exclude_authorities is not None
        and record.authority in filters.exclude_authorities
    ):
        return False
    if filters.tags is not None and not filters.tags.issubset(record.tags):
        return False
    if filters.importance_min is not None and record.importance < filters.importance_min:
        return False
    if filters.time_from is not None and record.created_at < filters.time_from:
        return False
    return not (filters.time_to is not None and record.created_at > filters.time_to)


def _extend_unique(target: list[str], values: Sequence[str]) -> None:
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in target:
            target.append(normalized)
