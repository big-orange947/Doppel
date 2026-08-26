"""Doppel 门面：接入方只和 DoppelClient 打交道。

```python
from doppel_memory import DoppelClient, MemoryScope

memory = DoppelClient(backend="graphiti", neo4j_uri=..., llm_api_key=...)
await memory.ingest_event(scope, msg)          # ① 喂消息
materials = await memory.inject_persona(scope) # ② 拿人格材料
memory.write_background(scope, "km 是产品经理") # ③ 主动背景（可选）
```
"""

from __future__ import annotations

from typing import Any

from doppel_memory.graphiti_store import GraphitiMemoryStore
from doppel_memory.ingestor import Ingestor
from doppel_memory.models import (
    ChatMessage,
    MemoryScope,
    MemorableType,
    RecallResult,
)
from doppel_memory.persona import PersonaInjector, PersonaMaterials
from doppel_memory.retriever import Retriever
from doppel_memory.store import MemoryStore


class DoppelClient:
    """记忆框架统一入口；内存材料提供商，不包含对话引擎职责。"""

    def __init__(
        self,
        store: MemoryStore | None = None,
        *,
        backend: str = "graphiti",
        **backend_kwargs: Any,
    ) -> None:
        if store is None:
            if backend == "graphiti":
                store = GraphitiMemoryStore(**backend_kwargs)
            else:
                raise ValueError(f"unknown backend: {backend!r} (supported: graphiti)")
        self._store = store
        self._ingestor = Ingestor(store)
        self._retriever = Retriever(store)
        self._persona = PersonaInjector(self._retriever)

    @property
    def is_enabled(self) -> bool:
        return self._store.is_enabled

    @property
    def store(self) -> MemoryStore:
        return self._store

    # ---------------------------------------------------------------- 写入

    async def ingest_event(self, scope: MemoryScope, message: ChatMessage) -> str:
        """写入一条聊天事件（自动记忆，幂等）。"""
        return await self._ingestor.ingest_event(scope, message)

    async def ingest_messages(
        self,
        scope: MemoryScope,
        messages: list[ChatMessage],
        *,
        progress=None,
    ) -> dict[str, Any]:
        """批量导入历史聊天记录并自动记忆（冷启动）。"""
        return await self._ingestor.ingest_messages(scope, messages, progress=progress)

    async def write_background(
        self,
        scope: MemoryScope,
        content: str,
        tags: list[str] | None = None,
        *,
        importance: float = 0.5,
        source: str = "manual",
    ) -> str:
        """主动注入聊天以外的号主背景。"""
        return await self._store.write_background(
            scope, content, tags, importance=importance, source=source
        )

    async def write_relation(
        self,
        scope: MemoryScope,
        *,
        counterpart: str,
        relationship: str = "",
        address: str = "",
        communication_preference: str = "",
    ) -> str:
        """写入与某人的关系记忆。"""
        return await self._store.write_relation(
            scope,
            counterpart=counterpart,
            relationship=relationship,
            address=address,
            communication_preference=communication_preference,
        )

    # ---------------------------------------------------------------- 检索

    async def recall(
        self,
        query: str,
        scopes: list[MemoryScope],
        *,
        limit: int = 10,
        kinds: set[MemorableType] | None = None,
    ) -> list[RecallResult]:
        """语义+时间+scope 隔离检索（scopes 必须显式给出）。"""
        return await self._retriever.recall(query, scopes, limit=limit, kinds=kinds)

    async def inject_persona(
        self,
        scope: MemoryScope,
        query: str = "",
        *,
        memory_limit: int = 10,
        style_sample_limit: int = 5,
    ) -> PersonaMaterials:
        """生成回复前拿"号主视角"记忆材料。"""
        return await self._persona.inject(
            scope,
            query,
            memory_limit=memory_limit,
            style_sample_limit=style_sample_limit,
        )

    async def owner_style_samples(self, scope: MemoryScope, *, limit: int = 5) -> list[str]:
        return await self._retriever.owner_style_samples(scope, limit=limit)

    # ---------------------------------------------------------------- 管理

    async def forget(self, memory_id: str) -> bool:
        return await self._store.forget(memory_id)

    async def health(self) -> dict[str, Any]:
        return await self._store.health()

    async def close(self) -> None:
        close = getattr(self._store, "close", None)
        if callable(close):
            await close()
