"""Executable contracts for the host-side periodic-memory recipes."""

from __future__ import annotations

import pytest

from doppel_memory import (
    BatchCheckpoint,
    ChatMessage,
    DoppelClient,
    HistoryWindow,
    MemoryIsolationError,
    MemoryScope,
)
from examples.batch_runtime import SQLiteCheckpointStore, SQLiteEventLog
from examples.periodic_memory import InteractionPatternTask

SCOPE = MemoryScope(
    user_id="u1",
    agent_id="agent",
    platform="qq",
    chat_type="private",
    chat_id="c1",
)
OTHER_SCOPE = SCOPE.with_chat("qq", "private", "c2")


async def test_external_event_reader_is_exact_and_resumable() -> None:
    event_log = SQLiteEventLog()
    try:
        for index in range(2):
            await event_log.append(
                SCOPE,
                ChatMessage.of(
                    "contact",
                    "",
                    f"2026-08-26T0{index + 1}:00:00Z",
                    event_id=f"nudge-{index + 1}",
                    message_type="nudge",
                ),
            )
        await event_log.append(
            OTHER_SCOPE,
            ChatMessage.of(
                "contact",
                "other",
                "2026-08-26T03:00:00Z",
                event_id="other",
            ),
        )

        reader = event_log.history(SCOPE)
        first = await reader.read(limit=1)
        second = await reader.read(cursor=first.next_cursor, limit=1)
        exhausted = await reader.read(cursor=second.next_cursor, limit=1)
        assert [first.messages[0].event_id, second.messages[0].event_id] == [
            "nudge-1",
            "nudge-2",
        ]
        assert exhausted.messages == []
        assert exhausted.next_cursor == second.next_cursor

        with pytest.raises(MemoryIsolationError, match="another scope"):
            await event_log.history(OTHER_SCOPE).read(cursor=second.next_cursor)
    finally:
        await event_log.close()


async def test_checkpoint_recipe_is_task_and_scope_isolated() -> None:
    checkpoints = SQLiteCheckpointStore()
    try:
        expected = BatchCheckpoint(cursor="resume-here", metadata={"window": 7})
        await checkpoints.save("task-a", SCOPE, expected)
        assert await checkpoints.load("task-a", SCOPE) == expected
        assert await checkpoints.load("task-b", SCOPE) is None
        assert await checkpoints.load("task-a", OTHER_SCOPE) is None
    finally:
        await checkpoints.close()


async def test_transient_events_only_persist_as_aggregate_memory() -> None:
    memory = DoppelClient(backend="memory")
    event_log = SQLiteEventLog()
    checkpoints = SQLiteCheckpointStore()
    task = InteractionPatternTask(message_types={"nudge"}, threshold=3, page_size=2)
    window = HistoryWindow(start="2026-08-26T00:00:00Z", end="2026-08-27T00:00:00Z")
    try:
        for index in range(3):
            await event_log.append(
                SCOPE,
                ChatMessage.of(
                    "contact",
                    "",
                    f"2026-08-26T0{index + 1}:00:00Z",
                    event_id=f"nudge-{index + 1}",
                    message_type="nudge",
                ),
            )
        result = await memory.run_batch_task(
            task, SCOPE, window, history=event_log.history(SCOPE)
        )
        assert result.accepted_count == 1
        assert len(await memory.recall("轻互动", [SCOPE])) == 1
        stored = await memory.store.scan(SCOPE)
        assert len(stored.records) == 1
        assert stored.records[0].kind == "relation"
        assert result.committable_checkpoint is not None
        await checkpoints.save(
            task.checkpoint_key, SCOPE, result.committable_checkpoint
        )

        retry = await memory.run_batch_task(
            task,
            SCOPE,
            window,
            checkpoint=await checkpoints.load(task.checkpoint_key, SCOPE),
            history=event_log.history(SCOPE),
        )
        assert retry.proposals == []
    finally:
        await memory.close()
        await event_log.close()
        await checkpoints.close()
