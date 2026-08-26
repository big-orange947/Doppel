"""Read-budget, pagination-guard, and checkpoint binding contracts."""

from __future__ import annotations

import pytest

from doppel_memory import (
    BatchCheckpoint,
    BatchProposalPlan,
    BatchTaskRunner,
    ChatMessage,
    HistoryPage,
    HistoryWindow,
    InMemoryStore,
    MemoryProposal,
    MemoryScope,
)
from doppel_memory.batch import BatchReadLimits

SCOPE = MemoryScope(user_id="u1", agent_id="agent")
WINDOW = HistoryWindow(start="2026-08-26T00:00:00Z", end="2026-08-27T00:00:00Z")


class EndlessReader:
    def __init__(self) -> None:
        self._count = 0

    @property
    def scope(self):
        return SCOPE

    async def read(self, *, cursor="", limit=500, **kwargs):
        self._count += 1
        return HistoryPage(
            messages=[
                ChatMessage.of(
                    "owner",
                    str(self._count),
                    f"2026-08-26T00:00:{self._count:02d}Z",
                    event_id=f"event-{self._count}",
                )
            ],
            next_cursor=f"cursor-{self._count}",
            has_more=True,
        )


class DrainTask:
    name = "drain"
    version = "1"

    async def propose(self, context):
        cursor = context.checkpoint.cursor
        while True:
            page = await context.history.read(cursor=cursor, limit=1)
            cursor = page.next_cursor
            if not page.has_more:
                break
        return BatchProposalPlan(next_checkpoint=BatchCheckpoint(cursor=cursor))


async def test_runner_stops_endless_reader_at_page_budget() -> None:
    result = await BatchTaskRunner(InMemoryStore()).run_once(
        DrainTask(),
        SCOPE,
        WINDOW,
        history=EndlessReader(),
        read_limits=BatchReadLimits(max_pages=2, max_messages=10, max_page_size=1),
    )
    assert result.errors[0].stage == "history_read"
    assert result.errors[0].error_type == "BatchReadLimitError"
    assert result.history_pages_read == 2
    assert result.history_messages_read == 2
    assert result.committable_checkpoint is None


class StuckReader:
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


async def test_runner_rejects_non_advancing_reader_cursor() -> None:
    result = await BatchTaskRunner(InMemoryStore()).run_once(
        DrainTask(), SCOPE, WINDOW, history=StuckReader()
    )
    assert result.errors[0].stage == "history_read"
    assert result.errors[0].error_type == "HistoryReaderContractError"
    assert "must advance" in result.errors[0].message


class NonAdvancingFinalReader(StuckReader):
    async def read(self, *, cursor="", limit=500, **kwargs):
        page = await super().read(cursor=cursor, limit=limit, **kwargs)
        page.has_more = False
        return page


async def test_runner_rejects_non_advancing_final_page() -> None:
    result = await BatchTaskRunner(InMemoryStore()).run_once(
        DrainTask(),
        SCOPE,
        WINDOW,
        checkpoint=BatchCheckpoint(cursor="stuck"),
        history=NonAdvancingFinalReader(),
    )
    assert result.errors[0].error_type == "HistoryReaderContractError"
    assert "every non-empty page" in result.errors[0].message


class OversizePageTask:
    name = "oversize-page"
    version = "1"

    async def propose(self, context):
        await context.history.read(limit=3)
        return BatchProposalPlan()


async def test_runner_rejects_requested_page_above_limit() -> None:
    result = await BatchTaskRunner(InMemoryStore()).run_once(
        OversizePageTask(),
        SCOPE,
        WINDOW,
        history=EndlessReader(),
        read_limits=BatchReadLimits(max_pages=10, max_messages=10, max_page_size=2),
    )
    assert result.errors[0].error_type == "BatchReadLimitError"
    assert result.history_pages_read == 0


class BurstReader:
    @property
    def scope(self):
        return SCOPE

    async def read(self, *, cursor="", limit=500, **kwargs):
        return HistoryPage(
            messages=[
                ChatMessage.of(
                    "owner",
                    str(index),
                    f"2026-08-26T0{index}:00:00Z",
                    event_id=str(index),
                )
                for index in (1, 2)
            ],
            next_cursor="burst-end",
        )


class OneReadTask:
    name = "one-read"
    version = "1"

    def __init__(self, limit: int) -> None:
        self._limit = limit

    async def propose(self, context):
        await context.history.read(limit=self._limit)
        return BatchProposalPlan()


async def test_runner_enforces_actual_message_budget() -> None:
    result = await BatchTaskRunner(InMemoryStore()).run_once(
        OneReadTask(2),
        SCOPE,
        WINDOW,
        history=BurstReader(),
        read_limits=BatchReadLimits(max_pages=10, max_messages=1, max_page_size=2),
    )
    assert result.errors[0].error_type == "BatchReadLimitError"
    assert result.history_pages_read == 1
    assert result.history_messages_read == 2


async def test_runner_rejects_reader_that_ignores_requested_limit() -> None:
    result = await BatchTaskRunner(InMemoryStore()).run_once(
        OneReadTask(1), SCOPE, WINDOW, history=BurstReader()
    )
    assert result.errors[0].error_type == "HistoryReaderContractError"
    assert "returned 2 messages for limit=1" in result.errors[0].message


class VersionedTask:
    name = "versioned"
    version = "2"
    checkpoint_schema_version = 2

    async def propose(self, context):
        assert context.checkpoint.task_name == self.name
        assert context.checkpoint.task_version == self.version
        assert context.checkpoint.schema_version == self.checkpoint_schema_version
        return BatchProposalPlan(
            next_checkpoint=BatchCheckpoint(
                cursor="next", schema_version=self.checkpoint_schema_version
            )
        )


async def test_runner_binds_task_identity_and_checkpoint_schema() -> None:
    result = await BatchTaskRunner(InMemoryStore()).run_once(
        VersionedTask(), SCOPE, WINDOW
    )
    assert result.checkpoint_schema_version == 2
    assert result.committable_checkpoint == BatchCheckpoint(
        cursor="next",
        task_name="versioned",
        task_version="2",
        schema_version=2,
    )


class InvalidSchemaTypeTask(VersionedTask):
    checkpoint_schema_version = "2"


async def test_runner_requires_strict_integer_checkpoint_schema() -> None:
    with pytest.raises(TypeError, match="positive integer"):
        await BatchTaskRunner(InMemoryStore()).run_once(
            InvalidSchemaTypeTask(), SCOPE, WINDOW
        )


async def test_runner_rejects_checkpoint_from_other_task_or_schema() -> None:
    runner = BatchTaskRunner(InMemoryStore())
    with pytest.raises(ValueError, match="belongs to task"):
        await runner.run_once(
            VersionedTask(),
            SCOPE,
            WINDOW,
            checkpoint=BatchCheckpoint(
                task_name="other", task_version="2", schema_version=2
            ),
        )
    with pytest.raises(ValueError, match="schema_version"):
        await runner.run_once(
            VersionedTask(),
            SCOPE,
            WINDOW,
            checkpoint=BatchCheckpoint(schema_version=1),
        )
    with pytest.raises(ValueError, match="task_version"):
        await runner.run_once(
            VersionedTask(),
            SCOPE,
            WINDOW,
            checkpoint=BatchCheckpoint(
                task_name="versioned", task_version="1", schema_version=2
            ),
        )


class WrongOutputCheckpointTask(VersionedTask):
    async def propose(self, context):
        return BatchProposalPlan(
            proposals=[
                MemoryProposal(
                    scope=context.scope,
                    content="must not write",
                    processor=self.name,
                )
            ],
            next_checkpoint=BatchCheckpoint(schema_version=1),
        )


async def test_invalid_output_checkpoint_prevents_proposal_write() -> None:
    store = InMemoryStore()
    result = await BatchTaskRunner(store).run_once(
        WrongOutputCheckpointTask(), SCOPE, WINDOW
    )
    assert result.errors[0].stage == "checkpoint"
    assert result.write_results == []
    assert await store.search("must not write", [SCOPE]) == []
