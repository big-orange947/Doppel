"""MemoryStore 抽象接口：存储后端只需实现这些方法（契约见 tests/store_contract.py）。

Doppel 是"记忆材料提供商"：接口只承诺记忆的写/读/查/删与能力声明，
不接触对话路由、回复生成或短期上下文窗口（那是接入方的事）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from doppel_memory.models import (
    ChatMessage,
    MemoryFilter,
    MemoryRecord,
    MemoryScope,
    RecallResult,
    StoreCapabilities,
)


class MemoryStore(ABC):
    """记忆存储后端接口（InMemory/SQLite/Graphiti 首个实现集，可替换其他后端）。"""

    @property
    @abstractmethod
    def capabilities(self) -> StoreCapabilities:
        """能力声明：支持什么、不支持什么，接入方据此降级或报错。"""

    @property
    @abstractmethod
    def is_enabled(self) -> bool:
        """未启用时调用方应降级为无记忆，不阻塞对话。"""

    # ---------------------------------------------------------------- 写入

    @abstractmethod
    async def write_event(self, scope: MemoryScope, message: ChatMessage) -> MemoryRecord:
        """写入一条聊天事件；同 identity_key（message_id/event_id）幂等，返回空记录跳过。"""

    @abstractmethod
    async def write_background(
        self,
        scope: MemoryScope,
        content: str,
        tags: list[str] | None = None,
        *,
        importance: float = 0.5,
        source: str = "manual",
    ) -> MemoryRecord:
        """主动注入聊天以外的号主背景（用户级或会话级 scope）。"""

    @abstractmethod
    async def write_relation(
        self,
        scope: MemoryScope,
        *,
        counterpart: str,
        relationship: str = "",
        address: str = "",
        communication_preference: str = "",
        attributes: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        """写入与某人的关系记忆（称呼/关系/沟通偏好/属性）。"""

    # ---------------------------------------------------------------- 检索

    @abstractmethod
    async def search(
        self,
        query: str,
        scopes: list[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> list[RecallResult]:
        """检索：scope 必须显式给出（空/越权直接抛 MemoryIsolationError）。"""

    @abstractmethod
    async def list_recent_owner_messages(
        self, scope: MemoryScope, *, limit: int = 5
    ) -> list[ChatMessage]:
        """读取会话内最近 N 条号主本人（owner）消息，作为风格 few-shot 样本。"""

    # ---------------------------------------------------------------- 管理

    @abstractmethod
    async def forget(self, memory_id: str, *, hard: bool = False) -> bool:
        """删除记忆（hard=False 软删/状态标记；不支持 hard delete 的后端应明确报错）。"""

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        """健康状态（接入方用于降级判断）。"""

    # 生命周期与确认的状态转换是可选的；核心协议只承诺以上方法。
