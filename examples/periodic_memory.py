"""Aggregate transient IM events without storing each event as long-term memory.

Run from the repository root:

    python examples/periodic_memory.py
"""

from __future__ import annotations

import asyncio

from doppel_memory import (
    BatchCheckpoint,
    BatchProposalPlan,
    ChatMessage,
    DoppelClient,
    HistoryWindow,
    MemoryFilter,
    MemoryKind,
    MemoryProposal,
    MemoryScope,
)
from examples.batch_runtime import SQLiteCheckpointStore, SQLiteEventLog


class InteractionPatternTask:
    """Example policy; applications choose their own event types and threshold."""

    name = "example.interaction-pattern"
    version = "1"

    def __init__(
        self,
        *,
        message_types: set[str],
        threshold: int,
        page_size: int = 200,
    ) -> None:
        if not message_types:
            raise ValueError("message_types must not be empty")
        if threshold <= 0:
            raise ValueError("threshold must be positive")
        self._message_types = frozenset(message_types)
        self._threshold = threshold
        self._page_size = max(1, page_size)

    @property
    def checkpoint_key(self) -> str:
        """Change the host key whenever history-selection semantics change."""

        type_key = "+".join(sorted(self._message_types))
        return f"{self.name}:{self.version}:{type_key}:threshold={self._threshold}"

    async def propose(self, context) -> BatchProposalPlan:
        cursor = context.checkpoint.cursor
        matching: list[ChatMessage] = []
        while True:
            page = await context.history.read(
                cursor=cursor,
                limit=self._page_size,
                time_from=context.window.start,
                time_to=context.window.end,
            )
            matching.extend(
                message
                for message in page.messages
                if message.message_type in self._message_types
            )
            cursor = page.next_cursor
            if not page.has_more:
                break

        proposals = []
        if len(matching) >= self._threshold:
            type_key = "+".join(sorted(self._message_types))
            proposals.append(
                MemoryProposal(
                    scope=context.scope,
                    kind=MemoryKind.RELATION,
                    content=f"本窗口发生 {len(matching)} 次轻互动",
                    processor=self.name,
                    processor_version=self.version,
                    idempotency_key=(
                        f"interaction:{type_key}:"
                        f"{context.window.start.isoformat()}:"
                        f"{context.window.end.isoformat()}"
                    ),
                    created_at=context.window.end,
                    derived_chain=[
                        f"event:{message.identity_key}"
                        for message in matching
                        if message.identity_key
                    ],
                    metadata={
                        "event_count": len(matching),
                        "message_types": sorted(self._message_types),
                    },
                )
            )
        return BatchProposalPlan(
            proposals=proposals,
            next_checkpoint=BatchCheckpoint(
                cursor=cursor,
                metadata={"window_end": context.window.end.isoformat()},
            ),
        )


async def main() -> None:
    memory = DoppelClient(backend="memory")
    event_log = SQLiteEventLog()
    checkpoints = SQLiteCheckpointStore()
    scope = MemoryScope(
        user_id="u1",
        agent_id="qq-bot",
        platform="qq",
        chat_type="private",
        chat_id="10001",
    )
    task = InteractionPatternTask(message_types={"nudge"}, threshold=3, page_size=2)
    window = HistoryWindow(
        start="2026-08-26T00:00:00Z",
        end="2026-08-27T00:00:00Z",
    )

    try:
        # These protocol events live only in the application's event log.
        for index in range(3):
            await event_log.append(
                scope,
                ChatMessage.of(
                    "contact",
                    "",
                    f"2026-08-26T0{index + 1}:00:00Z",
                    event_id=f"nudge-{index + 1}",
                    message_type="nudge",
                ),
            )

        checkpoint = await checkpoints.load(task.checkpoint_key, scope)
        result = await memory.run_batch_task(
            task,
            scope,
            window,
            checkpoint=checkpoint,
            history=event_log.history(scope),
            run_id="example-run-1",
        )
        if result.committable_checkpoint is not None:
            await checkpoints.save(
                task.checkpoint_key, scope, result.committable_checkpoint
            )

        relations = await memory.recall(
            "轻互动",
            [scope],
            filters=MemoryFilter(kinds={MemoryKind.RELATION}),
        )
        print("long-term memories:", [item.fact for item in relations])

        # A retry resumes after the durable watermark and proposes nothing.
        retry = await memory.run_batch_task(
            task,
            scope,
            window,
            checkpoint=await checkpoints.load(task.checkpoint_key, scope),
            history=event_log.history(scope),
            run_id="example-run-2",
        )
        print("retry proposals:", len(retry.proposals))
    finally:
        await memory.close()
        await event_log.close()
        await checkpoints.close()


if __name__ == "__main__":
    asyncio.run(main())
