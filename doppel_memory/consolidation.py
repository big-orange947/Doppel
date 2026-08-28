"""Auditable, replay-safe consolidation of evidence-bound personal memories."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from doppel_memory.indexing import memory_index_fingerprint
from doppel_memory.intelligence import (
    MemoryTemporalStatus,
    PersonalMemoryType,
    StructuredGenerationRequest,
    StructuredOutputModel,
)
from doppel_memory.models import (
    ACTIVE_MEMORY_STATES,
    FactAuthority,
    MemoryFilter,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    MemoryStateConflictError,
    WriteResult,
    WriteStatus,
    utc_now,
)
from doppel_memory.processing import (
    MemoryProposal,
    ProcessingError,
    ProcessorHooks,
    ProposalEvaluator,
    ProposalWriter,
)
from doppel_memory.store import MemoryStore


class ConsolidationOperation:
    """Closed v2 operation set; expiry and deletion are intentionally absent."""

    MERGE = "merge"
    CORRECT = "correct"
    CONFLICT = "conflict"


class ConsolidationDecision(BaseModel):
    """Pure consolidator output selecting existing records, never a write scope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Literal["merge", "correct", "conflict"]
    source_memory_ids: list[str] = Field(min_length=2)
    canonical_source_memory_id: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    explanation: str

    @field_validator("source_memory_ids")
    @classmethod
    def _normalize_sources(cls, value: list[str]) -> list[str]:
        normalized = [str(item or "").strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("source memory IDs must not be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("source memory IDs must be unique")
        return normalized

    @field_validator("canonical_source_memory_id", mode="before")
    @classmethod
    def _normalize_canonical(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("explanation", mode="before")
    @classmethod
    def _require_text(cls, value: Any) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("explanation is required")
        return normalized

    @model_validator(mode="after")
    def _require_canonical_source(self) -> ConsolidationDecision:
        if self.operation == ConsolidationOperation.CONFLICT:
            if self.canonical_source_memory_id:
                raise ValueError(
                    "conflict decisions must not select a canonical source"
                )
        elif self.canonical_source_memory_id not in self.source_memory_ids:
            raise ValueError("canonical source must be included in source_memory_ids")
        return self


class ConsolidationAnalysis(BaseModel):
    """Validated decision list returned by a consolidator."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decisions: list[ConsolidationDecision] = Field(default_factory=list)


class ConsolidationInput(BaseModel):
    """One bounded exact-scope snapshot visible to a consolidator."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: MemoryScope
    records: list[MemoryRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_snapshot(self) -> ConsolidationInput:
        memory_ids = [record.memory_id for record in self.records]
        if any(not memory_id for memory_id in memory_ids):
            raise ValueError("consolidation input records require memory IDs")
        if len(memory_ids) != len(set(memory_ids)):
            raise ValueError("consolidation input memory IDs must be unique")
        if any(
            record.scope.scope_key != self.scope.scope_key for record in self.records
        ):
            raise ValueError("consolidation input records must share one exact scope")
        return self


@runtime_checkable
class MemoryConsolidator(Protocol):
    """Select merge/correction/conflict decisions from a read-only snapshot."""

    name: str
    version: str

    async def consolidate(self, input: ConsolidationInput) -> ConsolidationAnalysis: ...


REFERENCE_CONSOLIDATION_INSTRUCTIONS = """\
You audit already-extracted personal memories. Return merge, correction, or conflict
decisions over supplied memory IDs. A merge requires claims about the same subject and
meaning. A correction requires the same non-empty topic_key, the same current or
planned temporal_status, and an explicit revision_kind=correction or retraction on the
strictly newer canonical source. When incompatible claims share that slot but no such
explicit revision exists, return conflict with an empty canonical_source_memory_id.
Conflict sources remain active. Current and planned claims may coexist and must not
replace one another. Do not generate replacement scope, authority, state, IDs,
or deletion actions. Do not generate replacement content. Do not merge separate episodes merely
because they are similar. Do not infer that a plan happened or expire temporary state.
Prefer no decision when evidence is insufficient.
"""


class ReferenceMemoryConsolidator:
    """Schema-constrained semantic consolidator using a host-owned model provider."""

    name = "doppel.reference-memory-consolidator"
    version = "2"

    def __init__(self, model: StructuredOutputModel) -> None:
        self.model = model
        _require_identity(model, "structured output model")

    async def consolidate(self, input: ConsolidationInput) -> ConsolidationAnalysis:
        bound = ConsolidationInput.model_validate(input)
        raw = await self.model.generate(
            StructuredGenerationRequest(
                instructions=REFERENCE_CONSOLIDATION_INSTRUCTIONS,
                input={
                    "scope": bound.scope.describe(),
                    "memories": [
                        {
                            "memory_id": record.memory_id,
                            "content": record.content,
                            "kind": record.kind,
                            "actor": record.actor,
                            "authority": record.authority.value,
                            "state": record.state.value,
                            "created_at": record.created_at.isoformat(),
                            "updated_at": record.updated_at.isoformat(),
                            "version": record.version,
                            "personal_memory_type": record.metadata.get(
                                "personal_memory_type", ""
                            ),
                            "topic_key": record.metadata.get("topic_key", ""),
                            "revision_kind": record.metadata.get(
                                "revision_kind", "assertion"
                            ),
                            "subject": record.metadata.get("subject", ""),
                            "subject_id": record.metadata.get("subject_id", ""),
                            "temporal_status": record.metadata.get(
                                "temporal_status", ""
                            ),
                            "valid_from": record.metadata.get("valid_from"),
                            "valid_to": record.metadata.get("valid_to"),
                            "evidence": record.metadata.get("evidence", []),
                        }
                        for record in bound.records
                    ],
                },
                output_schema=ConsolidationAnalysis.model_json_schema(),
            )
        )
        if isinstance(raw, BaseModel):
            raw = raw.model_dump(warnings=False)
        return ConsolidationAnalysis.model_validate(raw)


class DeterministicConsolidatorConfig(BaseModel):
    """Conservative exact-duplicate and stable-slot correction policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mutable_memory_types: set[str] = Field(
        default_factory=lambda: {
            PersonalMemoryType.FACT,
            PersonalMemoryType.STATE,
            PersonalMemoryType.PREFERENCE,
            PersonalMemoryType.RELATIONSHIP,
            PersonalMemoryType.PLAN,
            PersonalMemoryType.COMMITMENT,
        }
    )
    enable_latest_correction: bool = True
    emit_conflicts: bool = True

    @field_validator("mutable_memory_types", mode="before")
    @classmethod
    def _normalize_types(cls, value: Any) -> set[str]:
        normalized = {str(item or "").strip().lower() for item in set(value or ())}
        normalized.discard("")
        if not normalized:
            raise ValueError("mutable_memory_types must not be empty")
        return normalized

    @property
    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        payload["mutable_memory_types"] = sorted(self.mutable_memory_types)
        return _fingerprint(payload)


class DeterministicMemoryConsolidator:
    """Merge exact claims and require explicit revision evidence for correction."""

    name = "doppel.deterministic-memory-consolidator"
    version = "2"

    def __init__(self, config: DeterministicConsolidatorConfig | None = None) -> None:
        self.config = config or DeterministicConsolidatorConfig()

    async def consolidate(self, input: ConsolidationInput) -> ConsolidationAnalysis:
        bound = ConsolidationInput.model_validate(input)
        records = sorted(
            bound.records, key=lambda item: (item.created_at, item.memory_id)
        )
        decisions: list[ConsolidationDecision] = []
        used: set[str] = set()
        topic_groups: dict[tuple[str, str, str, str], list[MemoryRecord]] = defaultdict(
            list
        )
        for record in records:
            topic_key = _metadata_text(record, "topic_key")
            if topic_key:
                topic_groups[
                    (
                        _metadata_text(record, "subject"),
                        _metadata_text(record, "subject_id"),
                        _metadata_text(record, "personal_memory_type"),
                        topic_key,
                    )
                ].append(record)

        for group in topic_groups.values():
            if len(group) < 2:
                continue
            content_groups: dict[tuple[str, str], list[MemoryRecord]] = defaultdict(
                list
            )
            for record in group:
                content_groups[
                    (
                        _normalize_content(record.content),
                        _metadata_text(record, "temporal_status"),
                    )
                ].append(record)
            memory_type = _metadata_text(group[0], "personal_memory_type")
            temporal_groups: dict[str, list[MemoryRecord]] = defaultdict(list)
            for record in group:
                temporal_status = _metadata_text(record, "temporal_status")
                if temporal_status in {
                    MemoryTemporalStatus.CURRENT,
                    MemoryTemporalStatus.PLANNED,
                }:
                    temporal_groups[temporal_status].append(record)
            if memory_type in self.config.mutable_memory_types:
                for temporal_status, mutable_group in temporal_groups.items():
                    if len(_content_groups(mutable_group)) <= 1:
                        continue
                    canonical = _strictly_latest_record(mutable_group)
                    source_ids = [record.memory_id for record in mutable_group]
                    explicit_revision = canonical is not None and _metadata_text(
                        canonical, "revision_kind"
                    ) in {"correction", "retraction"}
                    if (
                        self.config.enable_latest_correction
                        and canonical is not None
                        and explicit_revision
                    ):
                        decisions.append(
                            ConsolidationDecision(
                                operation=ConsolidationOperation.CORRECT,
                                source_memory_ids=source_ids,
                                canonical_source_memory_id=canonical.memory_id,
                                explanation=(
                                    f"explicit {temporal_status} revision replaces "
                                    "older values in topic "
                                    f"{_metadata_text(canonical, 'topic_key')}"
                                ),
                            )
                        )
                        used.update(source_ids)
                    elif self.config.emit_conflicts:
                        decisions.append(
                            ConsolidationDecision(
                                operation=ConsolidationOperation.CONFLICT,
                                source_memory_ids=source_ids,
                                explanation=(
                                    f"incompatible {temporal_status} claims in topic "
                                    f"{_metadata_text(mutable_group[0], 'topic_key')} "
                                    "lack explicit correction evidence"
                                ),
                            )
                        )
                        used.update(source_ids)
            for exact_group in content_groups.values():
                available = [
                    record for record in exact_group if record.memory_id not in used
                ]
                if len(available) >= 2:
                    canonical = _latest_record(available)
                    source_ids = [record.memory_id for record in available]
                    decisions.append(
                        ConsolidationDecision(
                            operation=ConsolidationOperation.MERGE,
                            source_memory_ids=source_ids,
                            canonical_source_memory_id=canonical.memory_id,
                            explanation="exact normalized claims share one topic slot",
                        )
                    )
                    used.update(source_ids)

        unkeyed: dict[
            tuple[str, str, str, str, str, str], list[MemoryRecord]
        ] = defaultdict(list)
        for record in records:
            if record.memory_id in used:
                continue
            memory_type = _metadata_text(record, "personal_memory_type")
            topic_key = _metadata_text(record, "topic_key")
            if memory_type == PersonalMemoryType.EPISODE and not topic_key:
                continue
            unkeyed[
                (
                    _metadata_text(record, "subject"),
                    _metadata_text(record, "subject_id"),
                    memory_type,
                    topic_key,
                    _metadata_text(record, "temporal_status"),
                    _normalize_content(record.content),
                )
            ].append(record)
        for group in unkeyed.values():
            if len(group) < 2:
                continue
            canonical = _latest_record(group)
            source_ids = [record.memory_id for record in group]
            decisions.append(
                ConsolidationDecision(
                    operation=ConsolidationOperation.MERGE,
                    source_memory_ids=source_ids,
                    canonical_source_memory_id=canonical.memory_id,
                    explanation="exact normalized claims are duplicate personal memories",
                )
            )
            used.update(source_ids)
        return ConsolidationAnalysis(decisions=decisions)


class ConsolidationConfig(BaseModel):
    """Runner bounds and trusted decision gates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page_size: int = Field(default=200, ge=1, le=2_000)
    max_records: int = Field(default=2_000, ge=2, le=50_000)
    max_decisions: int = Field(default=200, ge=1, le=10_000)
    minimum_confidence: float = Field(default=0.8, ge=0.0, le=1.0)

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.model_dump(mode="json"))


class ConsolidationCheckpoint(BaseModel):
    """Host-owned completed-cycle marker; consolidation always audits a full scope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    cycle: int = Field(default=0, ge=0)
    consolidator: str = ""
    consolidator_version: str = ""
    config_fingerprint: str = ""
    input_fingerprint: str = ""
    completed_at: datetime | None = None

    @field_validator("completed_at")
    @classmethod
    def _normalize_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("checkpoint timestamps must include a timezone")
        return value.astimezone(UTC)


class ConsolidationSourceSnapshot(BaseModel):
    """Optimistic concurrency binding for one source memory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    state: MemoryState
    version: int = Field(ge=1)
    fingerprint: str


class ConsolidationAction(BaseModel):
    """Fully bound replayable write plus source lifecycle transitions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str
    operation: Literal["merge", "correct", "conflict"]
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[ConsolidationSourceSnapshot] = Field(min_length=2)
    proposal: MemoryProposal
    transition_sources: bool = True

    @model_validator(mode="after")
    def _validate_transition_policy(self) -> ConsolidationAction:
        expected = self.operation != ConsolidationOperation.CONFLICT
        if self.transition_sources is not expected:
            raise ValueError(
                f"{self.operation} actions require transition_sources={expected}"
            )
        return self


class ConsolidationPlan(BaseModel):
    """Immutable plan that a host can persist and replay after partial failure."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    plan_id: str
    run_id: str
    scope: MemoryScope
    consolidator: str
    consolidator_version: str
    config_fingerprint: str
    input_fingerprint: str
    input_record_count: int = Field(ge=0)
    actions: list[ConsolidationAction] = Field(default_factory=list)
    next_checkpoint: ConsolidationCheckpoint


class ConsolidationTransitionResult(BaseModel):
    """Replay-aware lifecycle result for one source memory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    status: Literal["transitioned", "already_applied", "failed"]
    from_state: MemoryState
    to_state: MemoryState = MemoryState.SUPERSEDED
    record: MemoryRecord | None = None
    error: str = ""


class ConsolidationActionResult(BaseModel):
    """Write and transition outcome for one planned decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str
    operation: Literal["merge", "correct", "conflict"]
    canonical_write: WriteResult
    transitions: list[ConsolidationTransitionResult] = Field(default_factory=list)
    complete: bool = False


class ConsolidationRunResult(BaseModel):
    """One plan execution; checkpoint is released only when every action is clean."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan: ConsolidationPlan
    actions: list[ConsolidationActionResult] = Field(default_factory=list)
    errors: list[ProcessingError] = Field(default_factory=list)
    committable_checkpoint: ConsolidationCheckpoint | None = None


class ConsolidationPlanningError(ValueError):
    """A consolidator decision cannot be bound safely to the input snapshot."""


class ConsolidationReadLimitError(RuntimeError):
    """A full-scope audit exceeded its configured record bound."""


class ConsolidationRunner:
    """Plan and replay exact-scope consolidation without a cross-record transaction."""

    def __init__(
        self, store: MemoryStore, config: ConsolidationConfig | None = None
    ) -> None:
        if not store.capabilities.pagination:
            raise NotImplementedError(
                "consolidation requires a Store with stable pagination"
            )
        self._store = store
        self.config = config or ConsolidationConfig()
        self._writer = ProposalWriter(store)

    async def plan_once(
        self,
        consolidator: MemoryConsolidator,
        scope: MemoryScope,
        *,
        checkpoint: ConsolidationCheckpoint | None = None,
        run_id: str | None = None,
    ) -> ConsolidationPlan:
        _require_identity(consolidator, "memory consolidator")
        bound_checkpoint = self._bind_checkpoint(consolidator, checkpoint)
        records = await self._read_all(scope)
        input = ConsolidationInput(scope=scope, records=records)
        raw_analysis = await consolidator.consolidate(input)
        analysis = ConsolidationAnalysis.model_validate(raw_analysis)
        if len(analysis.decisions) > self.config.max_decisions:
            raise ConsolidationPlanningError(
                f"consolidator returned {len(analysis.decisions)} decisions; "
                f"maximum is {self.config.max_decisions}"
            )
        input_fingerprint = _records_fingerprint(records)
        actions = self._bind_actions(
            consolidator, scope, records, analysis, input_fingerprint
        )
        run_identity = run_id or str(uuid4())
        plan = ConsolidationPlan(
            plan_id="",
            run_id=run_identity,
            scope=scope,
            consolidator=consolidator.name,
            consolidator_version=consolidator.version,
            config_fingerprint=self.config.fingerprint,
            input_fingerprint=input_fingerprint,
            input_record_count=len(records),
            actions=actions,
            next_checkpoint=ConsolidationCheckpoint(
                cycle=bound_checkpoint.cycle + 1,
                consolidator=consolidator.name,
                consolidator_version=consolidator.version,
                config_fingerprint=self.config.fingerprint,
                input_fingerprint=input_fingerprint,
                completed_at=utc_now(),
            ),
        )
        return plan.model_copy(
            update={"plan_id": "cpl_" + _fingerprint(_plan_identity_payload(plan))}
        )

    async def execute(
        self,
        plan: ConsolidationPlan,
        *,
        evaluator: ProposalEvaluator | None = None,
        hooks: ProcessorHooks | None = None,
    ) -> ConsolidationRunResult:
        bound = ConsolidationPlan.model_validate(plan)
        self._validate_plan_identity(bound)
        action_results: list[ConsolidationActionResult] = []
        errors: list[ProcessingError] = []
        for action in bound.actions:
            action_result, action_errors = await self._execute_action(
                bound,
                action,
                evaluator=evaluator,
                hooks=hooks,
            )
            action_results.append(action_result)
            errors.extend(action_errors)
        complete = not errors and all(result.complete for result in action_results)
        return ConsolidationRunResult(
            plan=bound,
            actions=action_results,
            errors=errors,
            committable_checkpoint=bound.next_checkpoint if complete else None,
        )

    async def run_once(
        self,
        consolidator: MemoryConsolidator,
        scope: MemoryScope,
        *,
        checkpoint: ConsolidationCheckpoint | None = None,
        evaluator: ProposalEvaluator | None = None,
        hooks: ProcessorHooks | None = None,
        run_id: str | None = None,
    ) -> ConsolidationRunResult:
        plan = await self.plan_once(
            consolidator, scope, checkpoint=checkpoint, run_id=run_id
        )
        return await self.execute(plan, evaluator=evaluator, hooks=hooks)

    async def _read_all(self, scope: MemoryScope) -> list[MemoryRecord]:
        cursor = ""
        records: list[MemoryRecord] = []
        while True:
            remaining = self.config.max_records - len(records)
            if remaining <= 0:
                raise ConsolidationReadLimitError(
                    f"active personal memories exceed max_records "
                    f"{self.config.max_records}"
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
            cursor = page.next_cursor
            if not page.has_more:
                return records
            if len(records) >= self.config.max_records:
                raise ConsolidationReadLimitError(
                    f"active personal memories exceed max_records "
                    f"{self.config.max_records}"
                )

    def _bind_checkpoint(
        self,
        consolidator: MemoryConsolidator,
        checkpoint: ConsolidationCheckpoint | None,
    ) -> ConsolidationCheckpoint:
        bound = checkpoint or ConsolidationCheckpoint()
        if bound.schema_version != 1:
            raise ConsolidationPlanningError(
                "unsupported consolidation checkpoint schema"
            )
        if bound.consolidator and bound.consolidator != consolidator.name:
            raise ConsolidationPlanningError(
                "checkpoint belongs to a different consolidator"
            )
        if (
            bound.consolidator_version
            and bound.consolidator_version != consolidator.version
        ):
            raise ConsolidationPlanningError(
                "checkpoint consolidator version does not match"
            )
        if (
            bound.config_fingerprint
            and bound.config_fingerprint != self.config.fingerprint
        ):
            raise ConsolidationPlanningError(
                "checkpoint consolidation config does not match"
            )
        return bound

    def _bind_actions(
        self,
        consolidator: MemoryConsolidator,
        scope: MemoryScope,
        records: Sequence[MemoryRecord],
        analysis: ConsolidationAnalysis,
        input_fingerprint: str,
    ) -> list[ConsolidationAction]:
        known = {record.memory_id: record for record in records}
        claimed_sources: set[str] = set()
        actions: list[ConsolidationAction] = []
        for decision in analysis.decisions:
            if decision.confidence < self.config.minimum_confidence:
                continue
            unknown = set(decision.source_memory_ids).difference(known)
            if unknown:
                raise ConsolidationPlanningError(
                    f"decision references unknown memory IDs: {sorted(unknown)}"
                )
            overlap = claimed_sources.intersection(decision.source_memory_ids)
            if overlap:
                raise ConsolidationPlanningError(
                    f"source memories appear in multiple decisions: {sorted(overlap)}"
                )
            sources = [known[memory_id] for memory_id in decision.source_memory_ids]
            self._validate_source_compatibility(decision, sources)
            canonical = (
                known[decision.canonical_source_memory_id]
                if decision.canonical_source_memory_id
                else None
            )
            decision_payload = {
                "operation": decision.operation,
                "scope_key": scope.scope_key,
                "consolidator": f"{consolidator.name}:{consolidator.version}",
                "sources": sorted(
                    (record.memory_id, record.version) for record in sources
                ),
                "canonical": canonical.memory_id if canonical is not None else "",
                "content": canonical.content if canonical is not None else "",
            }
            decision_id = "cds_" + _fingerprint(decision_payload)
            if decision.operation == ConsolidationOperation.CONFLICT:
                proposal = _conflict_proposal(
                    scope,
                    sources,
                    decision,
                    decision_id=decision_id,
                    consolidator=consolidator,
                    config_fingerprint=self.config.fingerprint,
                    input_fingerprint=input_fingerprint,
                )
            else:
                assert canonical is not None
                proposal = _canonical_proposal(
                    scope,
                    canonical,
                    sources,
                    decision,
                    decision_id=decision_id,
                    consolidator=consolidator,
                    config_fingerprint=self.config.fingerprint,
                    input_fingerprint=input_fingerprint,
                )
            actions.append(
                ConsolidationAction(
                    decision_id=decision_id,
                    operation=decision.operation,
                    explanation=decision.explanation,
                    confidence=decision.confidence,
                    sources=[
                        ConsolidationSourceSnapshot(
                            memory_id=record.memory_id,
                            state=record.state,
                            version=record.version,
                            fingerprint=memory_index_fingerprint(record),
                        )
                        for record in sources
                    ],
                    proposal=proposal,
                    transition_sources=(
                        decision.operation != ConsolidationOperation.CONFLICT
                    ),
                )
            )
            claimed_sources.update(decision.source_memory_ids)
        return actions

    def _validate_source_compatibility(
        self, decision: ConsolidationDecision, sources: Sequence[MemoryRecord]
    ) -> None:
        if any(record.state not in ACTIVE_MEMORY_STATES for record in sources):
            raise ConsolidationPlanningError(
                "consolidation decisions require active source memories"
            )
        attributes = ("actor", "authority", "kind")
        for attribute in attributes:
            if len({getattr(record, attribute) for record in sources}) != 1:
                raise ConsolidationPlanningError(
                    f"source memories disagree on trusted {attribute}"
                )
        for key in ("subject", "subject_id", "personal_memory_type"):
            if len({_metadata_text(record, key) for record in sources}) != 1:
                raise ConsolidationPlanningError(f"source memories disagree on {key}")
        topic_keys = {_metadata_text(record, "topic_key") for record in sources}
        nonempty_topics = topic_keys.difference({""})
        if len(nonempty_topics) > 1:
            raise ConsolidationPlanningError(
                "source memories disagree on non-empty topic_key"
            )
        if decision.operation in {
            ConsolidationOperation.CORRECT,
            ConsolidationOperation.CONFLICT,
        } and (len(nonempty_topics) != 1 or "" in topic_keys):
            raise ConsolidationPlanningError(
                f"{decision.operation} requires one identical non-empty topic_key"
            )
        if decision.operation in {
            ConsolidationOperation.CORRECT,
            ConsolidationOperation.CONFLICT,
        }:
            temporal_statuses = {
                _metadata_text(record, "temporal_status") for record in sources
            }
            if len(temporal_statuses) != 1 or not temporal_statuses.issubset(
                {
                    MemoryTemporalStatus.CURRENT,
                    MemoryTemporalStatus.PLANNED,
                }
            ):
                raise ConsolidationPlanningError(
                    f"{decision.operation} requires one shared current or planned "
                    "temporal_status"
                )
        if decision.operation == ConsolidationOperation.CORRECT:
            canonical = next(
                record
                for record in sources
                if record.memory_id == decision.canonical_source_memory_id
            )
            if _strictly_latest_record(sources) != canonical:
                raise ConsolidationPlanningError(
                    "correction canonical source must be strictly latest"
                )
            if _metadata_text(canonical, "revision_kind") not in {
                "correction",
                "retraction",
            }:
                raise ConsolidationPlanningError(
                    "correction requires explicit correction or retraction evidence"
                )
        if (
            decision.operation == ConsolidationOperation.CONFLICT
            and len(_content_groups(sources)) <= 1
        ):
            raise ConsolidationPlanningError(
                "conflict requires incompatible source contents"
            )

    def _validate_plan_identity(self, plan: ConsolidationPlan) -> None:
        if plan.schema_version != 1:
            raise ConsolidationPlanningError("unsupported consolidation plan schema")
        if plan.config_fingerprint != self.config.fingerprint:
            raise ConsolidationPlanningError(
                "consolidation plan config does not match this runner"
            )
        if plan.next_checkpoint.config_fingerprint != self.config.fingerprint:
            raise ConsolidationPlanningError(
                "consolidation plan checkpoint config does not match"
            )
        if plan.next_checkpoint.consolidator != plan.consolidator or (
            plan.next_checkpoint.consolidator_version != plan.consolidator_version
        ):
            raise ConsolidationPlanningError(
                "consolidation plan checkpoint identity does not match"
            )
        expected_plan_id = "cpl_" + _fingerprint(_plan_identity_payload(plan))
        if plan.plan_id != expected_plan_id:
            raise ConsolidationPlanningError(
                "consolidation plan content does not match its plan_id"
            )

    async def _execute_action(
        self,
        plan: ConsolidationPlan,
        action: ConsolidationAction,
        *,
        evaluator: ProposalEvaluator | None,
        hooks: ProcessorHooks | None,
    ) -> tuple[ConsolidationActionResult, list[ProcessingError]]:
        errors: list[ProcessingError] = []
        current: dict[str, MemoryRecord] = {}
        already_applied: set[str] = set()
        for source in action.sources:
            record = await self._store.get(plan.scope, source.memory_id)
            if record is None:
                errors.append(
                    _error(
                        "source_validate",
                        "KeyError",
                        f"source memory is missing: {source.memory_id}",
                        plan.consolidator,
                    )
                )
                continue
            current[source.memory_id] = record
            if (
                action.transition_sources
                and record.state is MemoryState.SUPERSEDED
                and record.version == source.version + 1
            ):
                already_applied.add(source.memory_id)
                continue
            if record.state != source.state or record.version != source.version:
                errors.append(
                    _error(
                        "source_validate",
                        "MemoryStateConflictError",
                        (
                            f"source {source.memory_id} changed from "
                            f"{source.state.value}/v{source.version} to "
                            f"{record.state.value}/v{record.version}"
                        ),
                        plan.consolidator,
                    )
                )
                continue
            if memory_index_fingerprint(record) != source.fingerprint:
                errors.append(
                    _error(
                        "source_validate",
                        "MemoryFingerprintConflict",
                        f"source memory fingerprint changed: {source.memory_id}",
                        plan.consolidator,
                    )
                )
        if errors:
            return (
                ConsolidationActionResult(
                    decision_id=action.decision_id,
                    operation=action.operation,
                    canonical_write=WriteResult(
                        status=WriteStatus.FAILED,
                        error_code="source_conflict",
                        message="source validation failed",
                    ),
                ),
                errors,
            )

        batch = await self._writer.write_batch(
            [action.proposal],
            allowed_scopes=[plan.scope],
            evaluator=evaluator,
            hooks=hooks,
        )
        errors.extend(batch.errors)
        write = batch.write_results[0]
        write_ok = (
            write.status in {WriteStatus.CREATED, WriteStatus.DUPLICATE}
            and write.record is not None
        )
        if write_ok:
            assert write.record is not None
            consolidation = write.record.metadata.get("consolidation", {})
            if not isinstance(consolidation, dict) or (
                consolidation.get("decision_id") != action.decision_id
            ):
                write_ok = False
                errors.append(
                    _error(
                        "canonical_write",
                        "ConsolidationReplayConflict",
                        "idempotent canonical record does not match the plan decision",
                        plan.consolidator,
                    )
                )
        if not write_ok:
            if not errors:
                errors.append(
                    _error(
                        "canonical_write",
                        "CanonicalWriteFailed",
                        write.message
                        or write.error_code
                        or "canonical was not persisted",
                        plan.consolidator,
                    )
                )
            return (
                ConsolidationActionResult(
                    decision_id=action.decision_id,
                    operation=action.operation,
                    canonical_write=write,
                ),
                errors,
            )

        transitions: list[ConsolidationTransitionResult] = []
        if not action.transition_sources:
            return (
                ConsolidationActionResult(
                    decision_id=action.decision_id,
                    operation=action.operation,
                    canonical_write=write,
                    transitions=[],
                    complete=not errors,
                ),
                errors,
            )
        for source in action.sources:
            if source.memory_id in already_applied:
                transitions.append(
                    ConsolidationTransitionResult(
                        memory_id=source.memory_id,
                        status="already_applied",
                        from_state=source.state,
                        record=current[source.memory_id],
                    )
                )
                continue
            try:
                transitioned = await self._store.transition(
                    plan.scope,
                    source.memory_id,
                    MemoryState.SUPERSEDED,
                    expected_state=source.state,
                )
                transitions.append(
                    ConsolidationTransitionResult(
                        memory_id=source.memory_id,
                        status="transitioned",
                        from_state=source.state,
                        record=transitioned,
                    )
                )
            except (KeyError, MemoryStateConflictError) as exc:
                transitions.append(
                    ConsolidationTransitionResult(
                        memory_id=source.memory_id,
                        status="failed",
                        from_state=source.state,
                        error=str(exc),
                    )
                )
                errors.append(
                    _error(
                        "source_transition",
                        type(exc).__name__,
                        str(exc),
                        plan.consolidator,
                    )
                )
        return (
            ConsolidationActionResult(
                decision_id=action.decision_id,
                operation=action.operation,
                canonical_write=write,
                transitions=transitions,
                complete=not errors
                and all(item.status != "failed" for item in transitions),
            ),
            errors,
        )


def _canonical_proposal(
    scope: MemoryScope,
    canonical: MemoryRecord,
    sources: Sequence[MemoryRecord],
    decision: ConsolidationDecision,
    *,
    decision_id: str,
    consolidator: MemoryConsolidator,
    config_fingerprint: str,
    input_fingerprint: str,
) -> MemoryProposal:
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for record in sources:
        evidence = record.metadata.get("evidence", [])
        if isinstance(evidence, list):
            for item in evidence:
                if isinstance(item, dict):
                    evidence_id = str(item.get("evidence_id", "") or "").strip()
                    if evidence_id:
                        evidence_by_id.setdefault(evidence_id, dict(item))
        fallback_id = record.source_message_id or record.source_event_id
        if fallback_id and fallback_id not in evidence_by_id:
            evidence_by_id[fallback_id] = {
                "evidence_id": fallback_id,
                "message_id": record.source_message_id,
                "event_id": record.source_event_id,
                "actor": record.actor,
                "at": record.created_at.isoformat(),
            }
    metadata = dict(canonical.metadata)
    metadata["evidence"] = list(evidence_by_id.values())
    metadata["consolidation"] = {
        "decision_id": decision_id,
        "operation": decision.operation,
        "explanation": decision.explanation,
        "source_memories": [
            {
                "memory_id": record.memory_id,
                "version": record.version,
                "state": record.state.value,
                "fingerprint": memory_index_fingerprint(record),
            }
            for record in sources
        ],
        "canonical_source_memory_id": canonical.memory_id,
        "consolidator": consolidator.name,
        "consolidator_version": consolidator.version,
        "config_fingerprint": config_fingerprint,
        "input_fingerprint": input_fingerprint,
    }
    chain = list(
        dict.fromkeys(
            [
                *(str(item) for item in canonical.metadata.get("derived_chain", [])),
                *(f"memory:{record.memory_id}" for record in sources),
            ]
        )
    )
    return MemoryProposal(
        scope=scope,
        content=canonical.content,
        kind=canonical.kind,
        actor=canonical.actor,
        authority=canonical.authority,
        confidence=decision.confidence,
        proposed_state=canonical.state,
        tags=list(dict.fromkeys([*canonical.tags, "consolidated", decision.operation])),
        importance=max(record.importance for record in sources),
        idempotency_key=f"consolidation:{decision_id}",
        source_event_id=canonical.source_event_id,
        source_message_id=canonical.source_message_id,
        processor=consolidator.name,
        processor_version=consolidator.version,
        derived_chain=chain,
        created_at=canonical.created_at,
        metadata=metadata,
    )


def _conflict_proposal(
    scope: MemoryScope,
    sources: Sequence[MemoryRecord],
    decision: ConsolidationDecision,
    *,
    decision_id: str,
    consolidator: MemoryConsolidator,
    config_fingerprint: str,
    input_fingerprint: str,
) -> MemoryProposal:
    anchor = _latest_record(sources)
    source_snapshots = [
        {
            "memory_id": record.memory_id,
            "version": record.version,
            "state": record.state.value,
            "fingerprint": memory_index_fingerprint(record),
        }
        for record in sources
    ]
    conflict = {
        "conflict_id": decision_id,
        "status": "open",
        "reason": decision.explanation,
        "source_memories": source_snapshots,
        "subject": _metadata_text(anchor, "subject"),
        "subject_id": _metadata_text(anchor, "subject_id"),
        "personal_memory_type": _metadata_text(anchor, "personal_memory_type"),
        "topic_key": _metadata_text(anchor, "topic_key"),
        "temporal_status": _metadata_text(anchor, "temporal_status"),
    }
    metadata = {
        "subject": conflict["subject"],
        "subject_id": conflict["subject_id"],
        "personal_memory_type": conflict["personal_memory_type"],
        "topic_key": conflict["topic_key"],
        "temporal_status": conflict["temporal_status"],
        "conflict": conflict,
        "consolidation": {
            "decision_id": decision_id,
            "operation": decision.operation,
            "explanation": decision.explanation,
            "source_memories": source_snapshots,
            "canonical_source_memory_id": "",
            "consolidator": consolidator.name,
            "consolidator_version": consolidator.version,
            "config_fingerprint": config_fingerprint,
            "input_fingerprint": input_fingerprint,
        },
    }
    chain = [f"memory:{record.memory_id}" for record in sources]
    return MemoryProposal(
        scope=scope,
        content=(
            "Unresolved personal-memory conflict in topic "
            f"{conflict['topic_key']} across {len(sources)} active claims."
        ),
        kind="memory_conflict",
        actor=anchor.actor,
        authority=FactAuthority.DERIVED_SUMMARY,
        confidence=decision.confidence,
        proposed_state=MemoryState.CONFIRMED,
        tags=["memory-conflict", "open"],
        importance=max(record.importance for record in sources),
        idempotency_key=f"consolidation:{decision_id}",
        processor=consolidator.name,
        processor_version=consolidator.version,
        derived_chain=chain,
        created_at=anchor.created_at,
        metadata=metadata,
    )


def _content_groups(records: Sequence[MemoryRecord]) -> dict[str, list[MemoryRecord]]:
    groups: dict[str, list[MemoryRecord]] = defaultdict(list)
    for record in records:
        groups[_normalize_content(record.content)].append(record)
    return groups


def _plan_identity_payload(plan: ConsolidationPlan) -> dict[str, Any]:
    payload = plan.model_dump(mode="json")
    payload.pop("plan_id", None)
    return payload


def _latest_record(records: Sequence[MemoryRecord]) -> MemoryRecord:
    return max(records, key=lambda item: (_effective_time(item), item.memory_id))


def _strictly_latest_record(records: Sequence[MemoryRecord]) -> MemoryRecord | None:
    if not records:
        return None
    canonical = _latest_record(records)
    if all(
        record.memory_id == canonical.memory_id
        or _effective_time(canonical) > _effective_time(record)
        for record in records
    ):
        return canonical
    return None


def _effective_time(record: MemoryRecord) -> datetime:
    raw = record.metadata.get("valid_from")
    if isinstance(raw, str) and raw:
        try:
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is not None:
                return parsed.astimezone(UTC)
        except ValueError:
            pass
    return record.created_at


def _normalize_content(content: str) -> str:
    normalized = unicodedata.normalize("NFKC", content).lower().strip()
    return re.sub(r"[\s，。！？；：、,.!?;:]+", "", normalized)


def _metadata_text(record: MemoryRecord, key: str) -> str:
    return str(record.metadata.get(key, "") or "").strip().lower()


def _records_fingerprint(records: Sequence[MemoryRecord]) -> str:
    return _fingerprint(
        sorted(
            (record.memory_id, memory_index_fingerprint(record)) for record in records
        )
    )


def _require_identity(component: Any, label: str) -> None:
    if not str(getattr(component, "name", "") or "").strip():
        raise ValueError(f"{label} name must not be empty")
    if not str(getattr(component, "version", "") or "").strip():
        raise ValueError(f"{label} version must not be empty")


def _error(
    stage: str, error_type: str, message: str, processor: str
) -> ProcessingError:
    return ProcessingError(
        stage=stage,
        error_type=error_type,
        message=message,
        processor=processor,
    )


def _fingerprint(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
