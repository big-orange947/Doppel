"""Periodic history aggregation without giving online processors store access.

The framework executes one task run and returns a checkpoint that is safe to
commit. Scheduling and checkpoint persistence deliberately belong to the host.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from doppel_memory.models import (
    ChatMessage,
    MemoryFilter,
    MemoryIsolationError,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    RecallResult,
    WriteStatus,
)
from doppel_memory.processing import (
    MemoryProposal,
    ProcessingError,
    ProcessorHooks,
    ProposalBatchResult,
    ProposalEvaluator,
    ProposalWriter,
)
from doppel_memory.retriever import Retriever
from doppel_memory.store import MemoryStore


class HistoryWindow(BaseModel):
    """Closed time window assigned to one deterministic task run."""

    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def _normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("history window timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_order(self) -> HistoryWindow:
        if self.end < self.start:
            raise ValueError("history window end must not precede start")
        return self


class BatchCheckpoint(BaseModel):
    """Opaque host-owned progress state passed between runs."""

    cursor: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class HistoryPage(BaseModel):
    """One exact-scope page of normalized historical IM events."""

    messages: list[ChatMessage] = Field(default_factory=list)
    next_cursor: str = ""
    has_more: bool = False


@runtime_checkable
class ScopedHistoryReader(Protocol):
    """Read-only, exact-scope event history made available to a batch task."""

    @property
    def scope(self) -> MemoryScope: ...

    async def read(
        self,
        *,
        cursor: str = "",
        limit: int = 500,
        actors: set[str] | None = None,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
    ) -> HistoryPage: ...


@runtime_checkable
class ScopedMemoryReader(Protocol):
    """Read-only memory view restricted to a fixed set of exact scopes."""

    @property
    def scopes(self) -> tuple[MemoryScope, ...]: ...

    async def recall(
        self,
        query: str,
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> list[RecallResult]: ...

    async def get(self, scope: MemoryScope, memory_id: str) -> MemoryRecord | None: ...


@dataclass(frozen=True)
class BatchTaskContext:
    """Capabilities and run identity visible to a periodic task."""

    run_id: str
    scope: MemoryScope
    window: HistoryWindow
    checkpoint: BatchCheckpoint
    history: ScopedHistoryReader
    memories: ScopedMemoryReader


class BatchProposalPlan(BaseModel):
    """Pure task output: proposed memories and tentative next progress."""

    proposals: list[MemoryProposal] = Field(default_factory=list)
    next_checkpoint: BatchCheckpoint | None = None


@runtime_checkable
class MemoryBatchTask(Protocol):
    """Aggregates read-only history into proposals; never writes a store."""

    name: str
    version: str

    async def propose(self, context: BatchTaskContext) -> BatchProposalPlan: ...


@runtime_checkable
class BatchProposalPolicy(Protocol):
    """Accept, reject, or replace one proposal with access to run context."""

    async def evaluate(
        self, proposal: MemoryProposal, context: BatchTaskContext
    ) -> MemoryProposal | None: ...


class BatchRunResult(ProposalBatchResult):
    """Outcome of one task invocation and its safely committable checkpoint."""

    task: str
    task_version: str = ""
    run_id: str
    scope: MemoryScope
    window: HistoryWindow
    committable_checkpoint: BatchCheckpoint | None = None


class StoreHistoryReader:
    """Default event-history view backed by stable ``MemoryStore.scan``."""

    def __init__(self, store: MemoryStore, scope: MemoryScope) -> None:
        if not store.capabilities.pagination:
            raise NotImplementedError(
                "history reading requires a backend with pagination capability"
            )
        self._store = store
        self._scope = scope

    @property
    def scope(self) -> MemoryScope:
        return self._scope

    async def read(
        self,
        *,
        cursor: str = "",
        limit: int = 500,
        actors: set[str] | None = None,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
    ) -> HistoryPage:
        page = await self._store.scan(
            self._scope,
            filters=MemoryFilter(
                kinds={MemoryKind.EVENT},
                actors=actors,
                time_from=time_from,
                time_to=time_to,
            ),
            cursor=cursor,
            limit=limit,
        )
        return HistoryPage(
            messages=[_record_to_message(record) for record in page.records],
            next_cursor=page.next_cursor,
            has_more=page.has_more,
        )


class StoreMemoryReader:
    """Default read-only memory view with immutable scope authorization."""

    def __init__(
        self,
        store: MemoryStore,
        scopes: Sequence[MemoryScope],
        *,
        retriever: Retriever | None = None,
    ) -> None:
        if not scopes:
            raise MemoryIsolationError(
                "memory reader requires at least one exact scope"
            )
        self._store = store
        self._scopes = tuple({scope.scope_key: scope for scope in scopes}.values())
        self._allowed_keys = {scope.scope_key for scope in self._scopes}
        self._retriever = retriever or Retriever(store)

    @property
    def scopes(self) -> tuple[MemoryScope, ...]:
        return self._scopes

    async def recall(
        self,
        query: str,
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> list[RecallResult]:
        return await self._retriever.recall(
            query, list(self._scopes), filters=filters, limit=limit
        )

    async def get(self, scope: MemoryScope, memory_id: str) -> MemoryRecord | None:
        if scope.scope_key not in self._allowed_keys:
            raise MemoryIsolationError("memory scope is not authorized for this task")
        return await self._store.get(scope, memory_id)


class _ContextPolicyEvaluator:
    def __init__(self, policy: BatchProposalPolicy, context: BatchTaskContext) -> None:
        self._policy = policy
        self._context = context

    async def evaluate(self, proposal: MemoryProposal) -> MemoryProposal | None:
        return await self._policy.evaluate(proposal, self._context)


class BatchTaskRunner:
    """Execute one periodic task run through the common proposal writer."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store
        self._writer = ProposalWriter(store)

    async def run_once(
        self,
        task: MemoryBatchTask,
        scope: MemoryScope,
        window: HistoryWindow,
        *,
        checkpoint: BatchCheckpoint | None = None,
        history: ScopedHistoryReader | None = None,
        memories: ScopedMemoryReader | None = None,
        read_scopes: Sequence[MemoryScope] | None = None,
        allowed_scopes: Sequence[MemoryScope] | None = None,
        policy: BatchProposalPolicy | None = None,
        hooks: ProcessorHooks | None = None,
        run_id: str | None = None,
    ) -> BatchRunResult:
        task_name = str(getattr(task, "name", "") or "")
        task_version = str(getattr(task, "version", "") or "")
        if not task_name:
            raise ValueError("batch task name is required")

        bound_history = history or StoreHistoryReader(self._store, scope)
        if bound_history.scope.scope_key != scope.scope_key:
            raise MemoryIsolationError("history reader scope does not match task scope")
        write_scopes = _unique_scopes([scope, *(allowed_scopes or ())])
        bound_memories = memories or StoreMemoryReader(
            self._store, read_scopes or write_scopes
        )
        context = BatchTaskContext(
            run_id=run_id or str(uuid4()),
            scope=scope,
            window=window,
            checkpoint=checkpoint or BatchCheckpoint(),
            history=bound_history,
            memories=bound_memories,
        )
        bound_hooks = hooks or ProcessorHooks()
        result = BatchRunResult(
            task=task_name,
            task_version=task_version,
            run_id=context.run_id,
            scope=scope,
            window=window,
        )

        try:
            raw_plan = await task.propose(context)
            if isinstance(raw_plan, BatchProposalPlan):
                raw_plan = raw_plan.model_dump(warnings=False)
            plan = BatchProposalPlan.model_validate(raw_plan)
        except Exception as exc:  # noqa: BLE001 - task/plugin boundary
            await _append_batch_error(
                result, bound_hooks, "batch_propose", exc, processor=task_name
            )
            return result

        evaluator: ProposalEvaluator | None = None
        if policy is not None:
            evaluator = _ContextPolicyEvaluator(policy, context)
        batch = await self._writer.write_batch(
            plan.proposals,
            allowed_scopes=write_scopes,
            evaluator=evaluator,
            hooks=bound_hooks,
        )
        result.proposals = batch.proposals
        result.write_results = batch.write_results
        result.errors.extend(batch.errors)
        if not result.errors and all(
            item.status is not WriteStatus.FAILED for item in result.write_results
        ):
            result.committable_checkpoint = plan.next_checkpoint
        return result


def _record_to_message(record: MemoryRecord) -> ChatMessage:
    metadata = record.metadata
    return ChatMessage(
        actor=record.actor,
        text=record.content,
        at=record.created_at,
        event_id=record.source_event_id,
        message_id=record.source_message_id,
        sender_id=metadata.get("sender_id", ""),
        message_type=metadata.get("message_type", "message"),
        reply_to_id=metadata.get("reply_to_id", ""),
        quoted_message_id=metadata.get("quoted_message_id", ""),
        thread_id=metadata.get("thread_id", ""),
        thread_root_id=metadata.get("thread_root_id", ""),
        attachments=metadata.get("attachments", []),
        raw=metadata.get("raw", {}),
    )


def _unique_scopes(scopes: Sequence[MemoryScope]) -> tuple[MemoryScope, ...]:
    return tuple({scope.scope_key: scope for scope in scopes}.values())


async def _append_batch_error(
    result: ProposalBatchResult,
    hooks: ProcessorHooks,
    stage: str,
    error: Exception,
    *,
    processor: str,
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
        await hooks.on_error(stage, error, processor=processor)
    except Exception as hook_error:  # noqa: BLE001 - terminal hook boundary
        result.errors.append(
            ProcessingError(
                stage="on_error",
                error_type=type(hook_error).__name__,
                message=str(hook_error),
                processor=processor,
            )
        )
