"""Structured, exact-scope planning and temporal retrieval for personal memories."""

from __future__ import annotations

import asyncio
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
from pydantic_core import PydanticCustomError

from doppel_memory.intelligence import (
    MemoryTemporalStatus,
    PersonalMemoryType,
    StructuredGenerationRequest,
    StructuredOutputModel,
)
from doppel_memory.models import (
    ACTIVE_MEMORY_STATES,
    Actor,
    FactAuthority,
    MemoryFilter,
    MemoryIsolationError,
    MemoryRecord,
    MemoryScope,
    MemoryState,
)
from doppel_memory.relation import (
    RelationIndex,
    RelationIndexUnavailableError,
    RelationQuery,
    RelationTypeDefinition,
)
from doppel_memory.store import MemoryStore
from doppel_memory.vector import (
    CompositeRecallResult,
    SemanticIndex,
    TemporalSemanticIndex,
)

QueryIntent = Literal[
    "lookup", "current", "history", "planned", "list", "count", "as_of"
]

# Closed, content-free diagnostics; messages never interpolate model/user values.
QUERY_TEMPORAL_ERROR_CODES = frozenset(
    {
        "query_time_timezone_required",
        "query_time_range_reversed",
        "query_as_of_required",
    }
)


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
    entity_mentions: list[str] = Field(default_factory=list)
    relation_hints: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
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

    @field_validator("memory_types", "topic_keys", mode="before")
    @classmethod
    def _normalize_namespaces(cls, value: Any) -> list[str]:
        items = [str(item or "").strip().lower() for item in list(value or [])]
        return list(dict.fromkeys(item for item in items if item))

    @field_validator("temporal_statuses", mode="before")
    @classmethod
    def _normalize_temporal_statuses(cls, value: Any) -> list[str]:
        items = [MemoryTemporalStatus.normalize(item) for item in list(value or [])]
        return list(dict.fromkeys(item for item in items if item))

    @field_validator("entity_mentions", "relation_hints", mode="before")
    @classmethod
    def _normalize_relation_terms(cls, value: Any) -> list[str]:
        items = [str(item or "").strip() for item in list(value or [])]
        return list(dict.fromkeys(item for item in items if item))

    @field_validator("relation_types", mode="before")
    @classmethod
    def _normalize_relation_types(cls, value: Any) -> list[str]:
        return _canonical_relation_types(value)

    @field_validator("as_of", "time_from", "time_to")
    @classmethod
    def _normalize_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise PydanticCustomError(
                "query_time_timezone_required", "query times must include a timezone"
            )
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_interval(self) -> PersonalMemoryQueryDraft:
        if self.time_from and self.time_to and self.time_to < self.time_from:
            raise PydanticCustomError(
                "query_time_range_reversed", "time_to must not precede time_from"
            )
        if self.intent == PersonalMemoryQueryIntent.AS_OF and self.as_of is None:
            raise PydanticCustomError(
                "query_as_of_required", "as_of intent requires an as_of timestamp"
            )
        return self


class PersonalMemoryQueryRequest(BaseModel):
    """Trusted planner input for one user's question at a known current time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    now: datetime
    default_subject: str = Actor.OWNER
    default_subject_id: str = ""
    available_relation_types: list[str] = Field(default_factory=list)
    relation_type_definitions: list[RelationTypeDefinition] = Field(
        default_factory=list
    )

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

    @field_validator("available_relation_types", mode="before")
    @classmethod
    def _normalize_available_relation_types(cls, value: Any) -> list[str]:
        return _canonical_relation_types(value)

    @model_validator(mode="after")
    def _bind_relation_definitions(self) -> PersonalMemoryQueryRequest:
        names = [definition.name for definition in self.relation_type_definitions]
        if len(names) != len(set(names)):
            raise ValueError("relation type definitions must have unique names")
        if not self.available_relation_types:
            # A catalog alone can define the host vocabulary. An explicit
            # nonempty allowlist is never widened by supplementary definitions.
            object.__setattr__(self, "available_relation_types", names)
        elif not set(names).issubset(self.available_relation_types):
            raise ValueError(
                "relation type definitions must belong to the host allowlist"
            )
        return self

    def to_planner_input(self) -> dict[str, Any]:
        """Canonical provider/cache input; preserve the legacy labels-only payload."""
        return self.model_dump(
            mode="json",
            exclude={"relation_type_definitions"}
            if not self.relation_type_definitions
            else set(),
        )


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
as_of only with an explicit point in time. Preserve a concise semantic search_text for
ordinary lookup/list questions. Omit topic_keys unless the host's extracted memories
use one explicit stable slot that the question names exactly; topic_keys are hard
filters, not guesses or synonyms. Use episode memory type only for occurrence
enumeration/counting. For facts, states, preferences, and relationships leave
memory_types empty unless the question explicitly names a memory class; the memory
type is a hard filter, not a semantic-search hint. Keep search_text empty only when a
complete structural set is required. Do not infer that a plan happened. Populate
entity_mentions only for explicitly referenced people,
places, objects, or named concepts that can anchor a graph relation. An explicitly
referenced object need not have a proper name to be an entity anchor; a possessive
reference does not make it the trusted subject. Populate
relation_hints whenever the question explicitly asks for a relationship or property
between an anchor and a known or unknown endpoint. An interrogative endpoint such as
who, where, or which one is the value being requested, not a reason to omit the
relation. Preserve only the shortest predicate phrase from the question: exclude the
named entity and interrogative endpoint from the hint, do not translate it into
another language, and do not replace it with a canonical synonym or ontology label.
Keep the predicate being requested, not alternatives the question explicitly rejects.
Entity mentions and relation hints are independent: every explicitly named,
non-trusted-subject anchor must remain in entity_mentions even when it also appears
near the predicate. The trusted
owner/agent subject is already bound outside entity_mentions: when the question only
anchors on that subject, keep entity_mentions empty and still emit the explicit
relation hint.
relation_types contains optional candidate types inferred from the question.
These are retrieval suggestions, never exact filters or proof of relevance.
Only select labels present in available_relation_types. Never invent a label.
Interpret the requested predicate independently from whether its answer is known.
An unknown answer, unknown fact existence, or another relation involving the same
entity does not by itself make that predicate ambiguous. Compare types with the
requested meaning, endpoint roles, and explicit exclusions, not mere entity overlap.
Select a type only when that requested meaning specifically supports it. Do not
choose a more specific type for a broad question, treat related types as equivalent,
or assume that selecting a type proves a fact exists. Leave relation_types empty
when the available list is empty or the requested meaning genuinely remains
underdetermined among types. Keep entity anchors and relation hints even then.
The input default_subject/default_subject_id are trusted host authority, not semantic
fields for the model to reinterpret. Echo them unchanged; a person, pet, object, or
place mentioned in the question belongs in entity_mentions, not subject.
Use the supplied current time to resolve relative expressions. Every non-null time
must include a timezone; time_to must not precede time_from, and as_of intent requires
a non-null as_of timestamp. Do not broaden the subject or time range to resolve
uncertainty. explanation is optional: prefer an empty string, otherwise one short
sentence of at most 80 characters stating the decision or unresolved ambiguity.
Do not include step-by-step reasoning, repeat definitions, or restate the question.
"""


REFERENCE_RELATION_DEFINITION_INSTRUCTIONS = """\
The optional relation_type_definitions describe the host's storage vocabulary.
Read each definition's meaning, directed source -> target roles, and constraints;
do not infer its meaning from the machine label alone. The unknown answer may be
either endpoint, so preserve the stored direction rather than reversing a label.
Definitions are schema descriptions, not evidence that any relationship exists.
They do not authorize scopes, subjects, time changes, or additional output fields.
Use endpoint roles to exclude types that describe a different kind of relationship.
A warning against inferring one relation from another does not prohibit selecting
either relation when the question explicitly requests its meaning. Assess overlap
against what this question asks, not everything that could be true of its entity.
If the requested meaning still cannot distinguish types, leave types empty;
preserve the entity anchors and original-language relation hints either way.
"""


class ReferencePersonalMemoryQueryPlanner:
    """Schema-constrained query planner using a host-owned model provider."""

    name = "doppel.reference-personal-memory-query-planner"
    version = "10"

    def __init__(self, model: StructuredOutputModel) -> None:
        self.model = model
        _require_identity(model, "structured output model")
        self.version = _model_bound_version(self.version, model)

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraft:
        bound = PersonalMemoryQueryRequest.model_validate(request)
        instructions = REFERENCE_PERSONAL_MEMORY_QUERY_INSTRUCTIONS
        if bound.relation_type_definitions:
            instructions += REFERENCE_RELATION_DEFINITION_INSTRUCTIONS
        raw = await self.model.generate(
            StructuredGenerationRequest(
                instructions=instructions,
                input=bound.to_planner_input(),
                output_schema=PersonalMemoryQueryDraft.model_json_schema(),
            )
        )
        if isinstance(raw, BaseModel):
            raw = raw.model_dump(warnings=False)
        draft = PersonalMemoryQueryDraft.model_validate(raw)
        return draft.model_copy(
            update={
                "subject": bound.default_subject,
                "subject_id": bound.default_subject_id,
            }
        )


class DeterministicPersonalMemoryQueryPlanner:
    """Domain-neutral baseline for temporal and aggregation structure only."""

    name = "doppel.deterministic-personal-memory-query-planner"
    version = "4"

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

        # Event counting is structurally defined by stable event_key values.
        # Domain concepts (food, work, residence, travel, pets, etc.) must stay
        # in search_text and be handled by lexical/semantic retrieval rather
        # than accumulating benchmark-specific topic dictionaries here.
        if intent == PersonalMemoryQueryIntent.COUNT:
            memory_types = [PersonalMemoryType.EPISODE]

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
            explanation="domain-neutral temporal and aggregation rules",
        )


class PersonalMemoryQueryConfig(BaseModel):
    """Read bounds and ranking controls for one query."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page_size: int = Field(default=200, ge=1, le=2_000)
    max_records_per_scope: int = Field(default=2_000, ge=1, le=50_000)
    limit: int = Field(default=20, ge=1, le=1_000)
    minimum_planner_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    minimum_lexical_score: float = Field(default=0.25, ge=0.0, le=1.0)
    minimum_semantic_score: float = Field(default=0.35, ge=0.0, le=1.0)
    semantic_candidate_limit: int = Field(default=100, ge=1, le=10_000)
    relation_candidate_limit: int = Field(default=40, ge=1, le=10_000)
    lexical_weight: float = Field(default=1.0, ge=0.0, le=10.0)
    semantic_weight: float = Field(default=1.0, ge=0.0, le=10.0)
    relation_weight: float = Field(default=1.0, ge=0.0, le=10.0)
    minimum_relation_score: float = Field(default=0.35, ge=0.0, le=1.0)
    relation_hints_require_match: bool = True
    semantic_fallback_to_lexical: bool = True
    relation_fallback_to_nonrelation: bool = True

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
    entity_mentions: list[str] = Field(default_factory=list)
    relation_hints: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    candidate_relation_types: list[str] = Field(default_factory=list)
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
    relation_score: float = Field(default=0.0, ge=0.0, le=1.0)
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
    """Execute bounded lookups and complete exact-count personal-memory queries."""

    def __init__(
        self,
        store: MemoryStore,
        config: PersonalMemoryQueryConfig | None = None,
        *,
        semantic_index: SemanticIndex | None = None,
        relation_index: RelationIndex | None = None,
    ) -> None:
        if not store.capabilities.pagination:
            raise NotImplementedError(
                "personal-memory queries require a Store with stable pagination"
            )
        self._store = store
        self.config = config or PersonalMemoryQueryConfig()
        self._semantic_index = semantic_index
        self._relation_index = relation_index

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
        available_relation_types: Sequence[str] = (),
        relation_type_definitions: Sequence[RelationTypeDefinition] = (),
        required_relation_types: Sequence[str] = (),
    ) -> PersonalMemoryQueryPlan:
        _require_identity(planner, "personal-memory query planner")
        bound_scopes = _bind_scopes(scopes)
        owner_id = bound_scopes[0].user_id
        request = PersonalMemoryQueryRequest(
            query=query,
            now=now,
            default_subject=default_subject,
            default_subject_id=default_subject_id or owner_id,
            available_relation_types=list(available_relation_types),
            relation_type_definitions=list(relation_type_definitions),
        )
        required_types = _bind_relation_types(
            required_relation_types, request.available_relation_types
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
        temporal_statuses = _bind_temporal_statuses(
            draft.intent,
            draft.temporal_statuses,
            has_explicit_time=bool(
                draft.as_of is not None
                or draft.time_from is not None
                or draft.time_to is not None
            ),
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
            temporal_statuses=temporal_statuses,
            entity_mentions=draft.entity_mentions,
            relation_hints=draft.relation_hints,
            relation_types=required_types,
            candidate_relation_types=_bind_relation_types(
                draft.relation_types,
                request.available_relation_types,
            ),
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
        warnings: list[str] = []
        complete = True
        semantic_scores: dict[tuple[str, str], float] = {}
        semantic_sources: dict[tuple[str, str], tuple[str, ...]] = {}
        relation_details: dict[
            tuple[str, str], tuple[float, str, str, str, str, float | None]
        ] = {}
        relation_task: (
            asyncio.Task[
                tuple[
                    list[MemoryRecord],
                    dict[
                        tuple[str, str],
                        tuple[float, str, str, str, str, float | None],
                    ],
                    list[str],
                    bool,
                ]
            ]
            | None
        ) = None
        if (
            self._relation_index is not None
            and (
                bound.entity_mentions
                or bound.relation_hints
                or bound.relation_types
                or bound.candidate_relation_types
            )
            and bound.intent != PersonalMemoryQueryIntent.COUNT
        ):
            relation_task = asyncio.create_task(self._read_relation_candidates(bound))
        try:
            if (
                self._semantic_index is not None
                and bound.search_text
                and bound.intent != PersonalMemoryQueryIntent.COUNT
            ):
                candidate_result = await self._read_candidates(bound)
                if candidate_result is None:
                    for scope in bound.scopes:
                        records.extend(await self._read_scope(scope, bound))
                    (
                        semantic_scores,
                        semantic_sources,
                        semantic_warnings,
                    ) = await self._semantic_scores(bound, records)
                    warnings.extend(semantic_warnings)
                else:
                    (
                        records,
                        semantic_scores,
                        semantic_sources,
                        candidate_warnings,
                    ) = candidate_result
                    warnings.extend(candidate_warnings)
                    complete = False
            else:
                for scope in bound.scopes:
                    records.extend(await self._read_scope(scope, bound))
                # A SemanticIndex is a bounded top-k interface. It may improve lookup
                # recall, but it cannot define an exhaustive set for an exact count.
                # Counts therefore use only the complete structural/lexical scan.
                if bound.intent != PersonalMemoryQueryIntent.COUNT:
                    (
                        semantic_scores,
                        semantic_sources,
                        semantic_warnings,
                    ) = await self._semantic_scores(bound, records)
                    warnings.extend(semantic_warnings)
            if relation_task is not None:
                (
                    relation_records,
                    relation_details,
                    relation_warnings,
                    relation_available,
                ) = await relation_task
                warnings.extend(relation_warnings)
                require_relation_match = (
                    self.config.relation_hints_require_match
                    and bool(
                        bound.relation_hints
                        or bound.relation_types
                        or bound.candidate_relation_types
                    )
                    and relation_available
                )
                if require_relation_match:
                    accepted_relation_keys = {
                        key
                        for key, detail in relation_details.items()
                        if detail[0] >= self.config.minimum_relation_score
                    }
                    records = [
                        record
                        for record in relation_records
                        if (record.scope.scope_key, record.memory_id)
                        in accepted_relation_keys
                    ]
                    semantic_scores = {
                        key: value
                        for key, value in semantic_scores.items()
                        if key in accepted_relation_keys
                    }
                    semantic_sources = {
                        key: value
                        for key, value in semantic_sources.items()
                        if key in accepted_relation_keys
                    }
                    relation_details = {
                        key: value
                        for key, value in relation_details.items()
                        if key in accepted_relation_keys
                    }
                    complete = False
                    if not accepted_relation_keys:
                        warnings.append(
                            "explicit relation constraints produced no qualified "
                            "relation evidence"
                        )
                else:
                    records_by_key = {
                        (record.scope.scope_key, record.memory_id): record
                        for record in records
                    }
                    for record in relation_records:
                        records_by_key.setdefault(
                            (record.scope.scope_key, record.memory_id), record
                        )
                    records = list(records_by_key.values())
        except BaseException:
            if relation_task is not None:
                if not relation_task.done():
                    relation_task.cancel()
                await asyncio.gather(relation_task, return_exceptions=True)
            raise
        for scope in bound.scopes:
            conflict_records.extend(await self._read_conflicts(scope))
        matched: list[
            tuple[MemoryRecord, float, float, float, datetime, list[str]]
        ] = []
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
            semantic_score = semantic_scores.get(
                (record.scope.scope_key, record.memory_id), 0.0
            )
            source_names = semantic_sources.get(
                (record.scope.scope_key, record.memory_id), ()
            )
            (
                relation_score,
                relation_source,
                relation_type,
                relation_edge,
                relation_match_kind,
                relation_reranker_score,
            ) = relation_details.get(
                (record.scope.scope_key, record.memory_id),
                (0.0, "", "", "", "", None),
            )
            if semantic_score < self.config.minimum_semantic_score:
                semantic_score = 0.0
                source_names = ()
            if relation_score < self.config.minimum_relation_score:
                relation_score = 0.0
                relation_source = ""
                relation_type = ""
                relation_edge = ""
                relation_match_kind = ""
                relation_reranker_score = None
            if (
                (bound.search_text or bound.entity_mentions)
                and lexical_score < self.config.minimum_lexical_score
                and semantic_score < self.config.minimum_semantic_score
                and relation_score < self.config.minimum_relation_score
            ):
                continue
            if lexical_score >= self.config.minimum_lexical_score:
                reasons.append("lexical_match")
            if semantic_score >= self.config.minimum_semantic_score:
                reasons.append("semantic_match")
                reasons.extend(f"semantic_source:{name}" for name in source_names)
            if relation_score >= self.config.minimum_relation_score:
                reasons.extend(
                    (
                        "relation_match",
                        f"relation_source:{relation_source}",
                        f"relation_type:{relation_type}",
                        f"relation_edge:{relation_edge}",
                    )
                )
                if relation_match_kind:
                    reasons.append(f"relation_match_kind:{relation_match_kind}")
                if relation_reranker_score is not None:
                    reasons.append(
                        f"relation_reranker_score:{relation_reranker_score:.6f}"
                    )
            matched.append(
                (
                    record,
                    lexical_score,
                    semantic_score,
                    relation_score,
                    effective_at,
                    reasons,
                )
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
                _rank_score(
                    self.config,
                    bound,
                    item[0],
                    item[1],
                    item[2],
                    item[3],
                    item[4],
                ),
                item[4],
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
                    relation_score,
                    effective_at,
                ),
                lexical_score=lexical_score,
                semantic_score=semantic_score,
                relation_score=relation_score,
                effective_at=effective_at,
                reasons=reasons,
            )
            for (
                record,
                lexical_score,
                semantic_score,
                relation_score,
                effective_at,
                reasons,
            ) in matched[: self.config.limit]
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
            complete=complete,
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
        available_relation_types: Sequence[str] = (),
        relation_type_definitions: Sequence[RelationTypeDefinition] = (),
        required_relation_types: Sequence[str] = (),
    ) -> PersonalMemoryQueryResult:
        plan = await self.plan(
            planner,
            query,
            scopes,
            now=now,
            default_subject=default_subject,
            default_subject_id=default_subject_id,
            allowed_subject_ids=allowed_subject_ids,
            available_relation_types=available_relation_types,
            relation_type_definitions=relation_type_definitions,
            required_relation_types=required_relation_types,
        )
        return await self.execute(plan)

    async def _read_scope(
        self, scope: MemoryScope, plan: PersonalMemoryQueryPlan
    ) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        cursor = ""
        filters = _query_memory_filter(plan)
        while True:
            remaining = self.config.max_records_per_scope - len(records)
            if remaining <= 0:
                raise PersonalMemoryQueryReadLimitError(
                    f"active personal memories in {scope.describe()} exceed "
                    f"max_records_per_scope {self.config.max_records_per_scope}"
                )
            page = await self._store.scan(
                scope,
                filters=filters,
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

    async def _read_candidates(
        self, plan: PersonalMemoryQueryPlan
    ) -> (
        tuple[
            list[MemoryRecord],
            dict[tuple[str, str], float],
            dict[tuple[str, str], tuple[str, ...]],
            list[str],
        ]
        | None
    ):
        """Load a bounded authorized union of lexical and semantic candidates.

        Returning ``None`` requests the exhaustive lexical fallback. Exact counts
        intentionally never enter this top-k path.
        """
        assert self._semantic_index is not None
        filters = _query_memory_filter(plan)
        lexical_result, semantic_result = await asyncio.gather(
            self._store.search(
                plan.search_text,
                list(plan.scopes),
                filters=filters,
                limit=self.config.semantic_candidate_limit,
            ),
            self._search_semantic_candidates(plan, filters),
            return_exceptions=True,
        )
        if isinstance(lexical_result, BaseException):
            raise lexical_result
        if isinstance(semantic_result, BaseException):
            if not self.config.semantic_fallback_to_lexical:
                raise semantic_result
            return None

        allowed_scopes = {scope.scope_key: scope for scope in plan.scopes}
        candidates: dict[tuple[str, str], MemoryScope] = {}
        semantic_scores: dict[tuple[str, str], float] = {}
        semantic_sources: dict[tuple[str, str], list[str]] = {}
        for candidate in [*lexical_result, *semantic_result]:
            scope = candidate.scope
            memory_id = str(candidate.memory_id or "").strip()
            if scope is None or scope.scope_key not in allowed_scopes or not memory_id:
                continue
            candidates.setdefault(
                (scope.scope_key, memory_id), allowed_scopes[scope.scope_key]
            )
        for candidate in semantic_result:
            scope = candidate.scope
            memory_id = str(candidate.memory_id or "").strip()
            if scope is None or scope.scope_key not in allowed_scopes or not memory_id:
                continue
            key = (scope.scope_key, memory_id)
            semantic_scores[key] = max(
                semantic_scores.get(key, 0.0),
                min(max(float(candidate.similarity), 0.0), 1.0),
            )
            source_names = semantic_sources.setdefault(key, [])
            for source in _composite_semantic_sources(candidate):
                if source not in source_names:
                    source_names.append(source)

        loaded = await asyncio.gather(
            *(
                self._store.get(scope, memory_id)
                for (_, memory_id), scope in candidates.items()
            )
        )
        records = [
            record
            for record in loaded
            if record is not None
            and "personal-memory" in record.tags
            and record.scope.scope_key in allowed_scopes
            and _is_query_record_eligible(record, plan)
        ]
        known_ids = {(record.scope.scope_key, record.memory_id) for record in records}
        semantic_scores = {
            key: score for key, score in semantic_scores.items() if key in known_ids
        }
        bound_sources = {
            key: tuple(sources)
            for key, sources in semantic_sources.items()
            if key in known_ids
        }
        return (
            records,
            semantic_scores,
            bound_sources,
            [
                (
                    "used bounded index-first lexical and semantic candidates; "
                    "result is not an exhaustive scope snapshot"
                )
            ],
        )

    async def _search_semantic_candidates(
        self, plan: PersonalMemoryQueryPlan, filters: MemoryFilter
    ) -> Sequence[Any]:
        assert self._semantic_index is not None
        valid_at = plan.as_of
        if valid_at is None and plan.intent == PersonalMemoryQueryIntent.CURRENT:
            valid_at = plan.now
        if valid_at is not None and isinstance(
            self._semantic_index, TemporalSemanticIndex
        ):
            return await self._semantic_index.search_at(
                plan.search_text,
                plan.scopes,
                valid_at=valid_at,
                filters=filters,
                limit=self.config.semantic_candidate_limit,
            )
        return await self._semantic_index.search(
            plan.search_text,
            plan.scopes,
            filters=filters,
            limit=self.config.semantic_candidate_limit,
        )

    async def _read_relation_candidates(
        self, plan: PersonalMemoryQueryPlan
    ) -> tuple[
        list[MemoryRecord],
        dict[
            tuple[str, str],
            tuple[float, str, str, str, str, float | None],
        ],
        list[str],
        bool,
    ]:
        assert self._relation_index is not None
        valid_at = plan.as_of
        if valid_at is None and plan.intent != PersonalMemoryQueryIntent.HISTORY:
            valid_at = plan.now
        request = RelationQuery(
            query_text=plan.query,
            entity_mentions=plan.entity_mentions,
            relation_hints=plan.relation_hints,
            relation_types=plan.relation_types,
            candidate_relation_types=plan.candidate_relation_types,
            subject=plan.subject,
            subject_id=plan.subject_id,
            valid_at=valid_at,
            time_from=plan.time_from if valid_at is None else None,
            time_to=plan.time_to if valid_at is None else None,
        )
        try:
            candidates = await self._relation_index.search_relations(
                request,
                plan.scopes,
                filters=_query_memory_filter(plan),
                limit=self.config.relation_candidate_limit,
            )
        except Exception as exc:
            if not self.config.relation_fallback_to_nonrelation:
                raise
            error_name = type(exc).__name__
            if isinstance(exc, RelationIndexUnavailableError):
                error_name = "RelationIndexUnavailableError"
            return (
                [],
                {},
                [
                    (
                        "relation index unavailable; used non-relation paths: "
                        f"{error_name}"
                    )
                ],
                False,
            )

        allowed_scopes = {scope.scope_key: scope for scope in plan.scopes}
        required_relation_types = set(plan.relation_types)
        candidate_scopes: dict[tuple[str, str], MemoryScope] = {}
        details: dict[
            tuple[str, str], tuple[float, str, str, str, str, float | None]
        ] = {}
        for candidate in candidates:
            scope_key = candidate.scope.scope_key
            memory_id = str(candidate.memory_id or "").strip()
            relation_type = str(candidate.relation_type or "").strip().upper()
            if (
                scope_key not in allowed_scopes
                or not memory_id
                or (
                    required_relation_types
                    and relation_type not in required_relation_types
                )
            ):
                continue
            key = (scope_key, memory_id)
            candidate_scopes.setdefault(key, allowed_scopes[scope_key])
            score = min(max(float(candidate.score), 0.0), 1.0)
            if required_relation_types:
                score = 1.0
            elif candidate.match_kind == "type":
                # A derived index cannot turn a planner suggestion into a hard
                # relation match. Type-only evidence remains below the gate.
                score = min(score, 0.2)
            current = details.get(key)
            if current is None or score > current[0]:
                details[key] = (
                    score,
                    candidate.source,
                    candidate.relation_type,
                    candidate.edge_id,
                    candidate.match_kind,
                    candidate.reranker_score,
                )
        loaded = await asyncio.gather(
            *(
                self._store.get(scope, memory_id)
                for (_, memory_id), scope in candidate_scopes.items()
            )
        )
        records = [
            record
            for record in loaded
            if record is not None
            and "personal-memory" in record.tags
            and record.scope.scope_key in allowed_scopes
            and _is_query_record_eligible(record, plan)
        ]
        known = {(record.scope.scope_key, record.memory_id) for record in records}
        return (
            records,
            {key: value for key, value in details.items() if key in known},
            [],
            True,
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
    ) -> tuple[
        dict[tuple[str, str], float],
        dict[tuple[str, str], tuple[str, ...]],
        list[str],
    ]:
        if self._semantic_index is None or not plan.search_text:
            return {}, {}, []
        try:
            candidates = await self._search_semantic_candidates(
                plan,
                _query_memory_filter(plan),
            )
        except Exception as exc:
            if not self.config.semantic_fallback_to_lexical:
                raise
            return (
                {},
                {},
                [
                    f"semantic index unavailable; used lexical fallback: {type(exc).__name__}"
                ],
            )
        allowed_scopes = {scope.scope_key for scope in plan.scopes}
        known_ids = {(record.scope.scope_key, record.memory_id) for record in records}
        scores: dict[tuple[str, str], float] = {}
        sources: dict[tuple[str, str], list[str]] = {}
        for candidate in candidates:
            memory_id = str(candidate.memory_id or "").strip()
            candidate_key = (
                candidate.scope.scope_key if candidate.scope is not None else "",
                memory_id,
            )
            if (
                candidate.scope is None
                or candidate.scope.scope_key not in allowed_scopes
                or not memory_id
                or candidate_key not in known_ids
            ):
                continue
            score = min(max(float(candidate.similarity), 0.0), 1.0)
            scores[candidate_key] = max(scores.get(candidate_key, 0.0), score)
            source_names = sources.setdefault(candidate_key, [])
            for source in _composite_semantic_sources(candidate):
                if source not in source_names:
                    source_names.append(source)
        return scores, {key: tuple(value) for key, value in sources.items()}, []


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
    if not _is_query_record_eligible(record, plan):
        return None
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
    if plan.time_from is not None or plan.time_to is not None:
        interval_start = valid_from or effective_at
        interval_end = valid_to or (effective_at if valid_from is None else None)
        if plan.time_to is not None and interval_start > plan.time_to:
            return None
        if (
            plan.time_from is not None
            and interval_end is not None
            and interval_end < plan.time_from
        ):
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


def _visible_memory_states(plan: PersonalMemoryQueryPlan) -> frozenset[MemoryState]:
    """Return lifecycle states that may supply evidence for this query intent.

    Lifecycle and temporal validity are deliberately separate. Current/ordinary
    queries keep the established active-state behavior. Historical point-in-time
    queries may inspect inactive, previously authoritative records, but the final
    eligibility gate below requires an explicit validity interval and never admits
    rejected records.
    """

    if (
        plan.intent
        in {
            PersonalMemoryQueryIntent.HISTORY,
            PersonalMemoryQueryIntent.AS_OF,
        }
        or plan.as_of is not None
    ):
        return frozenset(
            {
                MemoryState.CANDIDATE,
                MemoryState.CONFIRMED,
                MemoryState.SUPERSEDED,
                MemoryState.EXPIRED,
            }
        )
    return ACTIVE_MEMORY_STATES


def _bind_temporal_statuses(
    intent: str,
    temporal_statuses: Sequence[str],
    *,
    has_explicit_time: bool = False,
) -> list[str]:
    """Apply intent semantics when a planner omits the equivalent hard filter.

    An intent must not merely decorate a query plan: ``current``, ``history``, and
    ``planned`` each imply a safe temporal evidence class. Explicit planner filters
    remain authoritative, while an omitted list receives the domain-neutral default.
    """

    if has_explicit_time and intent in {
        PersonalMemoryQueryIntent.HISTORY,
        PersonalMemoryQueryIntent.AS_OF,
    }:
        # A record can be valid at a historical instant while its present-day
        # classification is still ``current``. Explicit validity coordinates are
        # authoritative for time-scoped history; status labels must not erase them.
        return []
    if temporal_statuses:
        return list(temporal_statuses)
    if intent == PersonalMemoryQueryIntent.CURRENT:
        return [MemoryTemporalStatus.CURRENT, MemoryTemporalStatus.TIMELESS]
    if intent == PersonalMemoryQueryIntent.HISTORY:
        return [MemoryTemporalStatus.HISTORICAL]
    if intent == PersonalMemoryQueryIntent.PLANNED:
        return [MemoryTemporalStatus.PLANNED]
    return []


def _query_memory_filter(plan: PersonalMemoryQueryPlan) -> MemoryFilter:
    """Build the same coarse eligibility filter for every candidate path."""

    excluded_authorities = (
        None if plan.subject == Actor.AGENT else {FactAuthority.AGENT_OUTPUT}
    )
    return MemoryFilter(
        tags={"personal-memory"},
        states=set(_visible_memory_states(plan)),
        exclude_authorities=excluded_authorities,
    )


def _is_query_record_eligible(
    record: MemoryRecord, plan: PersonalMemoryQueryPlan
) -> bool:
    """Final defense-in-depth gate for lifecycle and factual authority.

    Stores and indexes are expected to honor ``MemoryFilter``, but a custom or stale
    implementation must not be able to turn Agent output into a human fact or make an
    inactive record current merely by returning it as a candidate.
    """

    if record.state not in _visible_memory_states(plan):
        return False
    if record.authority == FactAuthority.AGENT_OUTPUT and plan.subject != Actor.AGENT:
        return False
    if record.state not in {MemoryState.SUPERSEDED, MemoryState.EXPIRED}:
        return True

    valid_from = _metadata_time(record, "valid_from")
    valid_to = _metadata_time(record, "valid_to")
    if valid_from is None and valid_to is None:
        return False
    if plan.intent == PersonalMemoryQueryIntent.HISTORY:
        return _metadata_text(record, "temporal_status") == (
            MemoryTemporalStatus.HISTORICAL
        )
    if plan.as_of is None:
        return False
    if valid_from is not None and valid_from > plan.as_of:
        return False
    return valid_to is None or valid_to >= plan.as_of


def _rank_score(
    config: PersonalMemoryQueryConfig,
    plan: PersonalMemoryQueryPlan,
    record: MemoryRecord,
    lexical_score: float,
    semantic_score: float,
    relation_score: float,
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
        + config.relation_weight * relation_score
        + recency_tiebreaker,
        6,
    )


def _composite_semantic_sources(candidate: Any) -> tuple[str, ...]:
    if not isinstance(candidate, CompositeRecallResult):
        return ()
    return tuple(dict.fromkeys(item.source for item in candidate.contributions))


def _relevant_conflicts(
    plan: PersonalMemoryQueryPlan,
    active_records: Sequence[MemoryRecord],
    matched: Sequence[tuple[MemoryRecord, float, float, float, datetime, list[str]]],
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
    matched: Sequence[tuple[MemoryRecord, float, float, float, datetime, list[str]]],
) -> tuple[bool, list[str]]:
    if plan.intent not in {
        PersonalMemoryQueryIntent.CURRENT,
        PersonalMemoryQueryIntent.AS_OF,
    }:
        return False, []
    groups: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    for record, _, _, _, _, _ in matched:
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
    score = max(score, _focused_query_coverage(normalized_query, document))
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


def _focused_query_coverage(query: str, document: str) -> float:
    """Reward compact phrase coverage without letting generic single chars dominate."""
    query_text = re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", query)
    document_text = re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", document)
    size = 1 if len(query_text) <= 2 else 2
    query_terms = _fixed_ngrams(query_text, size)
    document_terms = _fixed_ngrams(document_text, size)
    if not query_terms:
        return 0.0
    overlap = sum(
        min(count, document_terms.get(term, 0)) for term, count in query_terms.items()
    )
    return overlap / sum(query_terms.values())


def _fixed_ngrams(text: str, size: int) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for index in range(max(0, len(text) - size + 1)):
        counts[text[index : index + size]] += 1
    return dict(counts)


def _detect_intent(query: str) -> QueryIntent:
    if re.search(r"几次|多少次|次数", query):
        return PersonalMemoryQueryIntent.COUNT
    if _contains_any(query, ("哪些", "列出")):
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
    cleaned = re.sub(r"20\d{2}(?:[-/年]\d{1,2})?(?:[-/月]\d{1,2})?日?", "", cleaned)
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
        "叫什么",
        "叫啥",
        "是什么",
        "为什么",
        "什么",
        "怎么",
        "为何",
        "多少",
        "的记忆",
        "相关记忆",
        "关于",
        "告诉",
        "回忆",
        "吗",
        "呢",
        "了",
        "的",
    ):
        cleaned = cleaned.replace(phrase, "")
    return re.sub(r"[\s，。！？；：、,.!?;:]+", "", cleaned).strip()


def _explicit_as_of(query: str) -> datetime | None:
    iso_match = re.search(
        r"(?P<year>20\d{2})\s*[-/年]\s*"
        r"(?P<month>\d{1,2})\s*[-/月]\s*"
        r"(?P<day>\d{1,2})\s*日?",
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
    return re.sub(r"[\s，。！？；：、,.!?;:]+", "", normalized)


def _contains_any(value: str, needles: Sequence[str]) -> bool:
    return any(needle in value for needle in needles)


def _plan_payload(plan: PersonalMemoryQueryPlan) -> dict[str, Any]:
    payload = plan.model_dump(mode="json")
    payload.pop("plan_id", None)
    # Keep plan IDs generated before the additive relation_types field valid when
    # no exact relation constraint is selected.
    if not payload.get("relation_types"):
        payload.pop("relation_types", None)
    if not payload.get("candidate_relation_types"):
        payload.pop("candidate_relation_types", None)
    return payload


def _canonical_relation_types(value: Any) -> list[str]:
    raw_items = (
        list(value)
        if isinstance(value, (list, tuple, set, frozenset))
        else []
        if value is None
        else [value]
    )
    items = [str(item or "").strip().upper() for item in raw_items]
    normalized = list(dict.fromkeys(item for item in items if item))
    invalid = [
        item
        for item in normalized
        if re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", item) is None
    ]
    if invalid:
        raise ValueError(
            f"relation types must be canonical uppercase identifiers: {invalid}"
        )
    return normalized


def _bind_relation_types(
    requested: Sequence[str], available: Sequence[str]
) -> list[str]:
    selected = _canonical_relation_types(requested)
    allowed = set(_canonical_relation_types(available))
    unknown = sorted(set(selected).difference(allowed))
    if unknown:
        raise PersonalMemoryQueryPlanningError(
            f"planner selected relation types outside the host ontology: {unknown}"
        )
    return selected


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
