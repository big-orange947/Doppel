"""Structured, exact-scope planning and temporal retrieval for personal memories."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from doppel_memory.intelligence import (
    MemoryTemporalStatus,
    PersonalMemoryType,
    StructuredGenerationRequest,
    StructuredOutputModel,
)
from doppel_memory.models import (
    ACTIVE_MEMORY_STATES,
    Actor,
    MemoryFilter,
    MemoryIsolationError,
    MemoryRecord,
    MemoryScope,
)
from doppel_memory.store import MemoryStore
from doppel_memory.vector import SemanticIndex

QueryIntent = Literal[
    "lookup", "current", "history", "planned", "list", "count", "as_of"
]


class PersonalMemoryQueryIntent:
    """Closed v1 intent set; answer generation remains outside Doppel."""

    LOOKUP = "lookup"
    CURRENT = "current"
    HISTORY = "history"
    PLANNED = "planned"
    LIST = "list"
    COUNT = "count"
    AS_OF = "as_of"


class PersonalMemoryCountStatus:
    """Whether a requested episode count is safe to present as exact."""

    NOT_REQUESTED = "not_requested"
    EXACT = "exact"
    INDETERMINATE = "indeterminate"


class PersonalMemoryQueryDraft(BaseModel):
    """Planner output without authority to choose read scopes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: QueryIntent = PersonalMemoryQueryIntent.LOOKUP
    search_text: str = ""
    memory_types: list[str] = Field(default_factory=list)
    topic_keys: list[str] = Field(default_factory=list)
    temporal_statuses: list[str] = Field(default_factory=list)
    subject: str = Actor.OWNER
    subject_id: str = ""
    as_of: datetime | None = None
    time_from: datetime | None = None
    time_to: datetime | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    explanation: str = ""

    @field_validator("search_text", "subject_id", "explanation", mode="before")
    @classmethod
    def _normalize_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("subject", mode="before")
    @classmethod
    def _normalize_subject(cls, value: Any) -> str:
        return Actor.normalize(value)

    @field_validator("memory_types", "topic_keys", "temporal_statuses", mode="before")
    @classmethod
    def _normalize_namespaces(cls, value: Any) -> list[str]:
        items = [str(item or "").strip().lower() for item in list(value or [])]
        return list(dict.fromkeys(item for item in items if item))

    @field_validator("as_of", "time_from", "time_to")
    @classmethod
    def _normalize_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("query times must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_interval(self) -> PersonalMemoryQueryDraft:
        if self.time_from and self.time_to and self.time_to < self.time_from:
            raise ValueError("time_to must not precede time_from")
        if self.intent == PersonalMemoryQueryIntent.AS_OF and self.as_of is None:
            raise ValueError("as_of intent requires an as_of timestamp")
        return self


class PersonalMemoryQueryRequest(BaseModel):
    """Trusted planner input for one user's question at a known current time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    now: datetime
    default_subject: str = Actor.OWNER
    default_subject_id: str = ""

    @field_validator("query", "default_subject_id", mode="before")
    @classmethod
    def _normalize_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("query")
    @classmethod
    def _require_query(cls, value: str) -> str:
        if not value:
            raise ValueError("query is required")
        return value

    @field_validator("default_subject", mode="before")
    @classmethod
    def _normalize_subject(cls, value: Any) -> str:
        return Actor.normalize(value)

    @field_validator("now")
    @classmethod
    def _normalize_now(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("query now must include a timezone")
        return value.astimezone(UTC)


@runtime_checkable
class PersonalMemoryQueryPlanner(Protocol):
    """Turn a natural-language question into a scope-free structured draft."""

    name: str
    version: str

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraft: ...


REFERENCE_PERSONAL_MEMORY_QUERY_INSTRUCTIONS = """\
Plan retrieval over already-extracted personal memories. Return one structured query
draft and never choose read scopes, Store operations, memory IDs, lifecycle actions, or
an answer. Use current for facts true now, planned only for unfulfilled future plans,
history for prior facts, list for episode enumeration, count for episode counts, and
as_of only with an explicit point in time. Prefer stable topic keys such as
residence.primary when the question clearly names one slot. Use episode memory type for
travel/experience enumeration and counting. Keep search_text empty when structural
type/topic filters should retrieve the complete set. Do not infer that a plan happened.
Use the supplied current time to resolve relative expressions. Prefer a conservative
draft and explain ambiguity rather than broadening the subject or time range.
"""


class ReferencePersonalMemoryQueryPlanner:
    """Schema-constrained query planner using a host-owned model provider."""

    name = "doppel.reference-personal-memory-query-planner"
    version = "2"

    def __init__(self, model: StructuredOutputModel) -> None:
        self.model = model
        _require_identity(model, "structured output model")
        self.version = _model_bound_version(self.version, model)

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraft:
        bound = PersonalMemoryQueryRequest.model_validate(request)
        raw = await self.model.generate(
            StructuredGenerationRequest(
                instructions=REFERENCE_PERSONAL_MEMORY_QUERY_INSTRUCTIONS,
                input=bound.model_dump(mode="json"),
                output_schema=PersonalMemoryQueryDraft.model_json_schema(),
            )
        )
        if isinstance(raw, BaseModel):
            raw = raw.model_dump(warnings=False)
        return PersonalMemoryQueryDraft.model_validate(raw)


class DeterministicPersonalMemoryQueryPlanner:
    """Transparent Chinese baseline for common owner-memory questions."""

    name = "doppel.deterministic-personal-memory-query-planner"
    version = "1"

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraft:
        bound = PersonalMemoryQueryRequest.model_validate(request)
        query = unicodedata.normalize("NFKC", bound.query).strip()
        intent = _detect_intent(query)
        memory_types: list[str] = []
        topic_keys: list[str] = []
        temporal_statuses: list[str] = []
        search_text = _search_text(query)

        if _contains_any(query, ("住", "居住", "住所", "住址", "家在哪")):
            memory_types = [PersonalMemoryType.STATE]
            topic_keys = ["residence.primary"]
            search_text = ""
        elif _contains_any(query, ("旅行", "旅游", "去过", "游玩", "出差", "行程")):
            memory_types = [PersonalMemoryType.EPISODE]
            if intent in {
                PersonalMemoryQueryIntent.COUNT,
                PersonalMemoryQueryIntent.LIST,
            }:
                search_text = ""
        elif re.search(r"(?:最)?喜欢.*(?:颜色|色)", query):
            memory_types = [PersonalMemoryType.PREFERENCE]
            topic_keys = ["preference.favorite-color"]
            search_text = ""

        if intent == PersonalMemoryQueryIntent.CURRENT:
            temporal_statuses = [
                MemoryTemporalStatus.CURRENT,
                MemoryTemporalStatus.TIMELESS,
            ]
        elif intent == PersonalMemoryQueryIntent.PLANNED:
            temporal_statuses = [MemoryTemporalStatus.PLANNED]
        elif intent == PersonalMemoryQueryIntent.HISTORY:
            temporal_statuses = [MemoryTemporalStatus.HISTORICAL]

        as_of = _explicit_as_of(query)
        if as_of is not None:
            intent = PersonalMemoryQueryIntent.AS_OF
            temporal_statuses = []

        return PersonalMemoryQueryDraft(
            intent=intent,
            search_text=search_text,
            memory_types=memory_types,
            topic_keys=topic_keys,
            temporal_statuses=temporal_statuses,
            subject=bound.default_subject,
            subject_id=bound.default_subject_id,
            as_of=as_of,
            explanation="deterministic Chinese intent and topic rules",
        )


class PersonalMemoryQueryConfig(BaseModel):
    """Read bounds and ranking controls for one query."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page_size: int = Field(default=200, ge=1, le=2_000)
    max_records_per_scope: int = Field(default=2_000, ge=1, le=50_000)
    limit: int = Field(default=20, ge=1, le=1_000)
    minimum_planner_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    minimum_lexical_score: float = Field(default=0.25, ge=0.0, le=1.0)
    semantic_candidate_limit: int = Field(default=100, ge=1, le=10_000)
    lexical_weight: float = Field(default=1.0, ge=0.0, le=10.0)
    semantic_weight: float = Field(default=1.0, ge=0.0, le=10.0)
    semantic_fallback_to_lexical: bool = True

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.model_dump(mode="json"))


class PersonalMemoryQueryPlan(BaseModel):
    """Trusted, exact-scope execution plan derived from a planner draft."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    plan_id: str
    query: str
    now: datetime
    scopes: list[MemoryScope] = Field(min_length=1)
    intent: QueryIntent
    search_text: str = ""
    memory_types: list[str] = Field(default_factory=list)
    topic_keys: list[str] = Field(default_factory=list)
    temporal_statuses: list[str] = Field(default_factory=list)
    subject: str
    subject_id: str
    as_of: datetime | None = None
    time_from: datetime | None = None
    time_to: datetime | None = None
    planner: str
    planner_version: str
    planner_confidence: float = Field(ge=0.0, le=1.0)
    explanation: str = ""
    config_fingerprint: str


class PersonalMemoryQueryHit(BaseModel):
    """One evidence-bearing record with transparent ranking features."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record: MemoryRecord
    score: float = Field(ge=0.0)
    lexical_score: float = Field(ge=0.0, le=1.0)
    semantic_score: float = Field(ge=0.0, le=1.0)
    effective_at: datetime
    reasons: list[str] = Field(default_factory=list)


class PersonalMemoryConflictHit(BaseModel):
    """One persisted open conflict relevant to the authorized query."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record: MemoryRecord
    source_memory_ids: list[str] = Field(min_length=2)
    matched_source_memory_ids: list[str] = Field(default_factory=list)
    topic_key: str
    reason: str

    @field_validator("source_memory_ids", "matched_source_memory_ids")
    @classmethod
    def _normalize_source_ids(cls, value: list[str]) -> list[str]:
        normalized = [str(item or "").strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("conflict source memory IDs must not be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("conflict source memory IDs must be unique")
        return normalized

    @model_validator(mode="after")
    def _matched_sources_are_bound(self) -> PersonalMemoryConflictHit:
        unknown = set(self.matched_source_memory_ids).difference(self.source_memory_ids)
        if unknown:
            raise ValueError("matched conflict sources must be source memory IDs")
        return self


class PersonalMemoryCountResult(BaseModel):
    """Conservative episode aggregation; indeterminate is a first-class result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["not_requested", "exact", "indeterminate"]
    value: int | None = Field(default=None, ge=0)
    observed_records: int = Field(default=0, ge=0)
    distinct_event_keys: list[str] = Field(default_factory=list)
    reason: str = ""

    @model_validator(mode="after")
    def _validate_value(self) -> PersonalMemoryCountResult:
        if self.status == PersonalMemoryCountStatus.EXACT and self.value is None:
            raise ValueError("exact count requires a value")
        if self.status != PersonalMemoryCountStatus.EXACT and self.value is not None:
            raise ValueError("only an exact count may expose a value")
        return self


class PersonalMemoryQueryResult(BaseModel):
    """Auditable evidence set and optional aggregation, never a generated answer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan: PersonalMemoryQueryPlan
    hits: list[PersonalMemoryQueryHit] = Field(default_factory=list)
    conflicts: list[PersonalMemoryConflictHit] = Field(default_factory=list)
    matched_record_count: int = Field(default=0, ge=0)
    scanned_record_count: int = Field(default=0, ge=0)
    scanned_conflict_count: int = Field(default=0, ge=0)
    count: PersonalMemoryCountResult
    ambiguous: bool = False
    warnings: list[str] = Field(default_factory=list)
    complete: bool = True


class PersonalMemoryQueryPlanningError(ValueError):
    """A scope-free planner draft could not be bound to trusted query authority."""


class PersonalMemoryQueryReadLimitError(RuntimeError):
    """A complete exact-scope query exceeded the configured read bound."""


class PersonalMemoryQueryEngine:
    """Plan and execute a full-snapshot personal-memory query."""

    def __init__(
        self,
        store: MemoryStore,
        config: PersonalMemoryQueryConfig | None = None,
        *,
        semantic_index: SemanticIndex | None = None,
    ) -> None:
        if not store.capabilities.pagination:
            raise NotImplementedError(
                "personal-memory queries require a Store with stable pagination"
            )
        self._store = store
        self.config = config or PersonalMemoryQueryConfig()
        self._semantic_index = semantic_index

    async def plan(
        self,
        planner: PersonalMemoryQueryPlanner,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        now: datetime,
        default_subject: str = Actor.OWNER,
        default_subject_id: str = "",
        allowed_subject_ids: Sequence[str] = (),
    ) -> PersonalMemoryQueryPlan:
        _require_identity(planner, "personal-memory query planner")
        bound_scopes = _bind_scopes(scopes)
        owner_id = bound_scopes[0].user_id
        request = PersonalMemoryQueryRequest(
            query=query,
            now=now,
            default_subject=default_subject,
            default_subject_id=default_subject_id or owner_id,
        )
        draft = PersonalMemoryQueryDraft.model_validate(await planner.plan(request))
        if draft.confidence < self.config.minimum_planner_confidence:
            raise PersonalMemoryQueryPlanningError(
                f"planner confidence {draft.confidence} is below minimum "
                f"{self.config.minimum_planner_confidence}"
            )
        subject_id = _bind_subject_id(
            draft,
            bound_scopes,
            allowed_subject_ids=allowed_subject_ids,
        )
        plan = PersonalMemoryQueryPlan(
            plan_id="",
            query=request.query,
            now=request.now,
            scopes=bound_scopes,
            intent=draft.intent,
            search_text=draft.search_text,
            memory_types=draft.memory_types,
            topic_keys=draft.topic_keys,
            temporal_statuses=draft.temporal_statuses,
            subject=draft.subject,
            subject_id=subject_id,
            as_of=draft.as_of,
            time_from=draft.time_from,
            time_to=draft.time_to,
            planner=planner.name,
            planner_version=planner.version,
            planner_confidence=draft.confidence,
            explanation=draft.explanation,
            config_fingerprint=self.config.fingerprint,
        )
        return plan.model_copy(
            update={"plan_id": "pmq_" + _fingerprint(_plan_payload(plan))}
        )

    async def execute(self, plan: PersonalMemoryQueryPlan) -> PersonalMemoryQueryResult:
        bound = PersonalMemoryQueryPlan.model_validate(plan)
        self._validate_plan(bound)
        records: list[MemoryRecord] = []
        conflict_records: list[MemoryRecord] = []
        for scope in bound.scopes:
            records.extend(await self._read_scope(scope))
            conflict_records.extend(await self._read_conflicts(scope))
        semantic_scores, semantic_warnings = await self._semantic_scores(bound, records)
        matched: list[tuple[MemoryRecord, float, float, datetime, list[str]]] = []
        warnings = list(semantic_warnings)
        if (
            bound.as_of is not None
            and bound.as_of > bound.now
            and MemoryTemporalStatus.PLANNED not in bound.temporal_statuses
        ):
            warnings.append(
                "future as_of returns present evidence only; future actual state is unknown"
            )
        for record in records:
            structural = _structural_match(record, bound)
            if structural is None:
                continue
            effective_at, reasons = structural
            lexical_score = _lexical_score(bound.search_text, record)
            semantic_score = semantic_scores.get(record.memory_id, 0.0)
            if (
                bound.search_text
                and lexical_score < self.config.minimum_lexical_score
                and semantic_score <= 0.0
            ):
                continue
            if lexical_score >= self.config.minimum_lexical_score:
                reasons.append("lexical_match")
            if semantic_score > 0.0:
                reasons.append("semantic_match")
            matched.append(
                (record, lexical_score, semantic_score, effective_at, reasons)
            )

        conflicts = _relevant_conflicts(bound, records, matched, conflict_records)
        ambiguous, ambiguity_warnings = _detect_ambiguity(bound, matched)
        ambiguous = ambiguous or bool(conflicts)
        warnings.extend(ambiguity_warnings)
        warnings.extend(
            f"open conflict in topic {item.topic_key}: {item.reason}"
            for item in conflicts
        )
        matched.sort(
            key=lambda item: (
                _rank_score(self.config, bound, item[0], item[1], item[2], item[3]),
                item[3],
                item[0].memory_id,
            ),
            reverse=True,
        )
        hits = [
            PersonalMemoryQueryHit(
                record=record,
                score=_rank_score(
                    self.config,
                    bound,
                    record,
                    lexical_score,
                    semantic_score,
                    effective_at,
                ),
                lexical_score=lexical_score,
                semantic_score=semantic_score,
                effective_at=effective_at,
                reasons=reasons,
            )
            for record, lexical_score, semantic_score, effective_at, reasons in matched[
                : self.config.limit
            ]
        ]
        count = _count_result(bound, [item[0] for item in matched])
        if count.status == PersonalMemoryCountStatus.INDETERMINATE:
            warnings.append(count.reason)
        return PersonalMemoryQueryResult(
            plan=bound,
            hits=hits,
            conflicts=conflicts,
            matched_record_count=len(matched),
            scanned_record_count=len(records),
            scanned_conflict_count=len(conflict_records),
            count=count,
            ambiguous=ambiguous,
            warnings=list(dict.fromkeys(warnings)),
        )

    async def query(
        self,
        planner: PersonalMemoryQueryPlanner,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        now: datetime,
        default_subject: str = Actor.OWNER,
        default_subject_id: str = "",
        allowed_subject_ids: Sequence[str] = (),
    ) -> PersonalMemoryQueryResult:
        plan = await self.plan(
            planner,
            query,
            scopes,
            now=now,
            default_subject=default_subject,
            default_subject_id=default_subject_id,
            allowed_subject_ids=allowed_subject_ids,
        )
        return await self.execute(plan)

    async def _read_scope(self, scope: MemoryScope) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        cursor = ""
        while True:
            remaining = self.config.max_records_per_scope - len(records)
            if remaining <= 0:
                raise PersonalMemoryQueryReadLimitError(
                    f"active personal memories in {scope.describe()} exceed "
                    f"max_records_per_scope {self.config.max_records_per_scope}"
                )
            page = await self._store.scan(
                scope,
                filters=MemoryFilter(
                    tags={"personal-memory"}, states=set(ACTIVE_MEMORY_STATES)
                ),
                cursor=cursor,
                limit=min(self.config.page_size, remaining),
            )
            records.extend(page.records)
            if not page.has_more:
                return records
            cursor = page.next_cursor
            if len(records) >= self.config.max_records_per_scope:
                raise PersonalMemoryQueryReadLimitError(
                    f"active personal memories in {scope.describe()} exceed "
                    f"max_records_per_scope {self.config.max_records_per_scope}"
                )

    async def _read_conflicts(self, scope: MemoryScope) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        cursor = ""
        while True:
            remaining = self.config.max_records_per_scope - len(records)
            if remaining <= 0:
                raise PersonalMemoryQueryReadLimitError(
                    f"active conflict markers in {scope.describe()} exceed "
                    f"max_records_per_scope {self.config.max_records_per_scope}"
                )
            page = await self._store.scan(
                scope,
                filters=MemoryFilter(
                    tags={"memory-conflict"}, states=set(ACTIVE_MEMORY_STATES)
                ),
                cursor=cursor,
                limit=min(self.config.page_size, remaining),
            )
            records.extend(page.records)
            if not page.has_more:
                return records
            cursor = page.next_cursor
            if len(records) >= self.config.max_records_per_scope:
                raise PersonalMemoryQueryReadLimitError(
                    f"active conflict markers in {scope.describe()} exceed "
                    f"max_records_per_scope {self.config.max_records_per_scope}"
                )

    def _validate_plan(self, plan: PersonalMemoryQueryPlan) -> None:
        if plan.schema_version != 1:
            raise PersonalMemoryQueryPlanningError("unsupported query plan schema")
        if plan.config_fingerprint != self.config.fingerprint:
            raise PersonalMemoryQueryPlanningError(
                "query plan config does not match this engine"
            )
        _bind_scopes(plan.scopes)
        expected = "pmq_" + _fingerprint(_plan_payload(plan))
        if plan.plan_id != expected:
            raise PersonalMemoryQueryPlanningError(
                "query plan content does not match its plan_id"
            )

    async def _semantic_scores(
        self,
        plan: PersonalMemoryQueryPlan,
        records: Sequence[MemoryRecord],
    ) -> tuple[dict[str, float], list[str]]:
        if self._semantic_index is None or not plan.search_text:
            return {}, []
        try:
            candidates = await self._semantic_index.search(
                plan.search_text,
                plan.scopes,
                filters=MemoryFilter(
                    tags={"personal-memory"}, states=set(ACTIVE_MEMORY_STATES)
                ),
                limit=self.config.semantic_candidate_limit,
            )
        except Exception as exc:
            if not self.config.semantic_fallback_to_lexical:
                raise
            return {}, [
                f"semantic index unavailable; used lexical fallback: {type(exc).__name__}"
            ]
        allowed_scopes = {scope.scope_key for scope in plan.scopes}
        known_ids = {record.memory_id for record in records}
        scores: dict[str, float] = {}
        for candidate in candidates:
            if (
                candidate.scope is None
                or candidate.scope.scope_key not in allowed_scopes
                or candidate.memory_id not in known_ids
            ):
                continue
            score = min(max(float(candidate.similarity), 0.0), 1.0)
            scores[candidate.memory_id] = max(
                scores.get(candidate.memory_id, 0.0), score
            )
        return scores, []


def _bind_scopes(scopes: Sequence[MemoryScope]) -> list[MemoryScope]:
    if not scopes:
        raise MemoryIsolationError("personal-memory query requires explicit scopes")
    unique: dict[str, MemoryScope] = {}
    for scope in scopes:
        bound = MemoryScope.model_validate(scope)
        unique.setdefault(bound.scope_key, bound)
    user_ids = {scope.user_id for scope in unique.values()}
    if len(user_ids) != 1:
        raise MemoryIsolationError(
            "one personal-memory query cannot cross user_id boundaries"
        )
    return list(unique.values())


def _bind_subject_id(
    draft: PersonalMemoryQueryDraft,
    scopes: Sequence[MemoryScope],
    *,
    allowed_subject_ids: Sequence[str],
) -> str:
    owner_id = scopes[0].user_id
    agent_ids = {scope.agent_id for scope in scopes if scope.agent_id}
    requested = draft.subject_id.strip()
    if draft.subject == Actor.OWNER:
        if requested and requested != owner_id:
            raise PersonalMemoryQueryPlanningError(
                "owner subject_id must match the exact-scope user_id"
            )
        return owner_id
    if draft.subject == Actor.AGENT:
        if len(agent_ids) != 1:
            raise PersonalMemoryQueryPlanningError(
                "agent query requires one shared agent_id"
            )
        agent_id = next(iter(agent_ids))
        if requested and requested != agent_id:
            raise PersonalMemoryQueryPlanningError(
                "agent subject_id must match the exact-scope agent_id"
            )
        return agent_id
    trusted = {str(item or "").strip() for item in allowed_subject_ids}
    trusted.discard("")
    if not requested or requested not in trusted:
        raise PersonalMemoryQueryPlanningError(
            "contact/custom subject_id requires explicit host authorization"
        )
    return requested


def _structural_match(
    record: MemoryRecord, plan: PersonalMemoryQueryPlan
) -> tuple[datetime, list[str]] | None:
    if _metadata_text(record, "subject") != plan.subject:
        return None
    if _metadata_text(record, "subject_id") != plan.subject_id.lower():
        return None
    memory_type = _metadata_text(record, "personal_memory_type")
    if plan.memory_types and memory_type not in plan.memory_types:
        return None
    topic_key = _metadata_text(record, "topic_key")
    if plan.topic_keys and topic_key not in plan.topic_keys:
        return None
    temporal_status = _metadata_text(record, "temporal_status")
    if plan.temporal_statuses and temporal_status not in plan.temporal_statuses:
        return None
    if (
        plan.as_of is not None
        and temporal_status == MemoryTemporalStatus.PLANNED
        and MemoryTemporalStatus.PLANNED not in plan.temporal_statuses
    ):
        return None

    valid_from = _metadata_time(record, "valid_from")
    valid_to = _metadata_time(record, "valid_to")
    effective_at = valid_from or record.created_at
    if plan.intent == PersonalMemoryQueryIntent.CURRENT:
        if valid_from is not None and valid_from > plan.now:
            return None
        if valid_to is not None and valid_to < plan.now:
            return None
    if plan.as_of is not None:
        if valid_from is not None and valid_from > plan.as_of:
            return None
        if valid_to is not None and valid_to < plan.as_of:
            return None
        if (
            valid_from is None
            and valid_to is None
            and temporal_status
            not in {
                MemoryTemporalStatus.TIMELESS,
                MemoryTemporalStatus.CURRENT,
            }
        ):
            return None
    if plan.time_from is not None and effective_at < plan.time_from:
        return None
    if plan.time_to is not None and effective_at > plan.time_to:
        return None

    reasons = ["exact_scope", "active_personal_memory", "subject"]
    if plan.memory_types:
        reasons.append("memory_type")
    if plan.topic_keys:
        reasons.append("topic_key")
    if plan.temporal_statuses:
        reasons.append("temporal_status")
    if plan.as_of is not None:
        reasons.append("valid_at_as_of")
    elif plan.intent == PersonalMemoryQueryIntent.CURRENT and (
        valid_from is not None or valid_to is not None
    ):
        reasons.append("valid_at_now")
    return effective_at, reasons


def _rank_score(
    config: PersonalMemoryQueryConfig,
    plan: PersonalMemoryQueryPlan,
    record: MemoryRecord,
    lexical_score: float,
    semantic_score: float,
    effective_at: datetime,
) -> float:
    structural = 1.0
    structural += 0.3 if plan.topic_keys else 0.0
    structural += 0.2 if plan.memory_types else 0.0
    structural += 0.2 if plan.temporal_statuses or plan.as_of else 0.0
    structural += record.importance * 0.1
    timestamp = max(0.0, effective_at.timestamp())
    recency_tiebreaker = min(timestamp / 10_000_000_000, 0.2)
    return round(
        structural
        + config.lexical_weight * lexical_score
        + config.semantic_weight * semantic_score
        + recency_tiebreaker,
        6,
    )


def _relevant_conflicts(
    plan: PersonalMemoryQueryPlan,
    active_records: Sequence[MemoryRecord],
    matched: Sequence[tuple[MemoryRecord, float, float, datetime, list[str]]],
    conflict_records: Sequence[MemoryRecord],
) -> list[PersonalMemoryConflictHit]:
    active_ids = {
        (record.scope.scope_key, record.memory_id) for record in active_records
    }
    matched_ids = {(record.scope.scope_key, record.memory_id) for record, *_ in matched}
    results: list[PersonalMemoryConflictHit] = []
    for record in conflict_records:
        conflict = record.metadata.get("conflict", {})
        if not isinstance(conflict, dict) or conflict.get("status") != "open":
            continue
        if str(conflict.get("subject", "")).strip().lower() != plan.subject:
            continue
        if (
            str(conflict.get("subject_id", "")).strip().lower()
            != plan.subject_id.lower()
        ):
            continue
        memory_type = str(conflict.get("personal_memory_type", "")).strip().lower()
        topic_key = str(conflict.get("topic_key", "")).strip().lower()
        temporal_status = str(conflict.get("temporal_status", "")).strip().lower()
        if plan.memory_types and memory_type not in plan.memory_types:
            continue
        if plan.topic_keys and topic_key not in plan.topic_keys:
            continue
        if plan.temporal_statuses and temporal_status not in plan.temporal_statuses:
            continue
        raw_sources = conflict.get("source_memories", [])
        if not isinstance(raw_sources, list):
            continue
        source_ids = [
            str(item.get("memory_id", "") or "").strip()
            for item in raw_sources
            if isinstance(item, dict) and item.get("memory_id")
        ]
        live_sources = [
            memory_id
            for memory_id in source_ids
            if (record.scope.scope_key, memory_id) in active_ids
        ]
        matched_sources = [
            memory_id
            for memory_id in live_sources
            if (record.scope.scope_key, memory_id) in matched_ids
        ]
        if len(live_sources) < 2 or not matched_sources:
            continue
        results.append(
            PersonalMemoryConflictHit(
                record=record,
                source_memory_ids=source_ids,
                matched_source_memory_ids=matched_sources,
                topic_key=topic_key,
                reason=str(conflict.get("reason", "") or "").strip(),
            )
        )
    return results


def _detect_ambiguity(
    plan: PersonalMemoryQueryPlan,
    matched: Sequence[tuple[MemoryRecord, float, float, datetime, list[str]]],
) -> tuple[bool, list[str]]:
    if plan.intent not in {
        PersonalMemoryQueryIntent.CURRENT,
        PersonalMemoryQueryIntent.AS_OF,
    }:
        return False, []
    groups: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    for record, _, _, _, _ in matched:
        key = (
            record.scope.scope_key,
            _metadata_text(record, "subject_id"),
            _metadata_text(record, "personal_memory_type"),
            _metadata_text(record, "topic_key"),
        )
        groups[key].add(_normalize_text(record.content))
    warnings = [
        f"unresolved current/as-of conflict in topic {key[3] or '<unkeyed>'}"
        for key, contents in groups.items()
        if len(contents) > 1
    ]
    return bool(warnings), warnings


def _count_result(
    plan: PersonalMemoryQueryPlan, records: Sequence[MemoryRecord]
) -> PersonalMemoryCountResult:
    if plan.intent != PersonalMemoryQueryIntent.COUNT:
        return PersonalMemoryCountResult(status=PersonalMemoryCountStatus.NOT_REQUESTED)
    if not records:
        return PersonalMemoryCountResult(
            status=PersonalMemoryCountStatus.EXACT,
            value=0,
            reason="complete exact-scope scan found no matching episodes",
        )
    if any(
        _metadata_text(record, "personal_memory_type") != PersonalMemoryType.EPISODE
        for record in records
    ):
        return PersonalMemoryCountResult(
            status=PersonalMemoryCountStatus.INDETERMINATE,
            observed_records=len(records),
            reason="exact count requires episode-only results",
        )
    event_keys = [_metadata_text(record, "event_key") for record in records]
    if any(not key for key in event_keys):
        return PersonalMemoryCountResult(
            status=PersonalMemoryCountStatus.INDETERMINATE,
            observed_records=len(records),
            distinct_event_keys=sorted(set(event_keys).difference({""})),
            reason="exact episode count requires a stable event_key on every match",
        )
    distinct = sorted(set(event_keys))
    return PersonalMemoryCountResult(
        status=PersonalMemoryCountStatus.EXACT,
        value=len(distinct),
        observed_records=len(records),
        distinct_event_keys=distinct,
        reason="counted distinct stable event_key values over a complete scope scan",
    )


def _lexical_score(query: str, record: MemoryRecord) -> float:
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return 0.0
    document = _normalize_text(
        " ".join(
            (
                record.content,
                _metadata_text(record, "topic_key"),
                _metadata_text(record, "personal_memory_type"),
            )
        )
    )
    if not document:
        return 0.0
    query_terms = _character_ngrams(normalized_query)
    document_terms = _character_ngrams(document)
    if not query_terms or not document_terms:
        return 0.0
    overlap = sum(
        min(query_terms[term], document_terms.get(term, 0)) for term in query_terms
    )
    denominator = math.sqrt(sum(query_terms.values())) * math.sqrt(
        sum(document_terms.values())
    )
    score = overlap / denominator if denominator else 0.0
    if normalized_query in document:
        score = min(1.0, score + 0.25)
    return round(min(max(score, 0.0), 1.0), 6)


def _character_ngrams(text: str) -> dict[str, int]:
    compact = re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", text)
    counts: dict[str, int] = defaultdict(int)
    for size in (1, 2):
        for index in range(max(0, len(compact) - size + 1)):
            counts[compact[index : index + size]] += 1
    return dict(counts)


def _detect_intent(query: str) -> QueryIntent:
    if re.search(r"几次|多少次|次数|一共.*(?:旅行|旅游|去过)", query):
        return PersonalMemoryQueryIntent.COUNT
    if _contains_any(query, ("哪些", "列出", "去过哪", "都去过", "经历过")):
        return PersonalMemoryQueryIntent.LIST
    if _contains_any(query, ("计划", "打算", "准备", "将要", "将来")):
        return PersonalMemoryQueryIntent.PLANNED
    if _contains_any(query, ("以前", "过去", "曾经", "历史", "去年", "之前")):
        return PersonalMemoryQueryIntent.HISTORY
    if _contains_any(query, ("现在", "目前", "如今", "当前")):
        return PersonalMemoryQueryIntent.CURRENT
    return PersonalMemoryQueryIntent.LOOKUP


def _search_text(query: str) -> str:
    cleaned = unicodedata.normalize("NFKC", query).lower()
    for phrase in (
        "我",
        "用户",
        "现在",
        "目前",
        "如今",
        "以前",
        "过去",
        "曾经",
        "计划",
        "打算",
        "一共",
        "多少次",
        "几次",
        "哪些",
        "哪里",
        "哪儿",
        "是什么",
        "的记忆",
        "相关记忆",
        "关于",
        "告诉",
        "回忆",
        "吗",
        "呢",
    ):
        cleaned = cleaned.replace(phrase, "")
    return re.sub(r"[\s，。！？；：、,.!?;:]+", "", cleaned).strip()


def _explicit_as_of(query: str) -> datetime | None:
    iso_match = re.search(
        r"(?P<year>20\d{2})[-/年](?P<month>\d{1,2})[-/月](?P<day>\d{1,2})日?",
        query,
    )
    if iso_match is None:
        return None
    try:
        return datetime(
            int(iso_match.group("year")),
            int(iso_match.group("month")),
            int(iso_match.group("day")),
            12,
            tzinfo=UTC,
        )
    except ValueError:
        return None


def _metadata_text(record: MemoryRecord, key: str) -> str:
    return str(record.metadata.get(key, "") or "").strip().lower()


def _metadata_time(record: MemoryRecord, key: str) -> datetime | None:
    raw = record.metadata.get(key)
    if isinstance(raw, datetime):
        return raw.astimezone(UTC) if raw.tzinfo is not None else None
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else None


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).lower().strip()
    normalized = normalized.replace("旅游", "旅行").replace("之旅", "旅行")
    return re.sub(r"[\s，。！？；：、,.!?;:]+", "", normalized)


def _contains_any(value: str, needles: Sequence[str]) -> bool:
    return any(needle in value for needle in needles)


def _plan_payload(plan: PersonalMemoryQueryPlan) -> dict[str, Any]:
    payload = plan.model_dump(mode="json")
    payload.pop("plan_id", None)
    return payload


def _fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_identity(value: Any, label: str) -> None:
    for attribute in ("name", "version"):
        if not str(getattr(value, attribute, "") or "").strip():
            raise ValueError(f"{label} requires non-empty {attribute}")


def _model_bound_version(base_version: str, model: StructuredOutputModel) -> str:
    return f"{base_version}.{_fingerprint({'name': model.name, 'version': model.version})[:16]}"
