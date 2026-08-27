"""Dependency-free conformance probes for Stores and third-party batch extensions."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
from doppel_memory.models import (
    Actor,
    ChatMessage,
    ContentPart,
    FactAuthority,
    MediaRef,
    MemoryFilter,
    MemoryIsolationError,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    MemoryStateConflictError,
    StoreCapabilities,
    WriteStatus,
)
from doppel_memory.processing import MemoryProposal
from doppel_memory.store import MemoryStore


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


class StoreConformanceConfig(BaseModel):
    """Selection and capability requirements for one mutating Store audit."""

    model_config = ConfigDict(frozen=True)

    run_id: str = ""
    checks: frozenset[str] | None = None
    required_capabilities: frozenset[str] = Field(default_factory=frozenset)

    @field_validator("run_id", mode="before")
    @classmethod
    def _normalize_run_id(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("checks", mode="before")
    @classmethod
    def _normalize_checks(cls, value: Any) -> frozenset[str] | None:
        if value is None:
            return None
        normalized = frozenset(str(item or "").strip() for item in value)
        if "" in normalized:
            raise ValueError("checks must contain non-empty names")
        unknown = normalized.difference(_STORE_CHECK_NAMES)
        if unknown:
            raise ValueError(f"unknown Store conformance checks: {sorted(unknown)}")
        return normalized

    @field_validator("required_capabilities", mode="before")
    @classmethod
    def _normalize_capabilities(cls, value: Any) -> frozenset[str]:
        normalized = frozenset(str(item or "").strip() for item in (value or ()))
        if "" in normalized:
            raise ValueError("required_capabilities must contain non-empty names")
        unknown = normalized.difference(StoreCapabilities.model_fields)
        if unknown:
            raise ValueError(f"unknown Store capabilities: {sorted(unknown)}")
        return normalized


class StoreConformanceCheck(BaseModel):
    """Outcome of one isolated semantic check within a Store audit run."""

    name: str
    status: Literal["passed", "skipped", "failed"]
    capability: str = ""
    issues: list[ConformanceIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_issue_status(self) -> StoreConformanceCheck:
        if self.status == "failed" and not self.issues:
            raise ValueError("failed Store conformance checks must include an issue")
        if self.status != "failed" and self.issues:
            raise ValueError("only failed Store conformance checks may include issues")
        return self


class StoreConformanceReport(BaseModel):
    """Machine-readable result from the dependency-free Store conformance kit."""

    schema_version: int = 1
    run_id: str
    store: str
    capabilities: StoreCapabilities
    checks: list[StoreConformanceCheck] = Field(default_factory=list)
    passed_count: int = Field(default=0, ge=0)
    skipped_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate_counts(self) -> StoreConformanceReport:
        expected = {
            "passed": sum(check.status == "passed" for check in self.checks),
            "skipped": sum(check.status == "skipped" for check in self.checks),
            "failed": sum(check.status == "failed" for check in self.checks),
        }
        actual = {
            "passed": self.passed_count,
            "skipped": self.skipped_count,
            "failed": self.failed_count,
        }
        if actual != expected:
            raise ValueError(
                f"Store conformance counts do not match check statuses: {actual} != {expected}"
            )
        return self

    @property
    def ok(self) -> bool:
        return self.failed_count == 0

    @property
    def issues(self) -> list[ConformanceIssue]:
        return [issue for check in self.checks for issue in check.issues]

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


@dataclass(frozen=True)
class _StoreFixture:
    run_id: str
    check: str

    def scope(self, name: str = "primary", *, user: str = "owner") -> MemoryScope:
        token = f"{self.run_id}:{self.check}:{name}"
        return MemoryScope(
            user_id=f"doppel-conformance-{user}-{token}",
            agent_id="doppel-conformance-agent",
            platform="conformance",
            chat_type="private",
            chat_id=token,
        )

    def memory_id(self, name: str) -> str:
        return f"doppel-conformance:{self.run_id}:{self.check}:{name}"

    def event_id(self, name: str) -> str:
        return f"doppel-conformance-event:{self.run_id}:{self.check}:{name}"

    def token(self, name: str) -> str:
        return f"doppel-conformance-token-{self.run_id}-{self.check}-{name}"


_StoreCheck = Callable[[MemoryStore, _StoreFixture], Awaitable[None]]


async def audit_store(
    store: MemoryStore,
    *,
    config: StoreConformanceConfig | None = None,
) -> StoreConformanceReport:
    """Run the stable Store contract against a caller-owned writable backend.

    The audit writes uniquely namespaced test records and may transition or delete only
    records it created. It does not close the Store and cannot clean records from a
    backend without hard-delete support. Use a disposable database, tenant, or namespace.
    """

    bound_config = config or StoreConformanceConfig()
    run_id = bound_config.run_id or uuid4().hex[:12]
    selected = bound_config.checks or _STORE_CHECK_NAMES
    capabilities = StoreCapabilities.model_validate(store.capabilities)
    results: list[StoreConformanceCheck] = []

    covered_capabilities = {
        capability
        for name, capability, _ in _STORE_CHECKS
        if name in selected and capability
    }
    for capability in sorted(bound_config.required_capabilities):
        if (
            not getattr(capabilities, capability)
            and capability not in covered_capabilities
        ):
            error = NotImplementedError(
                f"required Store capability is not advertised: {capability}"
            )
            results.append(
                StoreConformanceCheck(
                    name=f"capability:{capability}",
                    status="failed",
                    capability=capability,
                    issues=[_issue(f"capability:{capability}", error)],
                )
            )

    for name, capability, check in _STORE_CHECKS:
        if name not in selected:
            continue
        if capability and not getattr(capabilities, capability):
            status: Literal["skipped", "failed"] = (
                "failed"
                if capability in bound_config.required_capabilities
                else "skipped"
            )
            issues = (
                [
                    _issue(
                        name,
                        NotImplementedError(
                            f"required Store capability is not advertised: {capability}"
                        ),
                    )
                ]
                if status == "failed"
                else []
            )
            results.append(
                StoreConformanceCheck(
                    name=name,
                    status=status,
                    capability=capability,
                    issues=issues,
                )
            )
            continue
        fixture = _StoreFixture(
            run_id=hashlib.sha256(run_id.encode()).hexdigest()[:16],
            check=name,
        )
        try:
            await check(store, fixture)
            result = StoreConformanceCheck(
                name=name,
                status="passed",
                capability=capability,
            )
        except Exception as exc:  # noqa: BLE001 - conformance boundary
            result = StoreConformanceCheck(
                name=name,
                status="failed",
                capability=capability,
                issues=[_issue(name, exc)],
            )
        results.append(result)

    return StoreConformanceReport(
        run_id=run_id,
        store=f"{type(store).__module__}.{type(store).__qualname__}",
        capabilities=capabilities,
        checks=results,
        passed_count=sum(result.status == "passed" for result in results),
        skipped_count=sum(result.status == "skipped" for result in results),
        failed_count=sum(result.status == "failed" for result in results),
    )


async def _audit_store_health(store: MemoryStore, fixture: _StoreFixture) -> None:
    del fixture
    _require(store.is_enabled, "Store must be enabled for a conformance audit")
    health = await store.health()
    _require(isinstance(health, dict), "health() must return a dictionary")
    _require(health.get("enabled") is True, "health.enabled must be true")
    _require(health.get("ok") is True, "health.ok must be true")


async def _audit_store_scope_isolation(
    store: MemoryStore, fixture: _StoreFixture
) -> None:
    scope_a = fixture.scope("a")
    scope_b = fixture.scope("b")
    scope_y = fixture.scope("y", user="other")
    token = fixture.token("isolation")
    for scope, suffix in ((scope_a, "a"), (scope_b, "b"), (scope_y, "y")):
        result = await store.write_event(
            scope,
            ChatMessage.of(
                Actor.OWNER,
                f"{token}-{suffix}",
                "2026-01-01T00:00:00Z",
                event_id=fixture.event_id(suffix),
            ),
        )
        _require(result.status is WriteStatus.CREATED, f"initial {suffix} write failed")

    hits_a = await store.search(f"{token}-a", [scope_a])
    _require_expected_event(hits_a, fixture.event_id("a"), scope_a)
    _require(
        await store.search(f"{token}-a", [scope_b]) == [],
        "search leaked a record into a different exact scope",
    )
    _require(
        await store.search(f"{token}-a", [scope_y]) == [],
        "search leaked a record across users",
    )

    try:
        await store.search(token, [])
    except MemoryIsolationError:
        pass
    else:
        raise ConformanceError("search without an exact scope must be rejected")

    user_scope = scope_a.user_scope()
    background = await store.write_background(user_scope, fixture.token("global"))
    _require(background.status is WriteStatus.CREATED, "user-scope write failed")
    _require(
        await store.search(fixture.token("global"), [scope_a]) == [],
        "scope hierarchy must not be implicit",
    )
    _require(
        len(await store.search(fixture.token("global"), [user_scope])) == 1,
        "explicit user-scope search did not return its record",
    )

    thread_a = scope_a.with_dimension("thread_id", "a")
    thread_b = scope_a.with_dimension("thread_id", "b")
    thread_result = await store.write_event(
        thread_a,
        ChatMessage.of(
            Actor.OWNER,
            fixture.token("thread"),
            "2026-01-01T00:01:00Z",
            event_id=fixture.event_id("thread"),
        ),
    )
    _require(thread_result.status is WriteStatus.CREATED, "thread write failed")
    _require(
        await store.search(fixture.token("thread"), [thread_b]) == [],
        "extra scope dimensions are not isolated",
    )


async def _audit_store_idempotency(store: MemoryStore, fixture: _StoreFixture) -> None:
    scope = fixture.scope()
    other = fixture.scope("other")
    message = ChatMessage.of(
        Actor.OWNER,
        fixture.token("idempotent"),
        "2026-01-01T01:00:00Z",
        event_id=fixture.event_id("same"),
    )
    first = await store.write_event(scope, message)
    duplicate = await store.write_event(scope, message)
    other_scope = await store.write_event(other, message)
    _require(first.status is WriteStatus.CREATED, "first idempotent write must create")
    _require(
        duplicate.status is WriteStatus.DUPLICATE,
        "repeated idempotency key must return duplicate",
    )
    _require(
        duplicate.memory_id == first.memory_id and bool(first.memory_id),
        "duplicate write must return the original memory ID",
    )
    _require(
        other_scope.status is WriteStatus.CREATED,
        "idempotency keys must be isolated by exact scope",
    )
    _require(
        len(await store.search(fixture.token("idempotent"), [scope])) == 1,
        "duplicate write created more than one record",
    )


async def _audit_store_record_round_trip(
    store: MemoryStore, fixture: _StoreFixture
) -> None:
    scope = fixture.scope()
    record = MemoryRecord(
        memory_id=fixture.memory_id("custom"),
        scope=scope,
        kind="example.preference",
        content=fixture.token("short-replies"),
        actor="moderator",
        state=MemoryState.CANDIDATE,
        tags=["style", "preference"],
        importance=0.8,
        metadata={"nested": {"value": 7}},
    )
    result = await store.put(record, idempotency_key=fixture.token("put-key"))
    _require(result.status is WriteStatus.CREATED, "generic put did not create")
    created = result.record
    if created is None:
        raise ConformanceError("created put must return its record")
    restored = await store.get(scope, result.memory_id)
    if restored is None:
        raise ConformanceError("get did not return the created record")
    _require(restored.kind == record.kind, "custom memory kind did not round-trip")
    _require(restored.actor == "moderator", "custom actor did not round-trip")
    _require(restored.state is MemoryState.CANDIDATE, "state did not round-trip")
    _require(restored.metadata == record.metadata, "metadata did not round-trip")

    created.content = "caller mutation"
    created.metadata["nested"]["value"] = 99
    independent = await store.get(scope, result.memory_id)
    if independent is None:
        raise ConformanceError("record disappeared after caller mutation")
    _require(
        independent.content == record.content
        and independent.metadata["nested"]["value"] == 7,
        "returned records must not alias mutable backend state",
    )

    conflict = await store.put(record)
    _require(
        conflict.status is WriteStatus.FAILED and bool(conflict.error_code),
        "reusing a memory ID must return a structured conflict",
    )


async def _audit_store_filters_and_provenance(
    store: MemoryStore, fixture: _StoreFixture
) -> None:
    scope = fixture.scope()
    owner = ChatMessage.of(
        Actor.OWNER,
        fixture.token("owner"),
        "2026-01-01T02:00:00Z",
        event_id=fixture.event_id("owner"),
    )
    contact = ChatMessage.of(
        Actor.CONTACT,
        fixture.token("contact"),
        "2026-01-01T02:01:00Z",
        event_id=fixture.event_id("contact"),
    )
    agent = ChatMessage.of(
        Actor.AGENT,
        fixture.token("agent"),
        "2026-01-01T02:02:00Z",
        event_id=fixture.event_id("agent"),
    )
    for message in (owner, contact, agent):
        result = await store.write_event(scope, message)
        _require(result.status is WriteStatus.CREATED, "filter fixture write failed")
    background = await store.write_background(
        scope,
        fixture.token("background"),
        tags=["work", "audit"],
        importance=0.9,
    )
    _require(background.status is WriteStatus.CREATED, "background write failed")

    contacts = await store.search(
        "", [scope], filters=MemoryFilter(actors={Actor.CONTACT})
    )
    _require(
        len(contacts) == 1 and contacts[0].source_event_id == contact.event_id,
        "actor filter did not select exactly the contact event",
    )
    backgrounds = await store.search(
        "",
        [scope],
        filters=MemoryFilter(
            kinds={MemoryKind.BACKGROUND}, tags={"work"}, importance_min=0.8
        ),
    )
    _require(len(backgrounds) == 1, "kind/tag/importance filters did not compose")
    non_agent = await store.search(
        "",
        [scope],
        filters=MemoryFilter(exclude_authorities={FactAuthority.AGENT_OUTPUT}),
        limit=20,
    )
    _require(
        all(item.authority is not FactAuthority.AGENT_OUTPUT for item in non_agent),
        "exclude_authorities returned agent output",
    )
    owner_hits = await store.search(owner.text, [scope])
    _require_expected_event(owner_hits, owner.event_id, scope)
    hit = next(item for item in owner_hits if item.source_event_id == owner.event_id)
    _require(hit.actor == Actor.OWNER, "recall actor provenance was lost")
    _require(
        hit.authority is FactAuthority.HUMAN_SELF,
        "recall authority provenance was lost",
    )
    _require(hit.raw_text == owner.text, "recall raw_text provenance was lost")


async def _audit_store_owner_samples(
    store: MemoryStore, fixture: _StoreFixture
) -> None:
    scope = fixture.scope()
    first = ChatMessage.of(
        Actor.OWNER,
        fixture.token("first"),
        "2026-01-01T03:00:00Z",
        event_id=fixture.event_id("first"),
    )
    structured = ChatMessage.of(
        Actor.OWNER,
        fixture.token("structured"),
        "2026-01-01T03:01:00Z",
        event_id=fixture.event_id("structured"),
        message_id=fixture.event_id("message"),
        sender_id="owner-id",
        reply_to_id="reply-target",
        quoted_message_id="quote-target",
        thread_id="thread-1",
        thread_root_id="root-1",
        raw={"sequence": 7},
        parts=[
            ContentPart(type="text", text=fixture.token("structured")),
            ContentPart(
                type="image",
                media=MediaRef(media_id="image-7", mime_type="image/png"),
            ),
        ],
    )
    contact = ChatMessage.of(
        Actor.CONTACT,
        fixture.token("contact"),
        "2026-01-01T03:02:00Z",
        event_id=fixture.event_id("contact"),
    )
    first_result = None
    for message in (first, structured, contact):
        result = await store.write_event(scope, message)
        _require(result.status is WriteStatus.CREATED, "owner sample write failed")
        if message is first:
            first_result = result
    samples = await store.list_recent_owner_messages(scope, limit=5)
    _require(
        [message.event_id for message in samples]
        == [first.event_id, structured.event_id],
        "owner samples must be active owner-only and oldest-first",
    )
    restored = samples[-1]
    _require(restored.sender_id == "owner-id", "sender provenance was lost")
    _require(restored.reply_to_id == "reply-target", "reply provenance was lost")
    _require(restored.quoted_message_id == "quote-target", "quote provenance was lost")
    _require(
        restored.thread_id == "thread-1" and restored.thread_root_id == "root-1",
        "thread provenance was lost",
    )
    _require(restored.raw == {"sequence": 7}, "raw event data was lost")
    _require(restored.parts == structured.parts, "structured content parts were lost")
    if first_result is None:
        raise ConformanceError("owner sample fixture did not retain its write result")
    _require(
        await store.forget(scope, first_result.memory_id),
        "owner sample soft forget failed",
    )
    remaining = await store.list_recent_owner_messages(scope, limit=5)
    _require(
        [message.event_id for message in remaining] == [structured.event_id],
        "owner samples must exclude inactive memories",
    )


async def _audit_store_lifecycle(store: MemoryStore, fixture: _StoreFixture) -> None:
    scope = fixture.scope()
    other = fixture.scope("other")
    candidate = await store.put(
        MemoryRecord(
            memory_id=fixture.memory_id("candidate"),
            scope=scope,
            kind=MemoryKind.FACT,
            content=fixture.token("candidate"),
            state=MemoryState.CANDIDATE,
        )
    )
    _require(candidate.status is WriteStatus.CREATED, "candidate write failed")
    candidate_content = fixture.token("candidate")
    confirmed = await store.transition(
        scope,
        candidate.memory_id,
        MemoryState.CONFIRMED,
        expected_state=MemoryState.CANDIDATE,
    )
    _require(confirmed.state is MemoryState.CONFIRMED, "transition state was not saved")
    _require(confirmed.version == 2, "transition must increment record version")
    try:
        await store.transition(
            scope,
            candidate.memory_id,
            MemoryState.REJECTED,
            expected_state=MemoryState.CANDIDATE,
        )
    except MemoryStateConflictError:
        pass
    else:
        raise ConformanceError(
            "stale expected_state must raise MemoryStateConflictError"
        )

    _require(
        await store.get(other, candidate.memory_id) is None,
        "get crossed an exact scope boundary",
    )
    _require(
        not await store.forget(other, candidate.memory_id),
        "forget crossed an exact scope boundary",
    )
    _require(
        await store.forget(scope, candidate.memory_id, hard=False),
        "soft forget did not report success",
    )
    _require(
        await store.search(candidate_content, [scope]) == [],
        "soft-forgotten memory remained active",
    )
    inactive = await store.search(
        candidate_content,
        [scope],
        filters=MemoryFilter(include_inactive=True),
    )
    _require(
        len(inactive) == 1 and inactive[0].state is MemoryState.EXPIRED,
        "include_inactive did not expose the expired memory",
    )


async def _audit_store_convenience_writers(
    store: MemoryStore, fixture: _StoreFixture
) -> None:
    scope = fixture.scope()
    background_text = fixture.token("background")
    background = await store.write_background(
        scope, background_text, tags=["work", "relation"]
    )
    relation = await store.write_relation(
        scope,
        counterpart="contact-1",
        relationship="former-colleague",
        address="friend",
    )
    _require(background.status is WriteStatus.CREATED, "background writer failed")
    _require(relation.status is WriteStatus.CREATED, "relation writer failed")
    _require(
        len(await store.search(background_text, [scope])) == 1,
        "background writer output was not searchable",
    )
    relations = await store.search(
        "", [scope], filters=MemoryFilter(kinds={MemoryKind.RELATION})
    )
    _require(
        len(relations) == 1 and relations[0].kind == MemoryKind.RELATION,
        "relation writer output was not filterable",
    )


async def _audit_store_pagination(store: MemoryStore, fixture: _StoreFixture) -> None:
    scope = fixture.scope("pages")
    other = fixture.scope("other")
    at = _time("2026-01-01T04:00:00Z")
    ids = [fixture.memory_id(f"page-{suffix}") for suffix in ("a", "b", "c")]
    for memory_id in ids:
        result = await store.put(
            MemoryRecord(
                memory_id=memory_id,
                scope=scope,
                kind=MemoryKind.EVENT,
                content=memory_id,
                actor=Actor.OWNER,
                created_at=at,
                updated_at=at,
            )
        )
        _require(
            result.status is WriteStatus.CREATED, "pagination fixture write failed"
        )
    await store.put(
        MemoryRecord(
            memory_id=fixture.memory_id("other-scope"),
            scope=other,
            content=fixture.token("other"),
            created_at=at,
            updated_at=at,
        )
    )
    first = await store.scan(scope, limit=2)
    _require(
        [record.memory_id for record in first.records] == ids[:2],
        "first page order or exact-scope filtering is incorrect",
    )
    _require(first.has_more and bool(first.next_cursor), "first page cursor is invalid")
    second = await store.scan(scope, cursor=first.next_cursor, limit=2)
    _require(
        [record.memory_id for record in second.records] == ids[2:],
        "second page order is incorrect",
    )
    _require(
        not second.has_more and bool(second.next_cursor),
        "final non-empty page must return a durable cursor",
    )
    exhausted = await store.scan(scope, cursor=second.next_cursor, limit=2)
    _require(
        exhausted.records == []
        and not exhausted.has_more
        and exhausted.next_cursor == second.next_cursor,
        "exhausted scan must preserve its input cursor",
    )
    try:
        await store.scan(scope, cursor="not-a-cursor")
    except ValueError:
        pass
    else:
        raise ConformanceError("invalid pagination cursor must raise ValueError")

    watermark_scope = fixture.scope("watermark")
    for suffix, timestamp in (
        ("a", "2026-01-01T04:00:00Z"),
        ("b", "2026-01-01T05:00:00Z"),
    ):
        await store.put(
            MemoryRecord(
                memory_id=fixture.memory_id(f"watermark-{suffix}"),
                scope=watermark_scope,
                content=suffix,
                created_at=_time(timestamp),
                updated_at=_time(timestamp),
            )
        )
    initial = await store.scan(watermark_scope)
    for suffix, timestamp in (
        ("late", "2026-01-01T04:30:00Z"),
        ("next", "2026-01-01T06:00:00Z"),
    ):
        await store.put(
            MemoryRecord(
                memory_id=fixture.memory_id(f"watermark-{suffix}"),
                scope=watermark_scope,
                content=suffix,
                created_at=_time(timestamp),
                updated_at=_time(timestamp),
            )
        )
    delta = await store.scan(watermark_scope, cursor=initial.next_cursor)
    _require(
        [record.memory_id for record in delta.records]
        == [fixture.memory_id("watermark-next")],
        "scan cursor is not a forward-only (created_at, memory_id) watermark",
    )


async def _audit_store_temporal_filter(
    store: MemoryStore, fixture: _StoreFixture
) -> None:
    scope = fixture.scope()
    earlier = ChatMessage.of(
        Actor.OWNER,
        fixture.token("earlier"),
        "2026-01-01T23:30:00+08:00",
        event_id=fixture.event_id("earlier"),
    )
    later = ChatMessage.of(
        Actor.OWNER,
        fixture.token("later"),
        "2026-01-01T16:00:00Z",
        event_id=fixture.event_id("later"),
    )
    await store.write_event(scope, earlier)
    await store.write_event(scope, later)
    hits = await store.search(
        "",
        [scope],
        filters=MemoryFilter(time_from=_time("2026-01-01T15:45:00Z")),
    )
    _require(
        [hit.source_event_id for hit in hits] == [later.event_id],
        "temporal filter did not normalize time zones",
    )


async def _audit_store_hard_delete(store: MemoryStore, fixture: _StoreFixture) -> None:
    scope = fixture.scope()
    result = await store.put(
        MemoryRecord(
            memory_id=fixture.memory_id("hard-delete"),
            scope=scope,
            content=fixture.token("hard-delete"),
        )
    )
    _require(result.status is WriteStatus.CREATED, "hard-delete fixture write failed")
    _require(
        await store.forget(scope, result.memory_id, hard=True),
        "advertised hard delete did not report success",
    )
    _require(
        await store.get(scope, result.memory_id) is None,
        "hard-deleted record is still retrievable",
    )


_STORE_CHECKS: tuple[tuple[str, str, _StoreCheck], ...] = (
    ("health", "", _audit_store_health),
    ("scope_isolation", "", _audit_store_scope_isolation),
    ("idempotency", "", _audit_store_idempotency),
    ("record_round_trip", "", _audit_store_record_round_trip),
    ("filters_and_provenance", "", _audit_store_filters_and_provenance),
    ("owner_samples", "", _audit_store_owner_samples),
    ("lifecycle", "", _audit_store_lifecycle),
    ("convenience_writers", "", _audit_store_convenience_writers),
    ("pagination", "pagination", _audit_store_pagination),
    ("temporal_filter", "temporal_search", _audit_store_temporal_filter),
    ("hard_delete", "hard_delete", _audit_store_hard_delete),
)
_STORE_CHECK_NAMES = frozenset(name for name, _, _ in _STORE_CHECKS)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConformanceError(message)


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _require_expected_event(
    hits: Sequence[Any], event_id: str, scope: MemoryScope
) -> None:
    matching = [item for item in hits if item.source_event_id == event_id]
    _require(bool(matching), f"search did not return expected event {event_id}")
    _require(
        all(
            item.scope is not None and item.scope.scope_key == scope.scope_key
            for item in hits
        ),
        "search returned a result outside its exact authorized scope",
    )


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


def _conformance_parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run Doppel Store conformance against a disposable built-in backend."
    )
    parser.add_argument(
        "--backend", choices=("memory", "sqlite", "postgres"), default="memory"
    )
    parser.add_argument(
        "--database",
        help="New SQLite path; existing files are refused to protect application data.",
    )
    parser.add_argument("--dsn", help="PostgreSQL DSN for a disposable test database.")
    parser.add_argument(
        "--allow-mutating-audit",
        action="store_true",
        help="Required for PostgreSQL; confirms that the target is disposable.",
    )
    parser.add_argument("--output", help="Optional JSON report path.")
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--require-capability",
        action="append",
        default=[],
        help="Capability that must be advertised; may be repeated.",
    )
    return parser


async def _run_conformance_cli(args: Any) -> int:
    import json
    import tempfile
    from pathlib import Path

    temporary_directory: tempfile.TemporaryDirectory[str] | None = None
    if args.backend == "memory":
        from doppel_memory.in_memory_store import InMemoryStore

        store: MemoryStore = InMemoryStore()
    elif args.backend == "sqlite":
        from doppel_memory.sqlite_store import SQLiteStore

        if args.database:
            database = Path(args.database).resolve()
            if database.exists():
                raise ValueError(
                    "conformance SQLite database must not already exist; use a "
                    "disposable path"
                )
            database.parent.mkdir(parents=True, exist_ok=True)
        else:
            temporary_directory = tempfile.TemporaryDirectory(
                prefix="doppel-conformance-"
            )
            database = Path(temporary_directory.name) / "audit.sqlite3"
        store = SQLiteStore(database=str(database))
    else:
        from doppel_memory.postgres_store import PostgreSQLStore

        if not args.dsn:
            raise ValueError("--dsn is required with --backend postgres")
        if not args.allow_mutating_audit:
            raise ValueError(
                "PostgreSQL conformance mutates its target; pass "
                "--allow-mutating-audit only for a disposable database"
            )
        store = PostgreSQLStore(dsn=args.dsn)

    try:
        report = await audit_store(
            store,
            config=StoreConformanceConfig(
                run_id=args.run_id,
                required_capabilities=args.require_capability,
            ),
        )
        rendered = json.dumps(
            report.model_dump(mode="json"), ensure_ascii=False, indent=2
        )
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
        return 0 if report.ok else 1
    finally:
        await store.close()
        if temporary_directory is not None:
            temporary_directory.cleanup()


def _conformance_main() -> int:
    import asyncio

    parser = _conformance_parser()
    args = parser.parse_args()
    if args.backend != "sqlite" and args.database:
        parser.error("--database is valid only with --backend sqlite")
    if args.backend != "postgres" and args.dsn:
        parser.error("--dsn is valid only with --backend postgres")
    if args.backend != "postgres" and args.allow_mutating_audit:
        parser.error("--allow-mutating-audit is valid only with --backend postgres")
    try:
        return asyncio.run(_run_conformance_cli(args))
    except ValueError as exc:
        parser.error(str(exc))
        return 2  # pragma: no cover - argparse exits


if __name__ == "__main__":
    raise SystemExit(_conformance_main())
