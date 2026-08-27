"""Mine owner text style from an external event log into persona materials.

Run from the repository root:

    python examples/style_mining.py
"""

from __future__ import annotations

import asyncio

from doppel_memory import (
    Actor,
    ChatMessage,
    DoppelClient,
    HistoryWindow,
    MemoryScope,
    StyleMiner,
    StyleMinerConfig,
)
from examples.batch_runtime import SQLiteCheckpointStore, SQLiteEventLog


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
    task = StyleMiner(
        StyleMinerConfig(
            min_messages=5,
            page_size=3,
            min_phrase_messages=2,
            min_phrase_ratio=0.3,
        )
    )
    window = HistoryWindow(
        start="2026-08-01T00:00:00Z",
        end="2026-09-01T00:00:00Z",
    )
    messages = [
        ChatMessage.of(
            Actor.OWNER,
            "哈哈可以！",
            "2026-08-01T10:00:00Z",
            event_id="style-1",
        ),
        ChatMessage.of(
            Actor.OWNER,
            "哈哈，晚点聊？",
            "2026-08-02T10:00:00Z",
            event_id="style-2",
        ),
        ChatMessage.of(
            Actor.CONTACT,
            "这条联系人消息不会参与号主风格",
            "2026-08-03T10:00:00Z",
            event_id="style-3",
        ),
        ChatMessage.of(
            Actor.OWNER,
            "收到哈哈",
            "2026-08-04T10:00:00Z",
            event_id="style-4",
        ),
        ChatMessage.of(
            Actor.OWNER,
            "可以的😊",
            "2026-08-05T10:00:00Z",
            event_id="style-5",
        ),
        ChatMessage.of(
            Actor.OWNER,
            "哈哈\n没问题",
            "2026-08-06T10:00:00Z",
            event_id="style-6",
        ),
        # Non-text protocol events remain transient inputs and are ignored by default.
        ChatMessage.of(
            Actor.OWNER,
            "",
            "2026-08-07T10:00:00Z",
            event_id="style-7",
            message_type="nudge",
        ),
    ]

    try:
        for message in messages:
            await event_log.append(scope, message)

        checkpoint = await checkpoints.load(task.checkpoint_key, scope)
        result = await memory.run_batch_task(
            task,
            scope,
            window,
            checkpoint=checkpoint,
            history=event_log.history(scope),
            run_id="style-example-1",
        )
        if result.committable_checkpoint is not None:
            await checkpoints.save(
                task.checkpoint_key, scope, result.committable_checkpoint
            )

        materials = await memory.materials(scope, query="今天聊什么")
        print("style profile:", materials.style_summary)
        print(materials.render())
    finally:
        await memory.close()
        await event_log.close()
        await checkpoints.close()


if __name__ == "__main__":
    asyncio.run(main())
