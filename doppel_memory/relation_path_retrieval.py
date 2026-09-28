"""Experimental union retrieval for exact and candidate relation paths.

The models in this module are additive and are not wired into the stable query engine.
They make one boundary explicit: a typed graph path may contribute candidates, but it
must never suppress independent semantic retrieval.  Exact and widened candidate paths
remain bounded, ontology-governed, scope-bound, time-filtered, and Store-revalidated by
the supplied :class:`~doppel_memory.relation.RelationPathIndex`.
"""

from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
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
    RelationReranker,
    RelationRerankItem,
    RelationRerankRequest,
    RelationRerankScore,
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


class RelationPathSemanticRerankResult(BaseModel):
    """Auditable reorder-only result for explored paths awaiting Store validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hits: list[RelationPathRetrievalHit] = Field(default_factory=list)
    status: Literal["completed", "not_run", "fallback"]
    error_type: str = ""

    @field_validator("error_type", mode="before")
    @classmethod
    def _normalize_error_type(cls, value: object) -> str:
        return str(value or "").strip()

    @model_validator(mode="after")
    def _validate_status(self) -> RelationPathSemanticRerankResult:
        if self.status == "fallback" and not self.error_type:
            raise ValueError("fallback path reranking requires an error_type")
        if self.status != "fallback" and self.error_type:
            raise ValueError("successful path reranking cannot report an error_type")
        return self


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


HybridRejectionReason = Literal[
    "unauthorized_scope",
    "store_missing",
    "scope_mismatch",
    "filter_mismatch",
    "path_support_limit",
]


class HybridRetrievalAssembly(BaseModel):
    """Bounded, auditable union of independent and typed-path candidates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: list[HybridRetrievalCandidate] = Field(default_factory=list)
    relation_paths: list[HybridRelationPathEvidence] = Field(default_factory=list)
    input_base_hits: int = Field(ge=0)
    input_path_hits: int = Field(ge=0)
    rejected_base_hits: int = Field(ge=0)
    rejected_path_hits: int = Field(ge=0)
    rejected_base_reasons: dict[HybridRejectionReason, int] = Field(
        default_factory=dict
    )
    rejected_path_reasons: dict[HybridRejectionReason, int] = Field(
        default_factory=dict
    )
    omitted_path_hits: int = Field(ge=0)
    truncated: bool = False

    @model_validator(mode="after")
    def _validate_rejection_accounting(self) -> HybridRetrievalAssembly:
        if sum(self.rejected_base_reasons.values()) != self.rejected_base_hits:
            raise ValueError(
                "base rejection reasons must account for every rejected hit"
            )
        if sum(self.rejected_path_reasons.values()) != self.rejected_path_hits:
            raise ValueError(
                "path rejection reasons must account for every rejected hit"
            )
        return self


class EvidenceRichHybridRetrievalConfig(BaseModel):
    """Versioned defaults for the opt-in V8 evidence-rich composition policy.

    The policy is intentionally separate from the stable query engine. Callers may
    lower output bounds for their context budget, but changing a default creates a
    different, unevaluated deployment profile.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    policy: Literal["evidence_rich_v1"] = "evidence_rich_v1"
    path_limit: int = Field(default=20, ge=1, le=100)
    output_limit: int = Field(default=20, ge=1, le=100)
    base_reserve: int = Field(default=5, ge=0, le=100)
    literal_entity_reserve: int = Field(default=1, ge=0, le=100)
    path_evidence_reserve: Literal[1] = 1
    rrf_k: int = Field(default=60, ge=1)
    base_weight: float = Field(default=1.0, gt=0.0)
    path_weight: float = Field(default=0.8, gt=0.0)
    max_path_support: int = Field(default=8, ge=1, le=100)

    @model_validator(mode="after")
    def _validate_reserves(self) -> EvidenceRichHybridRetrievalConfig:
        if self.literal_entity_reserve > self.base_reserve:
            raise ValueError("literal entity reserve cannot exceed base reserve")
        if self.base_reserve > self.output_limit:
            raise ValueError("base reserve cannot exceed output limit")
        return self


class EvidenceRichHybridRetrievalResult(BaseModel):
    """Auditable output from the named evidence-rich experimental policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: Literal["evidence_rich_v1"] = "evidence_rich_v1"
    configuration: EvidenceRichHybridRetrievalConfig
    path_reranking: RelationPathSemanticRerankResult
    promoted_path_hits: list[RelationPathRetrievalHit] = Field(default_factory=list)
    assembly: HybridRetrievalAssembly


async def assemble_hybrid_retrieval_candidates(
    store: MemoryStore,
    base_hits: Sequence[PersonalMemoryQueryHit],
    path_hits: Sequence[RelationPathRetrievalHit],
    scopes: Sequence[MemoryScope],
    *,
    filters: MemoryFilter,
    limit: int = 10,
    base_reserve: int = 5,
    literal_entity_reserve: int = 0,
    path_evidence_reserve: int = 0,
    preserve_base_reserve_order: bool = False,
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
    if (
        limit < 0
        or base_reserve < 0
        or literal_entity_reserve < 0
        or path_evidence_reserve < 0
    ):
        raise ValueError("hybrid retrieval limits must not be negative")
    if literal_entity_reserve > base_reserve:
        raise ValueError("literal entity reserve cannot exceed base reserve")
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
    literal_entity_keys: set[tuple[str, str]] = set()
    base_scores: dict[tuple[str, str], float] = {}
    path_scores: dict[tuple[str, str], float] = {}
    path_ranks: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
    path_ids: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    discovery_sources: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    rejected_base_reasons: Counter[HybridRejectionReason] = Counter()

    async def reload(
        scope: MemoryScope, memory_id: str
    ) -> tuple[MemoryRecord | None, HybridRejectionReason | None]:
        if scope.scope_key not in allowed_scopes:
            return None, "unauthorized_scope"
        record = await store.get(allowed_scopes[scope.scope_key], memory_id)
        if record is None:
            return None, "store_missing"
        if record.scope.scope_key != scope.scope_key:
            return None, "scope_mismatch"
        if not _record_matches_filter(record, filters):
            return None, "filter_mismatch"
        return record, None

    for rank, hit in enumerate(base_hits, start=1):
        record, rejection = await reload(hit.record.scope, hit.record.memory_id)
        if record is None:
            if rejection is None:  # pragma: no cover - defensive type narrowing
                raise RuntimeError("rejected base hit has no rejection reason")
            rejected_base_reasons[rejection] += 1
            continue
        key = (record.scope.scope_key, record.memory_id)
        records[key] = record
        if key not in base_ranks or rank < base_ranks[key]:
            base_ranks[key] = rank
            base_scores[key] = base_weight / (rrf_k + rank)
        if hit.candidate_evidence.entity_binding == "literal":
            literal_entity_keys.add(key)
        _extend_unique(discovery_sources[key], ["independent"])
        _extend_unique(discovery_sources[key], hit.candidate_evidence.sources)

    valid_paths: list[tuple[int, RelationPathRetrievalHit, list[tuple[str, str]]]] = []
    rejected_path_reasons: Counter[HybridRejectionReason] = Counter()
    for rank, hit in enumerate(path_hits, start=1):
        candidate = hit.candidate
        support_ids = candidate.supporting_memory_ids
        if candidate.scope.scope_key not in allowed_scopes:
            rejected_path_reasons["unauthorized_scope"] += 1
            continue
        if len(support_ids) > max_path_support:
            rejected_path_reasons["path_support_limit"] += 1
            continue
        loaded: list[MemoryRecord] = []
        path_rejection: HybridRejectionReason | None = None
        for memory_id in support_ids:
            record, rejection = await reload(candidate.scope, memory_id)
            if record is None:
                loaded = []
                path_rejection = rejection
                break
            loaded.append(record)
        if len(loaded) != len(support_ids):
            if path_rejection is None:  # pragma: no cover - defensive invariant
                raise RuntimeError("rejected path hit has no rejection reason")
            rejected_path_reasons[path_rejection] += 1
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

    selected_literal_keys = set(
        sorted(literal_entity_keys, key=lambda key: (base_ranks[key], key))[
            : min(literal_entity_reserve, base_reserve, limit)
        ]
    )
    selected: set[tuple[str, str]] = set(selected_literal_keys)
    reserved_base_keys = sorted(
        (key for key in base_ranks if key not in selected_literal_keys),
        key=lambda key: (base_ranks[key], key),
    )[: min(max(base_reserve - len(selected), 0), max(limit - len(selected), 0))]
    selected.update(reserved_base_keys)
    for key in selected_literal_keys:
        _extend_unique(discovery_sources[key], ["entity_anchor_reserve"])

    retained_paths: list[HybridRelationPathEvidence] = []
    retained_path_keys: set[tuple[str, str]] = set()
    reserved_path_keys: set[tuple[str, str]] = set()
    reserved_path_count = 0
    omitted_path_hits = 0
    for _, hit, keys in valid_paths:
        missing = [key for key in keys if key not in selected]
        if len(selected) + len(missing) > limit:
            omitted_path_hits += 1
            continue
        selected.update(missing)
        retained_path_keys.update(keys)
        if reserved_path_count < path_evidence_reserve:
            reserved_path_keys.update(keys)
            reserved_path_count += 1
        retained_paths.append(
            HybridRelationPathEvidence(
                hit=hit,
                supporting_memory_ids=list(hit.candidate.supporting_memory_ids),
            )
        )
    for key in reserved_path_keys:
        _extend_unique(discovery_sources[key], ["path_evidence_reserve"])

    remaining = sorted(
        (
            key
            for key in set(base_ranks).union(retained_path_keys)
            if key not in selected
        ),
        key=lambda key: (-combined_score(key), key),
    )
    selected.update(remaining[: max(limit - len(selected), 0)])
    if preserve_base_reserve_order:
        reserved_base_order = {
            key: rank
            for rank, key in enumerate(
                [
                    *sorted(
                        selected_literal_keys,
                        key=lambda item: (base_ranks[item], item),
                    ),
                    *reserved_base_keys,
                ]
            )
        }
        ordered = sorted(
            selected,
            key=lambda key: (
                0
                if key in reserved_base_order
                else 1
                if key in reserved_path_keys
                else 2,
                reserved_base_order.get(key, 0),
                -combined_score(key),
                key,
            ),
        )
    else:
        ordered = sorted(
            selected,
            key=lambda key: (
                key not in selected_literal_keys,
                key not in reserved_path_keys,
                -combined_score(key),
                key,
            ),
        )
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
        rejected_base_hits=sum(rejected_base_reasons.values()),
        rejected_path_hits=sum(rejected_path_reasons.values()),
        rejected_base_reasons=dict(sorted(rejected_base_reasons.items())),
        rejected_path_reasons=dict(sorted(rejected_path_reasons.items())),
        omitted_path_hits=omitted_path_hits,
        truncated=(
            len(selected) < len(records)
            or omitted_path_hits > 0
            or bool(rejected_base_reasons)
            or bool(rejected_path_reasons)
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
    prefer_complete_paths: bool = False,
) -> list[RelationPathRetrievalHit]:
    """Wrap Store-revalidated exploration results for bounded hybrid assembly.

    ``prefer_complete_paths`` is an opt-in recall policy for callers that want a
    complete bounded evidence chain ahead of one of its redundant strict prefixes.
    An unrelated one-hop path is not demoted merely because a different two-hop path
    exists. The policy never creates a path, changes its authority, or expands the
    two-hop exploration bound.
    """

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
    signatures = {
        key: tuple((hop.edge_id, hop.direction) for hop in candidate.hops)
        for key, candidate in unique.items()
    }
    strict_prefixes = {
        key
        for key, signature in signatures.items()
        if any(
            len(other) > len(signature) and other[: len(signature)] == signature
            for other in signatures.values()
        )
    }
    ordered = sorted(
        unique.items(),
        key=lambda pair: (
            pair[0] in strict_prefixes if prefer_complete_paths else False,
            -pair[1].score,
            pair[1].scope.scope_key,
            pair[1].path_id,
        ),
    )[:limit]
    return [
        RelationPathRetrievalHit(
            candidate=candidate,
            route_indexes=[0],
            route_modes=["exploration"],
            rrf_score=1.0 / (rrf_k + rank),
        )
        for rank, (_, candidate) in enumerate(ordered, start=1)
    ]


async def rerank_explored_relation_paths(
    candidates: Sequence[RelationPathCandidate],
    *,
    query_text: str,
    reranker: RelationReranker,
    limit: int = 10,
    rrf_k: int = 60,
    prefer_complete_paths: bool = True,
) -> RelationPathSemanticRerankResult:
    """Semantically reorder explored paths without granting retrieval authority.

    The scorer receives only opaque item IDs plus ordered relation types and facts.
    Scope, subject, memory IDs, authority, lifecycle, and provenance never cross the
    scoring boundary. Missing, duplicated, unknown, malformed, or failed scores cause
    a deterministic fallback to :func:`rank_explored_relation_paths`.
    """

    fallback = rank_explored_relation_paths(
        candidates,
        limit=limit,
        rrf_k=rrf_k,
        prefer_complete_paths=prefer_complete_paths,
    )
    normalized_query = str(query_text or "").strip()
    if limit <= 0 or not candidates or not normalized_query:
        return RelationPathSemanticRerankResult(
            hits=fallback,
            status="not_run",
        )

    unique: dict[
        tuple[str, tuple[str, ...], tuple[str, ...]], RelationPathCandidate
    ] = {}
    for candidate in candidates:
        key = _candidate_key(candidate)
        existing = unique.get(key)
        if existing is None or candidate.score > existing.score:
            unique[key] = candidate
    entries = list(unique.items())
    item_ids = [f"path-{index:03d}" for index in range(len(entries))]
    items = [
        RelationRerankItem(
            item_id=item_id,
            relation_type=" -> ".join(hop.relation_type for hop in candidate.hops),
            fact="\n".join(hop.fact for hop in candidate.hops if hop.fact),
        )
        for item_id, (_, candidate) in zip(item_ids, entries, strict=True)
    ]
    allowed_ids = set(item_ids)
    try:
        raw_scores = await reranker.rerank(
            RelationRerankRequest(query_text=normalized_query, items=items)
        )
        scores: dict[str, float] = {}
        for raw_score in raw_scores:
            score = RelationRerankScore.model_validate(raw_score)
            if score.item_id not in allowed_ids:
                raise ValueError("path reranker returned an unknown item ID")
            if score.item_id in scores:
                raise ValueError("path reranker returned a duplicate item ID")
            scores[score.item_id] = score.score
        if set(scores) != allowed_ids:
            raise ValueError("path reranker omitted one or more item IDs")

        signatures = {
            key: tuple((hop.edge_id, hop.direction) for hop in candidate.hops)
            for key, candidate in entries
        }
        strict_prefixes = {
            key
            for key, signature in signatures.items()
            if any(
                len(other) > len(signature) and other[: len(signature)] == signature
                for other in signatures.values()
            )
        }
        scored = list(zip(item_ids, entries, strict=True))
        scored.sort(
            key=lambda item: (
                -scores[item[0]],
                item[1][0] in strict_prefixes if prefer_complete_paths else False,
                -item[1][1].score,
                item[1][1].scope.scope_key,
                item[1][1].path_id,
            )
        )
        hits = [
            RelationPathRetrievalHit(
                candidate=candidate,
                route_indexes=[0],
                route_modes=["exploration"],
                rrf_score=1.0 / (rrf_k + rank),
            )
            for rank, (_, (_, candidate)) in enumerate(scored[:limit], start=1)
        ]
        return RelationPathSemanticRerankResult(
            hits=hits,
            status="completed",
        )
    except Exception as exc:  # noqa: BLE001 - optional scorer fails closed
        return RelationPathSemanticRerankResult(
            hits=fallback,
            status="fallback",
            error_type=type(exc).__name__,
        )


def promote_semantic_path_completions(
    hits: Sequence[RelationPathRetrievalHit],
    *,
    rrf_k: int = 60,
) -> list[RelationPathRetrievalHit]:
    """Move the best semantic extension immediately before its strict prefix.

    Semantic ranking still chooses the relevant first-hop family.  This topology-only
    pass prevents that family's one-hop prefix from consuming an atomic path reserve
    while its already-retrieved two-hop evidence is flattened later.  It never compares
    relation names or facts and cannot add, remove, or authorize a candidate.
    """

    if not hits:
        return []
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")

    ordered = list(hits)
    scope_keys = [hit.candidate.scope.scope_key for hit in ordered]
    signatures = [
        tuple((hop.edge_id, hop.direction) for hop in hit.candidate.hops)
        for hit in ordered
    ]
    promotions: dict[int, int] = {}
    claimed_extensions: set[int] = set()
    for prefix_index, prefix in enumerate(signatures):
        extensions = [
            index
            for index, signature in enumerate(signatures)
            if index not in claimed_extensions
            and scope_keys[index] == scope_keys[prefix_index]
            and len(signature) > len(prefix)
            and signature[: len(prefix)] == prefix
        ]
        if not extensions:
            continue
        best_extension = min(extensions)
        if best_extension > prefix_index:
            promotions[best_extension] = prefix_index
            claimed_extensions.add(best_extension)

    ranked = sorted(
        enumerate(ordered),
        key=lambda item: (
            promotions.get(item[0], item[0]),
            item[0] not in promotions,
            item[0],
        ),
    )
    return [
        hit.model_copy(update={"rrf_score": 1.0 / (rrf_k + rank)})
        for rank, (_, hit) in enumerate(ranked, start=1)
    ]


async def assemble_evidence_rich_hybrid_retrieval(
    store: MemoryStore,
    base_hits: Sequence[PersonalMemoryQueryHit],
    explored_candidates: Sequence[RelationPathCandidate],
    scopes: Sequence[MemoryScope],
    *,
    query_text: str,
    reranker: RelationReranker,
    filters: MemoryFilter,
    config: EvidenceRichHybridRetrievalConfig | None = None,
) -> EvidenceRichHybridRetrievalResult:
    """Run the evaluated V8 path-rerank, completion, and Store assembly policy.

    This helper is opt-in and module-only. It does not plan scopes or paths and it
    does not claim answer sufficiency. The semantic scorer can only reorder the
    supplied exploration membership; topology completion preserves that membership;
    and every flattened memory is still reloaded from the authoritative Store.
    Scorer failure remains visible in ``path_reranking.status`` and falls back to the
    deterministic bounded path order before the same Store-backed assembly.
    """

    bound = EvidenceRichHybridRetrievalConfig.model_validate(
        config or EvidenceRichHybridRetrievalConfig()
    )
    path_reranking = await rerank_explored_relation_paths(
        explored_candidates,
        query_text=query_text,
        reranker=reranker,
        limit=bound.path_limit,
        rrf_k=bound.rrf_k,
        prefer_complete_paths=True,
    )
    promoted = promote_semantic_path_completions(
        path_reranking.hits,
        rrf_k=bound.rrf_k,
    )
    assembly = await assemble_hybrid_retrieval_candidates(
        store,
        base_hits,
        promoted,
        scopes,
        filters=filters,
        limit=bound.output_limit,
        base_reserve=bound.base_reserve,
        literal_entity_reserve=bound.literal_entity_reserve,
        path_evidence_reserve=bound.path_evidence_reserve,
        preserve_base_reserve_order=False,
        rrf_k=bound.rrf_k,
        base_weight=bound.base_weight,
        path_weight=bound.path_weight,
        max_path_support=bound.max_path_support,
    )
    return EvidenceRichHybridRetrievalResult(
        configuration=bound,
        path_reranking=path_reranking,
        promoted_path_hits=promoted,
        assembly=assembly,
    )


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
    indexes: defaultdict[tuple[str, tuple[str, ...], tuple[str, ...]], list[int]] = (
        defaultdict(list)
    )
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
    if (
        filters.importance_min is not None
        and record.importance < filters.importance_min
    ):
        return False
    if filters.time_from is not None and record.created_at < filters.time_from:
        return False
    return not (filters.time_to is not None and record.created_at > filters.time_to)


def _extend_unique(target: list[str], values: Sequence[str]) -> None:
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in target:
            target.append(normalized)
