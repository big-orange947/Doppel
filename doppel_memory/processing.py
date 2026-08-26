"""Backend-neutral proposal processing pipeline.

Processors propose memories; policies decide whether and how they are persisted;
the pipeline is the only component in this module that writes to a store.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator

from doppel_memory.models import (
    ChatMessage,
    FactAuthority,
    MemoryIsolationError,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    WriteResult,
    WriteStatus,
    utc_now,
)
from doppel_memory.store import MemoryStore


class MemoryProposal(BaseModel):
    """A backend-neutral request to persist one derived memory."""

    scope: MemoryScope
    content: str = ""
    kind: str = MemoryKind.FACT
    actor: str = ""
    authority: FactAuthority = FactAuthority.DERIVED_SUMMARY
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    proposed_state: MemoryState = MemoryState.CANDIDATE
    tags: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    idempotency_key: str = ""
    source_event_id: str = ""
    source_message_id: str = ""
    processor: str
    processor_version: str = ""
    derived_chain: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind", mode="before")
    @classmethod
    def _normalize_kind(cls, value: Any) -> str:
        return MemoryKind.normalize(value)

    @field_validator(
        "content",
        "actor",
        "idempotency_key",
        "source_event_id",
        "source_message_id",
        "processor",
        "processor_version",
        mode="before",
    )
    @classmethod
    def _normalize_strings(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("processor")
    @classmethod
    def _require_processor(cls, value: str) -> str:
        if not value:
            raise ValueError("processor is required")
        return value

    @field_validator("created_at")
    @classmethod
    def _normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        return value.astimezone(UTC)

    def to_record(self) -> MemoryRecord:
        """Convert the proposal without making a persistence decision."""

        metadata = dict(self.metadata)
        metadata.setdefault("confidence", self.confidence)
        metadata.setdefault("processor_version", self.processor_version)
        metadata.setdefault("derived_chain", list(self.derived_chain))
        return MemoryRecord(
            kind=self.kind,
            scope=self.scope,
            content=self.content,
            actor=self.actor,
            authority=self.authority,
            state=self.proposed_state,
            tags=list(self.tags),
            importance=self.importance,
            idempotency_key=self.idempotency_key,
            source_event_id=self.source_event_id,
            source_message_id=self.source_message_id,
            extractor=self.processor,
            created_at=self.created_at,
            updated_at=self.created_at,
            metadata=metadata,
        )


class ProcessingError(BaseModel):
    """A serializable processor, policy, hook, validation, or store failure."""

    stage: str
    error_type: str
    message: str
    processor: str = ""


class ProposalBatchResult(BaseModel):
    """One proposal write batch; proposal and result lists have matching indices."""

    proposals: list[MemoryProposal] = Field(default_factory=list)
    write_results: list[WriteResult] = Field(default_factory=list)
    errors: list[ProcessingError] = Field(default_factory=list)

    @property
    def accepted_count(self) -> int:
        return sum(result.accepted for result in self.write_results)

    @property
    def failed_count(self) -> int:
        return sum(result.status is WriteStatus.FAILED for result in self.write_results)


class ProcessingResult(ProposalBatchResult):
    """One online processor run."""

    scope: MemoryScope
    message: ChatMessage


@runtime_checkable
class MemoryProcessor(Protocol):
    """Proposes memories from one normalized IM event; never writes a store."""

    name: str
    version: str

    async def process(
        self, scope: MemoryScope, message: ChatMessage
    ) -> Sequence[MemoryProposal]: ...


@runtime_checkable
class ProposalPolicy(Protocol):
    """Accept, reject, or replace a proposal before persistence."""

    async def evaluate(
        self, proposal: MemoryProposal, message: ChatMessage
    ) -> MemoryProposal | None: ...


@runtime_checkable
class ProposalEvaluator(Protocol):
    """A source-bound policy used by the common proposal writer."""

    async def evaluate(self, proposal: MemoryProposal) -> MemoryProposal | None: ...


class PassThroughProposalPolicy:
    """Default policy: retain the processor's proposed state and contents."""

    async def evaluate(
        self, proposal: MemoryProposal, message: ChatMessage
    ) -> MemoryProposal:
        return proposal


class ProcessorHooks:
    """Finite lifecycle hooks; subclass only the callbacks you need."""

    async def before_process(self, scope: MemoryScope, message: ChatMessage) -> None:
        pass

    async def after_proposal(
        self, proposal: MemoryProposal, message: ChatMessage | None
    ) -> None:
        pass

    async def before_write(
        self, proposal: MemoryProposal, record: MemoryRecord
    ) -> None:
        pass

    async def after_write(self, proposal: MemoryProposal, result: WriteResult) -> None:
        pass

    async def on_error(
        self,
        stage: str,
        error: Exception,
        *,
        processor: str = "",
        proposal: MemoryProposal | None = None,
    ) -> None:
        pass


class EventProcessor:
    """Deterministically maps a normalized message to one confirmed event."""

    name = "event"
    version = "1"

    async def process(
        self, scope: MemoryScope, message: ChatMessage
    ) -> Sequence[MemoryProposal]:
        identity = message.identity_key
        return [
            MemoryProposal(
                scope=scope,
                content=message.text,
                kind=MemoryKind.EVENT,
                actor=message.actor,
                authority=message.fact_authority,
                confidence=1.0,
                proposed_state=MemoryState.CONFIRMED,
                idempotency_key=f"event:{identity}" if identity else "",
                source_event_id=message.event_id,
                source_message_id=message.message_id,
                processor=self.name,
                processor_version=self.version,
                created_at=message.at,
                metadata={
                    "message_type": message.message_type,
                    "sender_id": message.sender_id,
                    "reply_to_id": message.reply_to_id,
                    "quoted_message_id": message.quoted_message_id,
                    "thread_id": message.thread_id,
                    "thread_root_id": message.thread_root_id,
                    "attachments": message.attachments,
                    "raw": message.raw,
                },
            )
        ]


class PassThroughProposalEvaluator:
    async def evaluate(self, proposal: MemoryProposal) -> MemoryProposal:
        return proposal


class _MessagePolicyEvaluator:
    def __init__(self, policy: ProposalPolicy, message: ChatMessage) -> None:
        self._policy = policy
        self._message = message

    async def evaluate(self, proposal: MemoryProposal) -> MemoryProposal | None:
        return await self._policy.evaluate(proposal, self._message)


class ProposalWriter:
    """Validate, authorize, deduplicate, and persist a proposal batch."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def write_batch(
        self,
        proposals: Sequence[MemoryProposal],
        *,
        allowed_scopes: Sequence[MemoryScope],
        evaluator: ProposalEvaluator | None = None,
        hooks: ProcessorHooks | None = None,
        message: ChatMessage | None = None,
    ) -> ProposalBatchResult:
        if not allowed_scopes:
            raise MemoryIsolationError("proposal writing requires allowed_scopes")
        result = ProposalBatchResult()
        allowed_keys = {scope.scope_key for scope in allowed_scopes}
        seen_keys: set[tuple[str, str]] = set()
        bound_evaluator = evaluator or PassThroughProposalEvaluator()
        bound_hooks = hooks or ProcessorHooks()

        for raw_proposal in proposals:
            processor_name = str(getattr(raw_proposal, "processor", "") or "")
            try:
                proposal = _validated_proposal(raw_proposal)
                processor_name = proposal.processor
            except Exception as exc:  # noqa: BLE001 - plugin boundary
                await _append_error(
                    result, bound_hooks, "validate", exc, processor=processor_name
                )
                continue

            await self._write_one(
                result,
                proposal,
                evaluator=bound_evaluator,
                hooks=bound_hooks,
                message=message,
                allowed_keys=allowed_keys,
                seen_keys=seen_keys,
            )
        return result

    async def _write_one(
        self,
        result: ProposalBatchResult,
        proposal: MemoryProposal,
        *,
        evaluator: ProposalEvaluator,
        hooks: ProcessorHooks,
        message: ChatMessage | None,
        allowed_keys: set[str],
        seen_keys: set[tuple[str, str]],
    ) -> None:
        processor_name = proposal.processor
        try:
            await hooks.after_proposal(proposal, message)
        except Exception as exc:  # noqa: BLE001 - extension boundary
            result.proposals.append(proposal)
            result.write_results.append(
                WriteResult(
                    status=WriteStatus.FAILED,
                    error_code="after_proposal_failed",
                    message=str(exc),
                )
            )
            await _append_error(
                result,
                hooks,
                "after_proposal",
                exc,
                processor=processor_name,
                proposal=proposal,
            )
            return

        try:
            evaluated = await evaluator.evaluate(proposal)
            if evaluated is not None:
                evaluated = _validated_proposal(evaluated)
        except Exception as exc:  # noqa: BLE001 - policy boundary
            result.proposals.append(proposal)
            result.write_results.append(
                WriteResult(
                    status=WriteStatus.FAILED,
                    error_code="proposal_evaluation_failed",
                    message=str(exc),
                )
            )
            await _append_error(
                result,
                hooks,
                "evaluate",
                exc,
                processor=processor_name,
                proposal=proposal,
            )
            return

        if evaluated is None:
            result.proposals.append(proposal)
            result.write_results.append(
                WriteResult(
                    status=WriteStatus.SKIPPED,
                    error_code="policy_rejected",
                    message="proposal rejected by policy",
                )
            )
            return

        proposal = evaluated
        result.proposals.append(proposal)
        if proposal.scope.scope_key not in allowed_keys:
            error = ValueError("proposal target scope is not in allowed_scopes")
            result.write_results.append(
                WriteResult(
                    status=WriteStatus.FAILED,
                    error_code="scope_not_allowed",
                    message=str(error),
                )
            )
            await _append_error(
                result,
                hooks,
                "validate",
                error,
                processor=processor_name,
                proposal=proposal,
            )
            return

        key = (proposal.scope.scope_key, proposal.idempotency_key)
        if proposal.idempotency_key and key in seen_keys:
            result.write_results.append(
                WriteResult(
                    status=WriteStatus.SKIPPED,
                    error_code="duplicate_proposal",
                    message="duplicate idempotency key in one proposal batch",
                )
            )
            return
        if proposal.idempotency_key:
            seen_keys.add(key)

        try:
            record = proposal.to_record()
        except Exception as exc:  # noqa: BLE001 - conversion boundary
            result.write_results.append(
                WriteResult(
                    status=WriteStatus.FAILED,
                    error_code="invalid_proposal",
                    message=str(exc),
                )
            )
            await _append_error(
                result,
                hooks,
                "validate",
                exc,
                processor=processor_name,
                proposal=proposal,
            )
            return

        try:
            await hooks.before_write(proposal, record)
        except Exception as exc:  # noqa: BLE001 - extension boundary
            result.write_results.append(
                WriteResult(
                    status=WriteStatus.FAILED,
                    error_code="before_write_failed",
                    message=str(exc),
                )
            )
            await _append_error(
                result,
                hooks,
                "before_write",
                exc,
                processor=processor_name,
                proposal=proposal,
            )
            return

        try:
            write_result = await self._store.put(
                record, idempotency_key=proposal.idempotency_key or None
            )
        except Exception as exc:  # noqa: BLE001 - store boundary
            result.write_results.append(
                WriteResult(
                    status=WriteStatus.FAILED,
                    error_code="proposal_write_failed",
                    message=str(exc),
                )
            )
            await _append_error(
                result,
                hooks,
                "write",
                exc,
                processor=processor_name,
                proposal=proposal,
            )
            return

        result.write_results.append(write_result)
        try:
            await hooks.after_write(proposal, write_result)
        except Exception as exc:  # noqa: BLE001 - extension boundary
            await _append_error(
                result,
                hooks,
                "after_write",
                exc,
                processor=processor_name,
                proposal=proposal,
            )


class MemoryPipeline:
    """Coordinates processors, one policy, exact-scope guards, hooks, and Store.put."""

    def __init__(
        self,
        store: MemoryStore,
        processors: Sequence[MemoryProcessor],
        *,
        policy: ProposalPolicy | None = None,
        hooks: ProcessorHooks | None = None,
    ) -> None:
        self._writer = ProposalWriter(store)
        self._processors = tuple(processors)
        self._policy = policy or PassThroughProposalPolicy()
        self._hooks = hooks or ProcessorHooks()

    async def run(
        self,
        scope: MemoryScope,
        message: ChatMessage,
        *,
        allowed_scopes: Sequence[MemoryScope] | None = None,
    ) -> ProcessingResult:
        result = ProcessingResult(scope=scope, message=message)

        try:
            await self._hooks.before_process(scope, message)
        except Exception as exc:  # noqa: BLE001 - extension boundary
            await _append_error(result, self._hooks, "before_process", exc)
            return result

        proposals: list[MemoryProposal] = []
        for processor in self._processors:
            processor_name = str(getattr(processor, "name", "") or "")
            try:
                proposals.extend(await processor.process(scope, message))
            except Exception as exc:  # noqa: BLE001 - extension boundary
                await _append_error(
                    result,
                    self._hooks,
                    "process",
                    exc,
                    processor=processor_name,
                )
                continue

        batch = await self._writer.write_batch(
            proposals,
            allowed_scopes=[scope, *(allowed_scopes or ())],
            evaluator=_MessagePolicyEvaluator(self._policy, message),
            hooks=self._hooks,
            message=message,
        )
        result.proposals = batch.proposals
        result.write_results = batch.write_results
        result.errors.extend(batch.errors)
        return result


def _validated_proposal(value: Any) -> MemoryProposal:
    """Revalidate model copies returned across plugin boundaries."""

    if isinstance(value, MemoryProposal):
        value = value.model_dump(warnings=False)
    return MemoryProposal.model_validate(value)


async def _append_error(
    result: ProposalBatchResult,
    hooks: ProcessorHooks,
    stage: str,
    error: Exception,
    *,
    processor: str = "",
    proposal: MemoryProposal | None = None,
) -> None:
    result.errors.append(
        ProcessingError(
            stage=stage,
            error_type=type(error).__name__,
            message=str(error),
            processor=processor,
        )
    )
    try:
        await hooks.on_error(stage, error, processor=processor, proposal=proposal)
    except Exception as hook_error:  # noqa: BLE001 - terminal hook boundary
        result.errors.append(
            ProcessingError(
                stage="on_error",
                error_type=type(hook_error).__name__,
                message=str(hook_error),
                processor=processor,
            )
        )
