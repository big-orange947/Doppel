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
    """Host-owned progress state bound to one task and checkpoint schema."""

    cursor: str = ""
    task_name: str = ""
    task_version: str = ""
    schema_version: int = Field(default=1, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("task_name", "task_version", mode="before")
    @classmethod
    def _normalize_identity(cls, value: Any) -> str:
        return str(value or "").strip()


class BatchReadLimits(BaseModel):
    """Hard per-run limits applied around any history reader implementation."""

    max_pages: int = Field(default=100, ge=1)
    max_messages: int = Field(default=50_000, ge=1)
    max_page_size: int = Field(default=2_000, ge=1)


class BatchReadLimitError(RuntimeError):
    """A batch task exhausted its configured history-reading budget."""


class HistoryReaderContractError(RuntimeError):
    """A custom history reader violated pagination protocol invariants."""


class HistoryPage(BaseModel):
    """One exact-scope page of normalized historical IM events."""

    messages: list[ChatMessage] = Field(default_factory=list)
    next_cursor: str = ""
    has_more: bool = False


@runtime_checkable
class ScopedHistoryReader(Protocol):
    """Read-only, exact-scope, stable oldest-first history for a batch task."""

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


class GuardedHistoryReader:
    """Validate pages and enforce a finite read budget around any reader."""

    def __init__(
        self,
        reader: ScopedHistoryReader,
        limits: BatchReadLimits | None = None,
    ) -> None:
        self._reader = reader
        self._limits = limits or BatchReadLimits()
        self._pages_read = 0
        self._messages_read = 0

    @property
    def scope(self) -> MemoryScope:
        return self._reader.scope

    @property
    def limits(self) -> BatchReadLimits:
        return self._limits

    @property
    def pages_read(self) -> int:
        return self._pages_read

    @property
    def messages_read(self) -> int:
        return self._messages_read

    async def read(
        self,
        *,
        cursor: str = "",
        limit: int = 500,
        actors: set[str] | None = None,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
    ) -> HistoryPage:
        if limit > self._limits.max_page_size:
            raise BatchReadLimitError(
                f"history page size {limit} exceeds max_page_size "
                f"{self._limits.max_page_size}"
            )
        if self._pages_read >= self._limits.max_pages:
            raise BatchReadLimitError(
                f"history reads exceed max_pages {self._limits.max_pages}"
            )
        self._pages_read += 1
        raw_page = await self._reader.read(
            cursor=cursor,
            limit=limit,
            actors=actors,
            time_from=time_from,
            time_to=time_to,
        )
        if isinstance(raw_page, HistoryPage):
            raw_page = raw_page.model_dump(warnings=False)
        try:
            page = HistoryPage.model_validate(raw_page)
        except Exception as exc:
            raise HistoryReaderContractError(
                f"history reader returned an invalid page: {exc}"
            ) from exc
        message_count = len(page.messages)
        self._messages_read += message_count
        if limit >= 0 and message_count > limit:
            raise HistoryReaderContractError(
                f"history reader returned {message_count} messages for limit={limit}"
            )
        if self._messages_read > self._limits.max_messages:
            raise BatchReadLimitError(
                f"history reads exceed max_messages {self._limits.max_messages}"
            )
        if page.messages and not page.next_cursor:
            raise HistoryReaderContractError(
                "non-empty history page must return a durable next_cursor"
            )
        if page.messages and page.next_cursor == cursor:
            raise HistoryReaderContractError(
                "history cursor must advance for every non-empty page"
            )
        if page.has_more and not page.messages:
            raise HistoryReaderContractError(
                "history page cannot set has_more=True without messages"
            )
        return page


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
    checkpoint_schema_version: int = 1
    history_pages_read: int = 0
    history_messages_read: int = 0
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
        read_limits: BatchReadLimits | None = None,
        run_id: str | None = None,
    ) -> BatchRunResult:
        task_name = str(getattr(task, "name", "") or "").strip()
        task_version = str(getattr(task, "version", "") or "").strip()
        if not task_name:
            raise ValueError("batch task name is required")
        if not task_version:
            raise ValueError("batch task version is required")
        checkpoint_schema_version = _task_checkpoint_schema_version(task)

        bound_history = history or StoreHistoryReader(self._store, scope)
        if bound_history.scope.scope_key != scope.scope_key:
            raise MemoryIsolationError("history reader scope does not match task scope")
        guarded_history = GuardedHistoryReader(bound_history, read_limits)
        write_scopes = _unique_scopes([scope, *(allowed_scopes or ())])
        bound_memories = memories or StoreMemoryReader(
            self._store, read_scopes or write_scopes
        )
        bound_checkpoint = _bind_checkpoint(
            checkpoint or BatchCheckpoint(schema_version=checkpoint_schema_version),
            task_name=task_name,
            task_version=task_version,
            schema_version=checkpoint_schema_version,
        )
        context = BatchTaskContext(
            run_id=run_id or str(uuid4()),
            scope=scope,
            window=window,
            checkpoint=bound_checkpoint,
            history=guarded_history,
            memories=bound_memories,
        )
        bound_hooks = hooks or ProcessorHooks()
        result = BatchRunResult(
            task=task_name,
            task_version=task_version,
            run_id=context.run_id,
            scope=scope,
            window=window,
            checkpoint_schema_version=checkpoint_schema_version,
        )

        try:
            raw_plan = await task.propose(context)
            if isinstance(raw_plan, BatchProposalPlan):
                raw_plan = raw_plan.model_dump(warnings=False)
            plan = BatchProposalPlan.model_validate(raw_plan)
        except Exception as exc:  # noqa: BLE001 - task/plugin boundary
            stage = (
                "history_read"
                if isinstance(exc, (BatchReadLimitError, HistoryReaderContractError))
                else "batch_propose"
            )
            await _append_batch_error(
                result, bound_hooks, stage, exc, processor=task_name
            )
            _copy_read_metrics(result, guarded_history)
            return result

        try:
            next_checkpoint = (
                _bind_checkpoint(
                    plan.next_checkpoint,
                    task_name=task_name,
                    task_version=task_version,
                    schema_version=checkpoint_schema_version,
                )
                if plan.next_checkpoint is not None
                else None
            )
        except Exception as exc:  # noqa: BLE001 - task/plugin boundary
            await _append_batch_error(
                result, bound_hooks, "checkpoint", exc, processor=task_name
            )
            _copy_read_metrics(result, guarded_history)
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
        _copy_read_metrics(result, guarded_history)
        if not result.errors and all(
            item.status is not WriteStatus.FAILED for item in result.write_results
        ):
            result.committable_checkpoint = next_checkpoint
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
        parts=metadata.get("parts", []),
    )


def _unique_scopes(scopes: Sequence[MemoryScope]) -> tuple[MemoryScope, ...]:
    return tuple({scope.scope_key: scope for scope in scopes}.values())


def _task_checkpoint_schema_version(task: MemoryBatchTask) -> int:
    raw_version = getattr(task, "checkpoint_schema_version", 1)
    if isinstance(raw_version, bool) or not isinstance(raw_version, int):
        raise TypeError("checkpoint_schema_version must be a positive integer")
    if raw_version < 1:
        raise ValueError("checkpoint_schema_version must be a positive integer")
    return raw_version


def _bind_checkpoint(
    checkpoint: BatchCheckpoint,
    *,
    task_name: str,
    task_version: str,
    schema_version: int,
) -> BatchCheckpoint:
    if checkpoint.task_name and checkpoint.task_name != task_name:
        raise ValueError(
            f"checkpoint belongs to task {checkpoint.task_name!r}, not {task_name!r}"
        )
    if checkpoint.task_version and checkpoint.task_version != task_version:
        raise ValueError(
            "checkpoint task_version does not match; migrate or reset the checkpoint"
        )
    if checkpoint.schema_version != schema_version:
        raise ValueError(
            "checkpoint schema_version does not match; migrate or reset the checkpoint"
        )
    return checkpoint.model_copy(
        update={"task_name": task_name, "task_version": task_version},
        deep=True,
    )


def _copy_read_metrics(result: BatchRunResult, history: GuardedHistoryReader) -> None:
    result.history_pages_read = history.pages_read
    result.history_messages_read = history.messages_read


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
