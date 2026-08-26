"""Dependency-free conformance probes for third-party batch extensions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from pydantic import BaseModel, Field

from doppel_memory.batch import (
    BatchProposalPlan,
    BatchReadLimitError,
    BatchReadLimits,
    BatchTaskContext,
    GuardedHistoryReader,
    HistoryReaderContractError,
    MemoryBatchTask,
    ScopedHistoryReader,
    _bind_checkpoint,
    _task_checkpoint_schema_version,
)
from doppel_memory.models import MemoryScope
from doppel_memory.processing import MemoryProposal


class ConformanceError(AssertionError):
    """One or more extension contract checks failed."""


class ConformanceIssue(BaseModel):
    stage: str
    error_type: str
    message: str


class HistoryReaderAuditReport(BaseModel):
    scope: MemoryScope
    pages_read: int = 0
    messages_read: int = 0
    final_cursor: str = ""
    issues: list[ConformanceIssue] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def raise_for_errors(self) -> None:
        _raise_issues(self.issues)


class BatchTaskAuditReport(BaseModel):
    task: str
    task_version: str = ""
    checkpoint_schema_version: int = 1
    proposal_count: int = 0
    proposes_checkpoint: bool = False
    history_pages_read: int = 0
    history_messages_read: int = 0
    issues: list[ConformanceIssue] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def raise_for_errors(self) -> None:
        _raise_issues(self.issues)


async def audit_history_reader(
    reader: ScopedHistoryReader,
    *,
    cursor: str = "",
    page_size: int = 2,
    limits: BatchReadLimits | None = None,
    verify_exhausted: bool = True,
) -> HistoryReaderAuditReport:
    """Audit a quiescent reader fixture without requiring pytest.

    ``verify_exhausted`` performs one extra read at the final cursor, so callers
    should seed a data source that is not receiving concurrent events.
    """

    if page_size <= 0:
        raise ValueError("page_size must be positive")
    guarded = GuardedHistoryReader(reader, limits)
    report = HistoryReaderAuditReport(scope=reader.scope, final_cursor=cursor)
    previous_time = None
    seen_identities: set[str] = set()
    try:
        while True:
            page = await guarded.read(cursor=report.final_cursor, limit=page_size)
            for message in page.messages:
                if previous_time is not None and message.at < previous_time:
                    raise HistoryReaderContractError(
                        "history messages must be returned in oldest-first order"
                    )
                previous_time = message.at
                identity = message.identity_key
                if identity and identity in seen_identities:
                    raise HistoryReaderContractError(
                        "history reader returned a duplicate message identity"
                    )
                if identity:
                    seen_identities.add(identity)
            report.final_cursor = page.next_cursor
            if not page.has_more:
                break
        if verify_exhausted and report.final_cursor:
            exhausted = await guarded.read(cursor=report.final_cursor, limit=page_size)
            if exhausted.messages or exhausted.has_more:
                raise HistoryReaderContractError(
                    "final cursor did not produce an exhausted page on a quiescent source"
                )
            if exhausted.next_cursor != report.final_cursor:
                raise HistoryReaderContractError(
                    "exhausted read must preserve the input cursor"
                )
    except Exception as exc:  # noqa: BLE001 - audit boundary
        report.issues.append(_issue("history_reader", exc))
    report.pages_read = guarded.pages_read
    report.messages_read = guarded.messages_read
    return report


async def audit_batch_task(
    task: MemoryBatchTask,
    context: BatchTaskContext,
    *,
    allowed_scopes: Sequence[MemoryScope] = (),
    read_limits: BatchReadLimits | None = None,
) -> BatchTaskAuditReport:
    """Run a task's pure proposal phase and audit its output without writing a Store."""

    task_name = str(getattr(task, "name", "") or "").strip()
    task_version = str(getattr(task, "version", "") or "").strip()
    report = BatchTaskAuditReport(task=task_name, task_version=task_version)
    guarded = GuardedHistoryReader(context.history, read_limits)
    try:
        if not task_name:
            raise ValueError("batch task name is required")
        if not task_version:
            raise ValueError("batch task version is required")
        if context.history.scope.scope_key != context.scope.scope_key:
            raise ValueError("history reader scope does not match task scope")
        schema_version = _task_checkpoint_schema_version(task)
        report.checkpoint_schema_version = schema_version
        bound_checkpoint = _bind_checkpoint(
            context.checkpoint,
            task_name=task_name,
            task_version=task_version,
            schema_version=schema_version,
        )
        guarded_context = replace(context, checkpoint=bound_checkpoint, history=guarded)
        raw_plan = await task.propose(guarded_context)
        if isinstance(raw_plan, BatchProposalPlan):
            raw_plan = raw_plan.model_dump(warnings=False)
        plan = BatchProposalPlan.model_validate(raw_plan)
        report.proposal_count = len(plan.proposals)
        report.proposes_checkpoint = plan.next_checkpoint is not None
        if plan.next_checkpoint is not None:
            _bind_checkpoint(
                plan.next_checkpoint,
                task_name=task_name,
                task_version=task_version,
                schema_version=schema_version,
            )
        allowed_keys = {
            context.scope.scope_key,
            *(scope.scope_key for scope in allowed_scopes),
        }
        for proposal in plan.proposals:
            _check_proposal_scope(proposal, allowed_keys)
    except Exception as exc:  # noqa: BLE001 - audit boundary
        stage = (
            "history_read"
            if isinstance(exc, (BatchReadLimitError, HistoryReaderContractError))
            else "batch_task"
        )
        report.issues.append(_issue(stage, exc))
    report.history_pages_read = guarded.pages_read
    report.history_messages_read = guarded.messages_read
    return report


def _check_proposal_scope(proposal: MemoryProposal, allowed_keys: set[str]) -> None:
    if proposal.scope.scope_key not in allowed_keys:
        raise ValueError("batch task proposal target scope is not authorized")


def _issue(stage: str, error: Exception) -> ConformanceIssue:
    return ConformanceIssue(
        stage=stage,
        error_type=type(error).__name__,
        message=str(error),
    )


def _raise_issues(issues: Sequence[ConformanceIssue]) -> None:
    if not issues:
        return
    details = "; ".join(
        f"{issue.stage}/{issue.error_type}: {issue.message}" for issue in issues
    )
    raise ConformanceError(details)
