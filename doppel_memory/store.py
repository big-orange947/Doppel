"""MemoryStore 抽象接口：存储后端只需实现这些方法。

Doppel 是"记忆材料提供商"：接口只承诺记忆的写/读/查/删，
不接触对话路由、回复生成或短期上下文窗口（那是接入方的事）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from doppel_memory.models import (
    BackgroundFact,
    ChatMessage,
    MemoryScope,
    MemorableType,
    RecallResult,
    RelationFact,
    StyleProfile,
)


class MemoryStore(ABC):
    """记忆存储后端接口（Graphiti/Neo4j 为首个实现，可替换 SQLite/向量/PG）。"""

    # ---------------------------------------------------------------- 写入

    @abstractmethod
    async def write_event(self, scope: MemoryScope, message: ChatMessage) -> str:
        """把一条聊天事件写入记忆库，返回记忆 ID（幂等：同 identity_key 只写一次）。"""

    @abstractmethod
    async def write_background(
        self,
        scope: MemoryScope,
        content: str,
        tags: list[str] | None = None,
        *,
        importance: float = 0.5,
        source: str = "manual",
    ) -> str:
        """主动注入聊天以外的号主背景（用户级 scope 或会话级 scope）。"""

    @abstractmethod
    async def write_relation(
        self,
        scope: MemoryScope,
        *,
        counterpart: str,
        relationship: str = "",
        address: str = "",
        communication_preference: str = "",
    ) -> str:
        """写入与某人的关系记忆（称呼/关系/沟通偏好）。"""

    # ---------------------------------------------------------------- 检索

    @abstractmethod
    async def recall(
        self,
        query: str,
        scopes: list[MemoryScope],
        *,
        limit: int = 10,
        kinds: set[MemorableType] | None = None,
    ) -> list[RecallResult]:
        """语义+时间+scope 隔离检索。

        ``scopes`` 必须非空且都显式传入；框架不提供"无 scope 全库检索"。
        越权/空 scope 直接抛 MemoryIsolationError。
        """

    @abstractmethod
    async def list_recent_owner_messages(
        self, scope: MemoryScope, *, limit: int = 5
    ) -> list[ChatMessage]:
        """读取会话内最近 N 条号主本人（owner）消息，作为风格 few-shot 样本。"""

    # ---------------------------------------------------------------- 状态

    @abstractmethod
    async def forget(self, memory_id: str) -> bool:
        """删除/软删一条记忆。"""

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        """后端健康状态（接入方用于降级判断）。"""

    @property
    @abstractmethod
    def is_enabled(self) -> bool:
        """未启用时调用方应降级为无记忆，不阻塞对话。"""
