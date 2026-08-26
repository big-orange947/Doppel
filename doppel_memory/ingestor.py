"""事件摄入：逐条实时写入 + 批量导入历史聊天记录（自动记忆）。

与实时管线共用同一批存储接口，行为一致；批量导入按 message_id/event_id 幂等。
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from doppel_memory.models import ChatMessage, MemoryScope
from doppel_memory.store import MemoryStore

logger = logging.getLogger(__name__)


class Ingestor:
    """把归一化消息写进记忆库的入口（接入方只调它，不直接碰后端）。"""

    def __init__(self, store: MemoryStore, *, batch_size: int = 8) -> None:
        self._store = store
        self._batch_size = max(1, batch_size)

    @property
    def store(self) -> MemoryStore:
        return self._store

    async def ingest_event(self, scope: MemoryScope, message: ChatMessage) -> str:
        """写入一条实时聊天事件；重复消息（同 identity_key）自动跳过。"""
        return await self._store.write_event(scope, message)

    async def ingest_messages(
        self,
        scope: MemoryScope,
        messages: list[ChatMessage],
        *,
        progress: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        """批量导入一段聊天记录并自动记忆（冷启动/历史迁移）。

        - 与 ``ingest_event`` 共用写入逻辑与幂等键。
        - 按 batch_size 分批，避免长记录一次写入占用过大。
        - ``progress(done, total)`` 报告进度；返回 {accepted, skipped, batchCount}。
        """
        accepted = 0
        skipped = 0
        batch_count = 0
        total = len(messages)
        for start in range(0, total, self._batch_size):
            batch = messages[start : start + self._batch_size]
            batch_count += 1
            for message in batch:
                memory_id = await self._store.write_event(scope, message)
                if memory_id:
                    accepted += 1
                else:
                    skipped += 1
            if progress:
                progress(min(start + len(batch), total), total)
        return {"accepted": accepted, "skipped": skipped, "batchCount": batch_count}
