"""Dependency-free conformance probes for third-party batch extensions."""

from __future__ import annotations

import pytest

from doppel_memory import (
    BatchCheckpoint,
    BatchProposalPlan,
    BatchTaskContext,
    ChatMessage,
    ConformanceError,
    HistoryPage,
    HistoryWindow,
    InMemoryStore,
    MemoryProposal,
    MemoryScope,
    StoreHistoryReader,
    StoreMemoryReader,
    audit_batch_task,
    audit_history_reader,
)

SCOPE = MemoryScope(user_id="u1", agent_id="agent")
OTHER_SCOPE = MemoryScope(user_id="u2", agent_id="agent")
WINDOW = HistoryWindow(start="2026-08-26T00:00:00Z", end="2026-08-27T00:00:00Z")


async def _seed(store: InMemoryStore) -> None:
    for index in range(2):
        await store.write_event(
            SCOPE,
            ChatMessage.of(
                "owner",
                f"message-{index}",
                f"2026-08-26T0{index + 1}:00:00Z",
                event_id=f"event-{index}",
            ),
        )


async def test_history_reader_audit_checks_paging_and_exhaustion() -> None:
    store = InMemoryStore()
    await _seed(store)
    report = await audit_history_reader(StoreHistoryReader(store, SCOPE), page_size=1)
    assert report.ok
    assert report.pages_read == 3
    assert report.messages_read == 2
    assert report.final_cursor
    report.raise_for_errors()


class NonAdvancingReader:
    @property
    def scope(self):
        return SCOPE

    async def read(self, *, cursor="", limit=500, **kwargs):
        return HistoryPage(
            messages=[
                ChatMessage.of(
                    "owner", "stuck", "2026-08-26T01:00:00Z", event_id="stuck"
                )
            ],
            next_cursor=cursor or "stuck",
            has_more=True,
        )


async def test_history_reader_audit_reports_contract_failure() -> None:
    report = await audit_history_reader(NonAdvancingReader(), page_size=1)
    assert not report.ok
    assert report.issues[0].error_type == "HistoryReaderContractError"
    with pytest.raises(ConformanceError, match="must advance"):
        report.raise_for_errors()


class OutOfOrderReader:
    @property
    def scope(self):
        return SCOPE

    async def read(self, *, cursor="", limit=500, **kwargs):
        if cursor:
            return HistoryPage(next_cursor=cursor)
        return HistoryPage(
            messages=[
                ChatMessage.of(
                    "owner", "later", "2026-08-26T02:00:00Z", event_id="later"
                ),
                ChatMessage.of(
                    "owner", "earlier", "2026-08-26T01:00:00Z", event_id="earlier"
                ),
            ],
            next_cursor="end",
        )


async def test_history_reader_audit_requires_oldest_first_order() -> None:
    report = await audit_history_reader(OutOfOrderReader(), page_size=2)
    assert not report.ok
    assert "oldest-first" in report.issues[0].message


class AuditedTask:
    name = "audited"
    version = "1"

    def __init__(self, target: MemoryScope = SCOPE) -> None:
        self._target = target

    async def propose(self, context):
        page = await context.history.read(limit=10)
        return BatchProposalPlan(
            proposals=[
                MemoryProposal(
                    scope=self._target,
                    content=f"audited {len(page.messages)} messages",
                    processor=self.name,
                )
            ],
            next_checkpoint=BatchCheckpoint(cursor=page.next_cursor),
        )


async def test_batch_task_audit_is_pure_and_validates_output() -> None:
    store = InMemoryStore()
    await _seed(store)
    context = BatchTaskContext(
        run_id="audit-run",
        scope=SCOPE,
        window=WINDOW,
        checkpoint=BatchCheckpoint(),
        history=StoreHistoryReader(store, SCOPE),
        memories=StoreMemoryReader(store, [SCOPE]),
    )
    report = await audit_batch_task(AuditedTask(), context)
    assert report.ok
    assert report.proposal_count == 1
    assert report.proposes_checkpoint
    assert report.history_pages_read == 1
    assert report.history_messages_read == 2
    assert await store.search("audited", [SCOPE]) == []


async def test_batch_task_audit_rejects_scope_escape_without_writing() -> None:
    store = InMemoryStore()
    context = BatchTaskContext(
        run_id="audit-run",
        scope=SCOPE,
        window=WINDOW,
        checkpoint=BatchCheckpoint(),
        history=StoreHistoryReader(store, SCOPE),
        memories=StoreMemoryReader(store, [SCOPE]),
    )
    report = await audit_batch_task(AuditedTask(OTHER_SCOPE), context)
    assert not report.ok
    assert "not authorized" in report.issues[0].message
    assert await store.search("audited", [OTHER_SCOPE]) == []
