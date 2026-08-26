"""检索召回：语义 + 时间 + scope 隔离（强制 scopes 白名单）。

框架不提供"无 scope 全库检索"：scopes 为空直接抛 MemoryIsolationError。
"""

from __future__ import annotations

from doppel_memory.models import (
    MemoryFilter,
    MemoryIsolationError,
    MemoryScope,
    RecallResult,
)
from doppel_memory.store import MemoryStore


class Retriever:
    """记忆召回门面：校验作用域后转发存储后端。"""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def recall(
        self,
        query: str,
        scopes: list[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> list[RecallResult]:
        if not scopes:
            raise MemoryIsolationError(
                "recall requires explicit scopes (e.g. [conversation_scope, user_scope]); "
                "Doppel refuses unscoped search to prevent memory leaking across users/sessions."
            )
        return await self._store.search(query, scopes, filters=filters, limit=limit)

    async def owner_style_samples(
        self, scope: MemoryScope, *, limit: int = 5
    ) -> list[str]:
        """读取会话内最近 N 条号主本人原话（风格 few-shot 样本）。"""
        messages = await self._store.list_recent_owner_messages(scope, limit=limit)
        return [message.text for message in messages if message.text]
