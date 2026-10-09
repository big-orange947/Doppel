"""Opt-in high-resource retrieval composition; no answers or benchmark labels.

This module wires the existing query engine and evidence-rich graph policy. It
does not replace the stable default, build indices, or certify index coverage.
Raw dialogue remains a separate evidence channel, never an owner fact.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryFilter,
    MemoryIsolationError,
    MemoryRecord,
    MemoryScope,
    MemoryState,
)
from doppel_memory.personal_rerank import (
    PersonalMemoryRerankConfig,
    PersonalMemoryReranker,
    PersonalMemoryRerankItem,
    PersonalMemoryRerankRequest,
    score_personal_memories,
)
from doppel_memory.query import (
    PersonalMemoryQueryConfig,
    PersonalMemoryQueryDraftV2,
    PersonalMemoryQueryEngine,
    PersonalMemoryQueryPlanV2,
    PersonalMemoryQueryRequest,
    PersonalMemoryQueryResult,
    _observation_cutoff,
    _query_memory_filter,
    _structural_rejection_reason,
)
from doppel_memory.query_path import (
    PersonalMemoryRelationPathDraftV4,
    PersonalMemoryRelationPathPlannerV4,
)
from doppel_memory.relation import (
    RelationIndex,
    RelationPathCandidate,
    RelationPathExploreIndex,
    RelationPathExploreQuery,
    RelationPathIndex,
    RelationReranker,
    RelationTypeDefinition,
)
from doppel_memory.relation_path_retrieval import (
    EvidenceRichHybridRetrievalConfig,
    EvidenceRichHybridRetrievalResult,
    assemble_evidence_rich_hybrid_retrieval,
    build_relation_path_retrieval_plan,
    search_relation_path_routes,
)
from doppel_memory.store import MemoryStore
from doppel_memory.vector import SemanticIndex


class SourceResolver(Protocol):
    """Host's durable source-event mapping; returned records are reloaded again."""

    async def resolve_event(
        self, scope: MemoryScope, evidence_id: str
    ) -> MemoryRecord | None: ...


class HighConfigRetrievalResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: str = "personal-high-config-v1"
    base: PersonalMemoryQueryResult
    hybrid: EvidenceRichHybridRetrievalResult | None = None
    raw_dialogue: list[MemoryRecord] = Field(default_factory=list)
    backing_sources: list[MemoryRecord] = Field(default_factory=list)
    path_decision: str
    graph_path_searches: int = 0
    graph_exploration_searches: int = 0
    rejected_paths: int = 0
    source_failures: int = 0
    warnings: list[str] = Field(default_factory=list)
    # A configured client is not proof that this corpus has been graph-indexed.
    index_coverage_certified: bool = False


class _CapturedPlanner:
    """One request-local capture; concurrent requests cannot overwrite a draft."""

    def __init__(self, planner: PersonalMemoryRelationPathPlannerV4) -> None:
        self.name, self.version = planner.name, planner.version
        self.planner = planner
        self.draft: PersonalMemoryRelationPathDraftV4 | None = None

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraftV2:
        self.draft = PersonalMemoryRelationPathDraftV4.model_validate(
            await self.planner.plan(request)
        )
        fields = self.draft.model_dump()
        projected = {
            key: fields[key] for key in PersonalMemoryQueryDraftV2.model_fields
        }
        projected["schema_version"] = 2
        return PersonalMemoryQueryDraftV2.model_validate(projected)


class HighConfigRetrieval:
    """Natural planning + lexical/vector/relations + graph paths + source backing.

    Dependencies are mandatory. Backend errors propagate; scorer degradation is
    visible. A host must separately audit corpus/index readiness before publishing
    a high-config score. No domain dictionary, oracle plan or answer generation.
    """

    def __init__(
        self,
        store: MemoryStore,
        *,
        semantic_index: SemanticIndex,
        relation_index: RelationIndex,
        path_index: RelationPathIndex,
        exploration_index: RelationPathExploreIndex,
        planner: PersonalMemoryRelationPathPlannerV4,
        memory_reranker: PersonalMemoryReranker,
        path_reranker: RelationReranker,
        source_resolver: SourceResolver,
        relation_definitions: Sequence[RelationTypeDefinition],
        query_config: PersonalMemoryQueryConfig | None = None,
        rerank_config: PersonalMemoryRerankConfig | None = None,
        hybrid_config: EvidenceRichHybridRetrievalConfig | None = None,
        raw_candidate_limit: int = 80,
        raw_output_limit: int = 20,
        source_limit: int = 80,
    ) -> None:
        if not relation_definitions:
            raise ValueError("high-config retrieval requires host relation definitions")
        if any(
            value is None
            for value in (
                semantic_index,
                relation_index,
                path_index,
                exploration_index,
                planner,
                memory_reranker,
                path_reranker,
                source_resolver,
            )
        ):
            raise ValueError("all high-config dependencies are required")
        if not (1 <= raw_output_limit <= raw_candidate_limit <= 1000) or not (
            1 <= source_limit <= 1000
        ):
            raise ValueError("invalid high-config retrieval bounds")
        self.store, self.semantic_index = store, semantic_index
        self.path_index, self.exploration_index = path_index, exploration_index
        self.planner, self.memory_reranker = planner, memory_reranker
        self.path_reranker, self.source_resolver = path_reranker, source_resolver
        self.definitions = list(relation_definitions)
        # Validate the host ontology without asking a model or reading any data.
        PersonalMemoryQueryRequest(
            query="validate host configuration",
            now=datetime.now().astimezone(),
            relation_type_definitions=self.definitions,
        )
        self.rerank_config = rerank_config or PersonalMemoryRerankConfig(
            max_candidates=100, timeout_seconds=120
        )
        self.hybrid_config = hybrid_config or EvidenceRichHybridRetrievalConfig()
        self.raw_candidate_limit, self.raw_output_limit = (
            raw_candidate_limit,
            raw_output_limit,
        )
        self.source_limit = source_limit
        self.engine = PersonalMemoryQueryEngine(
            store,
            query_config
            or PersonalMemoryQueryConfig(
                limit=100,
                candidate_fusion="union",
                semantic_fallback_to_lexical=False,
                relation_fallback_to_nonrelation=False,
            ),
            semantic_index=semantic_index,
            relation_index=relation_index,
            memory_reranker=memory_reranker,
            rerank_config=self.rerank_config,
        )

    async def query(
        self,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        now: datetime,
        calendar_timezone: str = "UTC",
        default_subject: str = Actor.OWNER,
        default_subject_id: str = "",
        allowed_subject_ids: Sequence[str] = (),
        trace_limit: int = 0,
        observed_until: datetime | None = None,
    ) -> HighConfigRetrievalResult:
        capture = _CapturedPlanner(self.planner)
        plan = await self.engine.plan(
            capture,
            query,
            scopes,
            now=now,
            calendar_timezone=calendar_timezone,
            default_subject=default_subject,
            default_subject_id=default_subject_id,
            allowed_subject_ids=allowed_subject_ids,
            relation_type_definitions=self.definitions,
            observed_until=observed_until,
        )
        if not isinstance(plan, PersonalMemoryQueryPlanV2):
            raise TypeError("high-config composition requires a bound V2 plan")
        base = await self.engine.execute(plan, trace_limit=trace_limit)
        draft = capture.draft
        if draft is None:
            raise RuntimeError("planner did not produce a path draft")
        result = HighConfigRetrievalResult(base=base, path_decision=draft.path_decision)
        warnings = list(base.warnings)
        if base.memory_reranking and base.memory_reranking.status not in {
            "completed",
            "not_run",
        }:
            warnings.append("memory_reranker_degraded")
        # A top-k graph branch must never manufacture or replace an exact count.
        if plan.operation == "count":
            return await self._evidence_channels(
                result, plan, query, [hit.record for hit in base.hits], warnings
            )

        # Use the host-bound, calendar-grounded plan, not the model's raw dates/ID.
        grounded = draft.model_copy(
            update={
                "subject": plan.subject,
                "subject_id": plan.subject_id,
                "entity_mentions": plan.entity_mentions,
                "search_text": plan.search_text,
                "as_of": plan.as_of,
                "time_from": plan.time_from,
                "time_to": plan.time_to,
            }
        )
        types = [item.name for item in self.definitions]
        filters = _query_memory_filter(plan)
        routes = build_relation_path_retrieval_plan(
            grounded, allowed_relation_types=types
        )
        # Current validity is a trusted host time, not an extraction timestamp.
        valid_at = plan.as_of or (plan.now if plan.temporal_view == "current" else None)
        routes = routes.model_copy(update={"valid_at": valid_at})
        exact = await search_relation_path_routes(
            self.path_index,
            routes,
            plan.scopes,
            filters=filters,
            limit=self.hybrid_config.path_limit,
        )
        explored = []
        if plan.entity_mentions:
            explored = list(
                await self.exploration_index.explore_relation_paths(
                    RelationPathExploreQuery(
                        query_text=query,
                        entity_mentions=plan.entity_mentions,
                        allowed_relation_types=types,
                        subject=plan.subject,
                        subject_id=plan.subject_id,
                        valid_at=valid_at,
                        time_from=plan.time_from,
                        time_to=plan.time_to,
                    ),
                    plan.scopes,
                    filters=filters,
                    limit=self.hybrid_config.path_limit,
                )
            )
        allowed = {scope.scope_key: scope for scope in plan.scopes}
        unique = {}
        for candidate in [*[item.candidate for item in exact], *explored]:
            if candidate.scope.scope_key not in allowed:
                raise MemoryIsolationError("graph candidate escaped authorized scopes")
            key = (candidate.scope.scope_key, candidate.path_id)
            unique.setdefault(key, candidate)
        qualified: list[RelationPathCandidate] = []
        for candidate in unique.values():
            if candidate.scope.scope_key not in allowed:
                raise MemoryIsolationError("graph candidate escaped authorized scopes")
            valid = True
            for hop in candidate.hops:
                if hop.relation_type not in types:
                    raise ValueError("graph path uses a type outside the host ontology")
                if valid_at is not None and (
                    (hop.valid_at is not None and hop.valid_at > valid_at)
                    or (hop.invalid_at is not None and hop.invalid_at < valid_at)
                ):
                    valid = False
                if (
                    plan.time_to is not None
                    and hop.valid_at is not None
                    and hop.valid_at > plan.time_to
                ):
                    valid = False
                if (
                    plan.time_from is not None
                    and hop.invalid_at is not None
                    and hop.invalid_at < plan.time_from
                ):
                    valid = False
            for memory_id in candidate.supporting_memory_ids:
                record = await self.store.get(
                    allowed[candidate.scope.scope_key], memory_id
                )
                if (
                    record is not None
                    and record.scope.scope_key != candidate.scope.scope_key
                ):
                    raise MemoryIsolationError("graph Store reload escaped scope")
                if record is None or _structural_rejection_reason(record, plan):
                    valid = False
                    break
            if valid:
                qualified.append(candidate)
        hybrid = await assemble_evidence_rich_hybrid_retrieval(
            self.store,
            base.hits,
            qualified,
            plan.scopes,
            query_text=query,
            reranker=self.path_reranker,
            filters=filters,
            config=self.hybrid_config,
        )
        for item in hybrid.assembly.candidates:
            if _structural_rejection_reason(item.record, plan):
                raise RuntimeError("assembled memory no longer satisfies bound plan")
        if hybrid.path_reranking.status == "fallback":
            warnings.append("path_reranker_degraded")

        result = result.model_copy(
            update={
                "hybrid": hybrid,
                "rejected_paths": len(unique) - len(qualified),
                "graph_path_searches": len(routes.routes),
                "graph_exploration_searches": int(bool(plan.entity_mentions)),
            }
        )
        return await self._evidence_channels(
            result,
            plan,
            query,
            [item.record for item in hybrid.assembly.candidates],
            warnings,
        )

    async def _evidence_channels(
        self,
        result: HighConfigRetrievalResult,
        plan: PersonalMemoryQueryPlanV2,
        query: str,
        memories: Sequence[MemoryRecord],
        warnings: list[str],
    ) -> HighConfigRetrievalResult:
        """Supply bounded raw/source evidence without altering aggregation.

        Count queries need source evidence too. Neither raw top-k nor source
        backing upgrades an indeterminate predicate count to an exact one.
        """
        allowed = {scope.scope_key: scope for scope in plan.scopes}
        observation_clock = _observation_cutoff(plan)

        # Raw dialogue is useful evidence about what was said, including assistant
        # suggestions, but must not enter the factual owner-memory engine.
        raw = []
        for item in await self.semantic_index.search(
            query,
            plan.scopes,
            filters=MemoryFilter(
                states={MemoryState.CONFIRMED},
                kinds={"event"},
                time_to=observation_clock,
            ),
            limit=self.raw_candidate_limit,
        ):
            if item.scope is None or item.scope.scope_key not in allowed:
                raise MemoryIsolationError("raw candidate escaped authorized scopes")
            record = await self.store.get(allowed[item.scope.scope_key], item.memory_id)
            if (
                record is not None
                and self._raw_eligible(record, item.scope, observation_clock)
                and record.memory_id not in {r.memory_id for r in raw}
            ):
                raw.append(record)
        scores, summary = await score_personal_memories(
            self.memory_reranker,
            PersonalMemoryRerankRequest(
                question=query,
                items=[
                    PersonalMemoryRerankItem(
                        item_id=f"raw_{index}", content=record.content
                    )
                    for index, record in enumerate(raw)
                ],
            ),
            config=self.rerank_config,
            total_candidates=len(raw),
        )
        if summary.status not in {"completed", "not_run"}:
            warnings.append("raw_reranker_degraded")
        raw = sorted(
            enumerate(raw), key=lambda pair: (-scores.get(f"raw_{pair[0]}", 0), pair[0])
        )
        raw_records = [record for _, record in raw[: self.raw_output_limit]]
        backing: dict[str, MemoryRecord] = {}
        failures = 0
        truncated = False
        for memory in memories:
            evidence = memory.metadata.get("evidence", [])
            if not isinstance(evidence, list) or not evidence:
                failures += 1
                continue
            for reference in evidence:
                event = (
                    reference.get("evidence_id")
                    if isinstance(reference, dict)
                    else None
                )
                if not isinstance(event, str) or not event:
                    failures += 1
                    continue
                resolved = await self.source_resolver.resolve_event(memory.scope, event)
                record = (
                    await self.store.get(memory.scope, resolved.memory_id)
                    if resolved
                    else None
                )
                if (
                    record is None
                    or record.source_event_id != event
                    or not self._raw_eligible(record, memory.scope, observation_clock)
                    or record.actor != memory.actor
                    or record.authority != memory.authority
                ):
                    failures += 1
                    continue
                if record.memory_id in backing:
                    continue
                if len(backing) >= self.source_limit:
                    truncated = True
                    continue
                backing[record.memory_id] = record
        if failures:
            warnings.append("source_backing_incomplete")
        if truncated:
            warnings.append("source_backing_limit_reached")
        return result.model_copy(
            update={
                "raw_dialogue": raw_records,
                "backing_sources": list(backing.values()),
                "warnings": warnings,
                "source_failures": failures,
            }
        )

    @staticmethod
    def _raw_eligible(record: MemoryRecord, scope: MemoryScope, now: datetime) -> bool:
        if record.scope.scope_key != scope.scope_key:
            raise MemoryIsolationError("raw Store reload escaped scope")
        return (
            record.extractor == "ingestor"
            and record.kind == "event"
            and record.state == MemoryState.CONFIRMED
            and bool(record.source_event_id)
            and record.actor in {Actor.OWNER, Actor.AGENT}
            and record.authority == FactAuthority.of(record.actor)
            and record.created_at <= now
        )
