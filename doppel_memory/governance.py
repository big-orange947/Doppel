"""Conservative, auditable lifecycle governance for personal memories.

Governance is deliberately additive to the stable Store protocol.  Every change
creates an immutable replacement snapshot and then supersedes the active source;
an archive is an ``expired`` replacement snapshot, and restoration creates a new
active snapshot from that archive.  No policy decision deletes evidence.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from doppel_memory.indexing import memory_index_fingerprint
from doppel_memory.intelligence import PersonalMemoryType
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


class MemoryGovernanceOperation:
    """Closed v1 operation set; deletion is intentionally absent."""

    REINFORCE = "reinforce"
    DECAY = "decay"
    ARCHIVE = "archive"
    RESTORE = "restore"


class MemoryGovernanceDecision(BaseModel):
    """Pure policy output over one existing active memory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Literal["reinforce", "decay", "archive"]
    source_memory_id: str
    target_importance: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str

    @field_validator("source_memory_id", "reason", mode="before")
    @classmethod
    def _require_text(cls, value: Any) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("source_memory_id and reason are required")
        return normalized

    @model_validator(mode="after")
    def _validate_target(self) -> MemoryGovernanceDecision:
        if (
            self.operation
            in {
                MemoryGovernanceOperation.REINFORCE,
                MemoryGovernanceOperation.DECAY,
            }
            and self.target_importance is None
        ):
            raise ValueError(f"{self.operation} requires target_importance")
        if self.operation == MemoryGovernanceOperation.ARCHIVE and (
            self.target_importance is not None
        ):
            raise ValueError("archive must not change importance")
        return self


class MemoryGovernanceAnalysis(BaseModel):
    """Validated decision list returned by a governance policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    decisions: list[MemoryGovernanceDecision] = Field(default_factory=list)


class MemoryGovernanceInput(BaseModel):
    """One bounded exact-scope active snapshot visible to a policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    scope: MemoryScope
    records: list[MemoryRecord] = Field(default_factory=list)
    now: datetime

    @field_validator("now")
    @classmethod
    def _normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("governance time must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_snapshot(self) -> MemoryGovernanceInput:
        ids = [record.memory_id for record in self.records]
        if any(not memory_id for memory_id in ids):
            raise ValueError("governance input records require memory IDs")
        if len(ids) != len(set(ids)):
            raise ValueError("governance input memory IDs must be unique")
        if any(
            record.scope.scope_key != self.scope.scope_key for record in self.records
        ):
            raise ValueError("governance input records must share one exact scope")
        if any(record.state not in ACTIVE_MEMORY_STATES for record in self.records):
            raise ValueError("governance input records must be active")
        return self


@runtime_checkable
class MemoryGovernancePolicy(Protocol):
    """Proposes lifecycle decisions from a read-only snapshot; never writes."""

    name: str
    version: str

    async def evaluate(
        self, input: MemoryGovernanceInput
    ) -> MemoryGovernanceAnalysis: ...


class DeterministicGovernancePolicyConfig(BaseModel):
    """Conservative defaults: explicit validity may archive; decay is opt-in."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reinforcement_evidence_threshold: int = Field(default=3, ge=2, le=100)
    reinforcement_step: float = Field(default=0.1, gt=0.0, le=1.0)
    reinforcement_cap: float = Field(default=0.9, ge=0.0, le=1.0)
    expirable_memory_types: frozenset[str] = frozenset(
        {
            PersonalMemoryType.STATE,
            PersonalMemoryType.PLAN,
            PersonalMemoryType.COMMITMENT,
        }
    )
    enable_decay: bool = False
    ephemeral_retention_classes: frozenset[str] = frozenset({"ephemeral"})
    decay_after_days: int = Field(default=30, ge=1, le=36_500)
    decay_step: float = Field(default=0.1, gt=0.0, le=1.0)
    decay_floor: float = Field(default=0.1, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_bounds(self) -> DeterministicGovernancePolicyConfig:
        if self.decay_floor > self.reinforcement_cap:
            raise ValueError("decay_floor must not exceed reinforcement_cap")
        return self

    @property
    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        payload["expirable_memory_types"] = sorted(self.expirable_memory_types)
        payload["ephemeral_retention_classes"] = sorted(
            self.ephemeral_retention_classes
        )
        return _fingerprint(payload)


class DeterministicMemoryGovernancePolicy:
    """Evidence-aware reinforcement and explicit-time lifecycle governance."""

    name = "doppel.deterministic-memory-governance"
    version = "1"

    def __init__(
        self, config: DeterministicGovernancePolicyConfig | None = None
    ) -> None:
        self.config = config or DeterministicGovernancePolicyConfig()

    async def evaluate(self, input: MemoryGovernanceInput) -> MemoryGovernanceAnalysis:
        bound = MemoryGovernanceInput.model_validate(input)
        decisions: list[MemoryGovernanceDecision] = []
        for record in bound.records:
            archive = self._archive_decision(record, bound.now)
            if archive is not None:
                decisions.append(archive)
                continue
            decay = self._decay_decision(record, bound.now)
            if decay is not None:
                decisions.append(decay)
                continue
            reinforce = self._reinforcement_decision(record)
            if reinforce is not None:
                decisions.append(reinforce)
        return MemoryGovernanceAnalysis(decisions=decisions)

    def _archive_decision(
        self, record: MemoryRecord, now: datetime
    ) -> MemoryGovernanceDecision | None:
        memory_type = _metadata_text(record, "personal_memory_type")
        if memory_type not in self.config.expirable_memory_types:
            return None
        valid_to = _metadata_time(record, "valid_to")
        if valid_to is None or valid_to >= now:
            return None
        return MemoryGovernanceDecision(
            operation=MemoryGovernanceOperation.ARCHIVE,
            source_memory_id=record.memory_id,
            reason=(
                f"explicit valid_to {valid_to.isoformat()} ended before "
                f"the governance time {now.isoformat()}"
            ),
        )

    def _decay_decision(
        self, record: MemoryRecord, now: datetime
    ) -> MemoryGovernanceDecision | None:
        if not self.config.enable_decay:
            return None
        retention_class = _metadata_text(record, "retention_class")
        if retention_class not in self.config.ephemeral_retention_classes:
            return None
        if record.importance <= self.config.decay_floor:
            return None
        anchor = _latest_evidence_time(record) or record.created_at
        governance = record.metadata.get("governance", {})
        if isinstance(governance, dict) and governance.get("operation") == "decay":
            governed_at = _parse_time(governance.get("evaluated_at"))
            if governed_at is not None:
                anchor = max(anchor, governed_at)
        if now - anchor < timedelta(days=self.config.decay_after_days):
            return None
        target = max(
            self.config.decay_floor, record.importance - self.config.decay_step
        )
        if target >= record.importance:
            return None
        return MemoryGovernanceDecision(
            operation=MemoryGovernanceOperation.DECAY,
            source_memory_id=record.memory_id,
            target_importance=target,
            reason=(
                "host opted this memory into ephemeral decay and its evidence "
                f"has not changed for {self.config.decay_after_days} days"
            ),
        )

    def _reinforcement_decision(
        self, record: MemoryRecord
    ) -> MemoryGovernanceDecision | None:
        if record.authority not in {
            FactAuthority.HUMAN_SELF,
            FactAuthority.PEER_STATEMENT,
        }:
            return None
        evidence_count = len(_evidence_ids(record))
        if evidence_count < self.config.reinforcement_evidence_threshold:
            return None
        governance = record.metadata.get("governance", {})
        reinforced_count = 0
        if isinstance(governance, dict):
            reinforced_count = _safe_nonnegative_int(
                governance.get("observed_evidence_count", 0)
            )
        if evidence_count <= reinforced_count:
            return None
        if record.importance >= self.config.reinforcement_cap:
            return None
        increments = evidence_count - self.config.reinforcement_evidence_threshold + 1
        target = min(
            self.config.reinforcement_cap,
            record.importance + self.config.reinforcement_step * increments,
        )
        if target <= record.importance:
            return None
        return MemoryGovernanceDecision(
            operation=MemoryGovernanceOperation.REINFORCE,
            source_memory_id=record.memory_id,
            target_importance=target,
            reason=f"{evidence_count} distinct trusted evidence items support the memory",
        )


class MemoryGovernanceConfig(BaseModel):
    """Runner bounds and trusted decision gate."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    page_size: int = Field(default=200, ge=1, le=2_000)
    max_records: int = Field(default=2_000, ge=1, le=50_000)
    max_decisions: int = Field(default=200, ge=1, le=10_000)
    minimum_confidence: float = Field(default=0.8, ge=0.0, le=1.0)

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.model_dump(mode="json"))


class MemoryGovernanceCheckpoint(BaseModel):
    """Host-owned marker released only after a full successful cycle."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: int = Field(default=1, ge=1)
    cycle: int = Field(default=0, ge=0)
    policy: str = ""
    policy_version: str = ""
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


class MemoryGovernanceSourceSnapshot(BaseModel):
    """Optimistic concurrency binding for one source memory."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    memory_id: str
    state: MemoryState
    version: int = Field(ge=1)
    fingerprint: str


class MemoryGovernanceAction(BaseModel):
    """One fully bound replayable replacement operation."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    decision_id: str
    operation: Literal["reinforce", "decay", "archive", "restore"]
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: MemoryGovernanceSourceSnapshot
    proposal: MemoryProposal
    transition_source: bool = True


class MemoryGovernancePlan(BaseModel):
    """Immutable plan a host can persist and replay after partial failure."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: int = 1
    plan_id: str
    run_id: str
    scope: MemoryScope
    policy: str
    policy_version: str
    evaluated_at: datetime
    config_fingerprint: str
    input_fingerprint: str
    input_record_count: int = Field(ge=0)
    actions: list[MemoryGovernanceAction] = Field(default_factory=list)
    next_checkpoint: MemoryGovernanceCheckpoint | None = None

    @field_validator("evaluated_at")
    @classmethod
    def _normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("plan time must include a timezone")
        return value.astimezone(UTC)


class MemoryGovernanceTransitionResult(BaseModel):
    """Replay-aware lifecycle result for one source memory."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    memory_id: str
    status: Literal["transitioned", "already_applied", "not_required", "failed"]
    from_state: MemoryState
    to_state: MemoryState = MemoryState.SUPERSEDED
    record: MemoryRecord | None = None
    error: str = ""


class MemoryGovernanceActionResult(BaseModel):
    """Replacement write and source transition outcome."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    decision_id: str
    operation: Literal["reinforce", "decay", "archive", "restore"]
    replacement_write: WriteResult
    transition: MemoryGovernanceTransitionResult | None = None
    complete: bool = False


class MemoryGovernanceRunResult(BaseModel):
    """One plan execution; checkpoint is available only after clean completion."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    plan: MemoryGovernancePlan
    actions: list[MemoryGovernanceActionResult] = Field(default_factory=list)
    errors: list[ProcessingError] = Field(default_factory=list)
    committable_checkpoint: MemoryGovernanceCheckpoint | None = None


class MemoryGovernancePlanningError(ValueError):
    """A governance decision cannot be safely bound to its input snapshot."""


class MemoryGovernanceReadLimitError(RuntimeError):
    """A full exact-scope governance audit exceeded its configured bound."""


class MemoryGovernanceRunner:
    """Plan and replay personal-memory lifecycle governance without deletion."""

    def __init__(
        self, store: MemoryStore, config: MemoryGovernanceConfig | None = None
    ) -> None:
        if not store.capabilities.pagination:
            raise NotImplementedError("governance requires stable Store pagination")
        self._store = store
        self.config = config or MemoryGovernanceConfig()
        self._writer = ProposalWriter(store)

    async def plan_once(
        self,
        policy: MemoryGovernancePolicy,
        scope: MemoryScope,
        *,
        now: datetime | None = None,
        checkpoint: MemoryGovernanceCheckpoint | None = None,
        run_id: str | None = None,
    ) -> MemoryGovernancePlan:
        _require_identity(policy)
        evaluated_at = _aware(now or utc_now())
        bound_checkpoint = self._bind_checkpoint(policy, checkpoint)
        records = await self._read_active(scope)
        analysis = MemoryGovernanceAnalysis.model_validate(
            await policy.evaluate(
                MemoryGovernanceInput(scope=scope, records=records, now=evaluated_at)
            )
        )
        if len(analysis.decisions) > self.config.max_decisions:
            raise MemoryGovernancePlanningError(
                f"policy returned {len(analysis.decisions)} decisions; maximum is "
                f"{self.config.max_decisions}"
            )
        input_fingerprint = _records_fingerprint(records)
        actions = self._bind_actions(
            policy, scope, records, analysis, input_fingerprint, evaluated_at
        )
        plan = MemoryGovernancePlan(
            plan_id="",
            run_id=run_id or str(uuid4()),
            scope=scope,
            policy=policy.name,
            policy_version=policy.version,
            evaluated_at=evaluated_at,
            config_fingerprint=self.config.fingerprint,
            input_fingerprint=input_fingerprint,
            input_record_count=len(records),
            actions=actions,
            next_checkpoint=MemoryGovernanceCheckpoint(
                cycle=bound_checkpoint.cycle + 1,
                policy=policy.name,
                policy_version=policy.version,
                config_fingerprint=self.config.fingerprint,
                input_fingerprint=input_fingerprint,
                completed_at=evaluated_at,
            ),
        )
        return _bind_plan_id(plan)

    async def plan_restore(
        self,
        scope: MemoryScope,
        archived_memory_id: str,
        *,
        target_state: MemoryState = MemoryState.CANDIDATE,
        now: datetime | None = None,
        run_id: str | None = None,
    ) -> MemoryGovernancePlan:
        if target_state not in ACTIVE_MEMORY_STATES:
            raise MemoryGovernancePlanningError("restore target must be active")
        source = await self._store.get(scope, str(archived_memory_id or "").strip())
        if source is None:
            raise MemoryGovernancePlanningError("archived memory does not exist")
        governance = source.metadata.get("governance", {})
        if source.state is not MemoryState.EXPIRED or not isinstance(governance, dict):
            raise MemoryGovernancePlanningError(
                "restore requires an expired Doppel governance archive snapshot"
            )
        if governance.get("operation") != MemoryGovernanceOperation.ARCHIVE:
            raise MemoryGovernancePlanningError(
                "restore source is not a Doppel governance archive snapshot"
            )
        evaluated_at = _aware(now or utc_now())
        input_fingerprint = _records_fingerprint([source])
        reason = "host explicitly requested recovery from an archived snapshot"
        decision_id = "gov_" + _fingerprint(
            {
                "operation": "restore",
                "scope_key": scope.scope_key,
                "source": [source.memory_id, source.version],
                "target_state": target_state.value,
            }
        )
        proposal = _replacement_proposal(
            scope,
            source,
            operation=MemoryGovernanceOperation.RESTORE,
            decision_id=decision_id,
            reason=reason,
            confidence=1.0,
            target_importance=source.importance,
            target_state=target_state,
            policy="doppel.explicit-restore",
            policy_version="1",
            config_fingerprint=self.config.fingerprint,
            input_fingerprint=input_fingerprint,
            evaluated_at=evaluated_at,
        )
        action = MemoryGovernanceAction(
            decision_id=decision_id,
            operation=MemoryGovernanceOperation.RESTORE,
            reason=reason,
            confidence=1.0,
            source=_source_snapshot(source),
            proposal=proposal,
            transition_source=False,
        )
        plan = MemoryGovernancePlan(
            plan_id="",
            run_id=run_id or str(uuid4()),
            scope=scope,
            policy="doppel.explicit-restore",
            policy_version="1",
            evaluated_at=evaluated_at,
            config_fingerprint=self.config.fingerprint,
            input_fingerprint=input_fingerprint,
            input_record_count=1,
            actions=[action],
            next_checkpoint=None,
        )
        return _bind_plan_id(plan)

    async def execute(
        self,
        plan: MemoryGovernancePlan,
        *,
        evaluator: ProposalEvaluator | None = None,
        hooks: ProcessorHooks | None = None,
    ) -> MemoryGovernanceRunResult:
        bound = MemoryGovernancePlan.model_validate(plan)
        self._validate_plan(bound)
        action_results: list[MemoryGovernanceActionResult] = []
        errors: list[ProcessingError] = []
        for action in bound.actions:
            result, action_errors = await self._execute_action(
                bound, action, evaluator=evaluator, hooks=hooks
            )
            action_results.append(result)
            errors.extend(action_errors)
        complete = not errors and all(item.complete for item in action_results)
        return MemoryGovernanceRunResult(
            plan=bound,
            actions=action_results,
            errors=errors,
            committable_checkpoint=(bound.next_checkpoint if complete else None),
        )

    async def run_once(
        self,
        policy: MemoryGovernancePolicy,
        scope: MemoryScope,
        *,
        now: datetime | None = None,
        checkpoint: MemoryGovernanceCheckpoint | None = None,
        evaluator: ProposalEvaluator | None = None,
        hooks: ProcessorHooks | None = None,
        run_id: str | None = None,
    ) -> MemoryGovernanceRunResult:
        plan = await self.plan_once(
            policy, scope, now=now, checkpoint=checkpoint, run_id=run_id
        )
        return await self.execute(plan, evaluator=evaluator, hooks=hooks)

    async def restore(
        self,
        scope: MemoryScope,
        archived_memory_id: str,
        *,
        target_state: MemoryState = MemoryState.CANDIDATE,
        now: datetime | None = None,
        evaluator: ProposalEvaluator | None = None,
        hooks: ProcessorHooks | None = None,
        run_id: str | None = None,
    ) -> MemoryGovernanceRunResult:
        plan = await self.plan_restore(
            scope,
            archived_memory_id,
            target_state=target_state,
            now=now,
            run_id=run_id,
        )
        return await self.execute(plan, evaluator=evaluator, hooks=hooks)

    async def _read_active(self, scope: MemoryScope) -> list[MemoryRecord]:
        cursor = ""
        records: list[MemoryRecord] = []
        while True:
            remaining = self.config.max_records - len(records)
            if remaining <= 0:
                raise MemoryGovernanceReadLimitError(
                    f"active personal memories exceed max_records {self.config.max_records}"
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
                raise MemoryGovernanceReadLimitError(
                    f"active personal memories exceed max_records {self.config.max_records}"
                )

    def _bind_checkpoint(
        self,
        policy: MemoryGovernancePolicy,
        checkpoint: MemoryGovernanceCheckpoint | None,
    ) -> MemoryGovernanceCheckpoint:
        bound = checkpoint or MemoryGovernanceCheckpoint()
        if bound.schema_version != 1:
            raise MemoryGovernancePlanningError(
                "unsupported governance checkpoint schema"
            )
        if bound.policy and bound.policy != policy.name:
            raise MemoryGovernancePlanningError("checkpoint belongs to another policy")
        if bound.policy_version and bound.policy_version != policy.version:
            raise MemoryGovernancePlanningError(
                "checkpoint policy version does not match"
            )
        if bound.config_fingerprint and (
            bound.config_fingerprint != self.config.fingerprint
        ):
            raise MemoryGovernancePlanningError(
                "checkpoint runner config does not match"
            )
        return bound

    def _bind_actions(
        self,
        policy: MemoryGovernancePolicy,
        scope: MemoryScope,
        records: Sequence[MemoryRecord],
        analysis: MemoryGovernanceAnalysis,
        input_fingerprint: str,
        evaluated_at: datetime,
    ) -> list[MemoryGovernanceAction]:
        known = {record.memory_id: record for record in records}
        claimed: set[str] = set()
        actions: list[MemoryGovernanceAction] = []
        for decision in analysis.decisions:
            if decision.confidence < self.config.minimum_confidence:
                continue
            if decision.source_memory_id not in known:
                raise MemoryGovernancePlanningError(
                    f"decision references unknown memory: {decision.source_memory_id}"
                )
            if decision.source_memory_id in claimed:
                raise MemoryGovernancePlanningError(
                    f"multiple decisions target memory: {decision.source_memory_id}"
                )
            source = known[decision.source_memory_id]
            target_importance = (
                source.importance
                if decision.target_importance is None
                else decision.target_importance
            )
            if decision.operation == MemoryGovernanceOperation.REINFORCE and (
                target_importance <= source.importance
            ):
                raise MemoryGovernancePlanningError("reinforce must raise importance")
            if decision.operation == MemoryGovernanceOperation.DECAY and (
                target_importance >= source.importance
            ):
                raise MemoryGovernancePlanningError("decay must lower importance")
            target_state = (
                MemoryState.EXPIRED
                if decision.operation == MemoryGovernanceOperation.ARCHIVE
                else source.state
            )
            decision_id = "gov_" + _fingerprint(
                {
                    "operation": decision.operation,
                    "scope_key": scope.scope_key,
                    "policy": f"{policy.name}:{policy.version}",
                    "source": [source.memory_id, source.version],
                    "target_importance": target_importance,
                    "target_state": target_state.value,
                    "reason": decision.reason,
                }
            )
            proposal = _replacement_proposal(
                scope,
                source,
                operation=decision.operation,
                decision_id=decision_id,
                reason=decision.reason,
                confidence=decision.confidence,
                target_importance=target_importance,
                target_state=target_state,
                policy=policy.name,
                policy_version=policy.version,
                config_fingerprint=self.config.fingerprint,
                input_fingerprint=input_fingerprint,
                evaluated_at=evaluated_at,
            )
            actions.append(
                MemoryGovernanceAction(
                    decision_id=decision_id,
                    operation=decision.operation,
                    reason=decision.reason,
                    confidence=decision.confidence,
                    source=_source_snapshot(source),
                    proposal=proposal,
                )
            )
            claimed.add(source.memory_id)
        return actions

    def _validate_plan(self, plan: MemoryGovernancePlan) -> None:
        if plan.schema_version != 1:
            raise MemoryGovernancePlanningError("unsupported governance plan schema")
        if plan.config_fingerprint != self.config.fingerprint:
            raise MemoryGovernancePlanningError(
                "plan config does not match this runner"
            )
        if plan.next_checkpoint is not None:
            checkpoint = plan.next_checkpoint
            if checkpoint.config_fingerprint != self.config.fingerprint:
                raise MemoryGovernancePlanningError("checkpoint config does not match")
            if checkpoint.policy != plan.policy or (
                checkpoint.policy_version != plan.policy_version
            ):
                raise MemoryGovernancePlanningError("checkpoint policy does not match")
        expected = "gpl_" + _fingerprint(_plan_identity_payload(plan))
        if plan.plan_id != expected:
            raise MemoryGovernancePlanningError("plan content does not match plan_id")

    async def _execute_action(
        self,
        plan: MemoryGovernancePlan,
        action: MemoryGovernanceAction,
        *,
        evaluator: ProposalEvaluator | None,
        hooks: ProcessorHooks | None,
    ) -> tuple[MemoryGovernanceActionResult, list[ProcessingError]]:
        source = action.source
        errors: list[ProcessingError] = []
        current = await self._store.get(plan.scope, source.memory_id)
        already_applied = False
        if current is None:
            errors.append(
                _error("source_validate", "KeyError", "source is missing", plan.policy)
            )
        elif action.transition_source and (
            current.state is MemoryState.SUPERSEDED
            and current.version == source.version + 1
        ):
            already_applied = True
        elif current.state != source.state or current.version != source.version:
            errors.append(
                _error(
                    "source_validate",
                    "MemoryStateConflictError",
                    (
                        f"source changed from {source.state.value}/v{source.version} "
                        f"to {current.state.value}/v{current.version}"
                    ),
                    plan.policy,
                )
            )
        elif memory_index_fingerprint(current) != source.fingerprint:
            errors.append(
                _error(
                    "source_validate",
                    "MemoryFingerprintConflict",
                    "source memory fingerprint changed",
                    plan.policy,
                )
            )
        if errors:
            return (
                MemoryGovernanceActionResult(
                    decision_id=action.decision_id,
                    operation=action.operation,
                    replacement_write=WriteResult(
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
            governance = write.record.metadata.get("governance", {})
            if not isinstance(governance, dict) or (
                governance.get("decision_id") != action.decision_id
            ):
                write_ok = False
                errors.append(
                    _error(
                        "replacement_write",
                        "GovernanceReplayConflict",
                        "idempotent replacement does not match the planned decision",
                        plan.policy,
                    )
                )
        if not write_ok:
            if not errors:
                errors.append(
                    _error(
                        "replacement_write",
                        "ReplacementWriteFailed",
                        write.message
                        or write.error_code
                        or "replacement was not persisted",
                        plan.policy,
                    )
                )
            return (
                MemoryGovernanceActionResult(
                    decision_id=action.decision_id,
                    operation=action.operation,
                    replacement_write=write,
                ),
                errors,
            )

        if not action.transition_source:
            transition = MemoryGovernanceTransitionResult(
                memory_id=source.memory_id,
                status="not_required",
                from_state=source.state,
                record=current,
            )
        elif already_applied:
            transition = MemoryGovernanceTransitionResult(
                memory_id=source.memory_id,
                status="already_applied",
                from_state=source.state,
                record=current,
            )
        else:
            try:
                transitioned = await self._store.transition(
                    plan.scope,
                    source.memory_id,
                    MemoryState.SUPERSEDED,
                    expected_state=source.state,
                )
                transition = MemoryGovernanceTransitionResult(
                    memory_id=source.memory_id,
                    status="transitioned",
                    from_state=source.state,
                    record=transitioned,
                )
            except (KeyError, MemoryStateConflictError) as exc:
                transition = MemoryGovernanceTransitionResult(
                    memory_id=source.memory_id,
                    status="failed",
                    from_state=source.state,
                    error=str(exc),
                )
                errors.append(
                    _error(
                        "source_transition", type(exc).__name__, str(exc), plan.policy
                    )
                )
        return (
            MemoryGovernanceActionResult(
                decision_id=action.decision_id,
                operation=action.operation,
                replacement_write=write,
                transition=transition,
                complete=not errors and transition.status != "failed",
            ),
            errors,
        )


def _replacement_proposal(
    scope: MemoryScope,
    source: MemoryRecord,
    *,
    operation: str,
    decision_id: str,
    reason: str,
    confidence: float,
    target_importance: float,
    target_state: MemoryState,
    policy: str,
    policy_version: str,
    config_fingerprint: str,
    input_fingerprint: str,
    evaluated_at: datetime,
) -> MemoryProposal:
    metadata = dict(source.metadata)
    metadata["governance"] = {
        "decision_id": decision_id,
        "operation": operation,
        "reason": reason,
        "source_memory_id": source.memory_id,
        "source_version": source.version,
        "source_state": source.state.value,
        "source_fingerprint": memory_index_fingerprint(source),
        "policy": policy,
        "policy_version": policy_version,
        "config_fingerprint": config_fingerprint,
        "input_fingerprint": input_fingerprint,
        "evaluated_at": evaluated_at.isoformat(),
        "previous_importance": source.importance,
        "target_importance": target_importance,
        "target_state": target_state.value,
        "observed_evidence_count": len(_evidence_ids(source)),
    }
    chain = list(
        dict.fromkeys(
            [
                *(str(item) for item in source.metadata.get("derived_chain", [])),
                f"memory:{source.memory_id}",
            ]
        )
    )
    tags = [
        tag
        for tag in source.tags
        if not tag.startswith("governance:")
        and tag not in {"governance-archive", "governance-restored"}
    ]
    tags.extend(["governed", f"governance:{operation}"])
    if operation == MemoryGovernanceOperation.ARCHIVE:
        tags.append("governance-archive")
    if operation == MemoryGovernanceOperation.RESTORE:
        tags.append("governance-restored")
    return MemoryProposal(
        scope=scope,
        content=source.content,
        kind=source.kind,
        actor=source.actor,
        authority=source.authority,
        confidence=confidence,
        proposed_state=target_state,
        tags=list(dict.fromkeys(tags)),
        importance=target_importance,
        idempotency_key=f"governance:{decision_id}",
        source_event_id=source.source_event_id,
        source_message_id=source.source_message_id,
        processor=policy,
        processor_version=policy_version,
        derived_chain=chain,
        # Preserve claim chronology.  Governance time lives in provenance and must
        # not make an old fact appear newly learned to temporal queries.
        created_at=source.created_at,
        metadata=metadata,
    )


def _source_snapshot(record: MemoryRecord) -> MemoryGovernanceSourceSnapshot:
    return MemoryGovernanceSourceSnapshot(
        memory_id=record.memory_id,
        state=record.state,
        version=record.version,
        fingerprint=memory_index_fingerprint(record),
    )


def _bind_plan_id(plan: MemoryGovernancePlan) -> MemoryGovernancePlan:
    return plan.model_copy(
        update={"plan_id": "gpl_" + _fingerprint(_plan_identity_payload(plan))}
    )


def _plan_identity_payload(plan: MemoryGovernancePlan) -> dict[str, Any]:
    payload = plan.model_dump(mode="json")
    payload.pop("plan_id", None)
    return payload


def _records_fingerprint(records: Sequence[MemoryRecord]) -> str:
    return _fingerprint(
        [
            {
                "memory_id": record.memory_id,
                "version": record.version,
                "state": record.state.value,
                "fingerprint": memory_index_fingerprint(record),
            }
            for record in sorted(records, key=lambda item: item.memory_id)
        ]
    )


def _evidence_ids(record: MemoryRecord) -> set[str]:
    identities: set[str] = set()
    evidence = record.metadata.get("evidence", [])
    if isinstance(evidence, list):
        for item in evidence:
            if isinstance(item, dict):
                identity = str(item.get("evidence_id", "") or "").strip()
                if identity:
                    identities.add(identity)
    fallback = record.source_message_id or record.source_event_id
    if fallback:
        identities.add(fallback)
    return identities


def _latest_evidence_time(record: MemoryRecord) -> datetime | None:
    times: list[datetime] = []
    evidence = record.metadata.get("evidence", [])
    if isinstance(evidence, list):
        for item in evidence:
            if isinstance(item, dict):
                parsed = _parse_time(item.get("at"))
                if parsed is not None:
                    times.append(parsed)
    return max(times) if times else None


def _metadata_text(record: MemoryRecord, key: str) -> str:
    return str(record.metadata.get(key, "") or "").strip().lower()


def _metadata_time(record: MemoryRecord, key: str) -> datetime | None:
    return _parse_time(record.metadata.get(key))


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else None
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else None


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("governance time must include a timezone")
    return value.astimezone(UTC)


def _safe_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _require_identity(policy: MemoryGovernancePolicy) -> None:
    if (
        not str(getattr(policy, "name", "") or "").strip()
        or not str(getattr(policy, "version", "") or "").strip()
    ):
        raise ValueError("memory governance policy requires non-empty name and version")


def _error(stage: str, error_type: str, message: str, policy: str) -> ProcessingError:
    return ProcessingError(
        stage=stage, error_type=error_type, message=message, processor=policy
    )


def _fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
