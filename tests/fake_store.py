"""测试用内存 FakeStore：实现 MemoryStore 接口，验证隔离语义与幂等逻辑。"""

from __future__ import annotations

from typing import Any

from doppel_memory.models import (
    ChatMessage,
    MemoryScope,
    MemorableType,
    RecallResult,
)
from doppel_memory.store import MemoryStore


class FakeStore(MemoryStore):
    """内存后端：超小实现，用于隔离/幂等/注入单测（无需 Neo4j/LLM）。"""

    def __init__(self) -> None:
        self.events: list[tuple[MemoryScope, ChatMessage]] = []
        self.backgrounds: list[tuple[MemoryScope, str, list[str]]] = []
        self.relations: list[tuple[MemoryScope, dict[str, str]]] = []
        self.forgotten: list[str] = []
        self._seen: dict[str, set[str]] = {}

    @property
    def is_enabled(self) -> bool:
        return True

    async def write_event(self, scope: MemoryScope, message: ChatMessage) -> str:
        key = message.identity_key
        group = scope.group_id
        if key:
            seen = self._seen.setdefault(group, set())
            if key in seen:
                return ""
            seen.add(key)
        real_scope = scope if scope.chat_id else scope
        self.events.append((real_scope, message))
        return f"evt:{len(self.events)}"

    async def write_background(
        self,
        scope: MemoryScope,
        content: str,
        tags: list[str] | None = None,
        *,
        importance: float = 0.5,
        source: str = "manual",
    ) -> str:
        self.backgrounds.append((scope, content, tags or []))
        return f"bg:{len(self.backgrounds)}"

    async def write_relation(
        self,
        scope: MemoryScope,
        *,
        counterpart: str,
        relationship: str = "",
        address: str = "",
        communication_preference: str = "",
    ) -> str:
        self.relations.append(
            (scope, {"counterpart": counterpart, "relationship": relationship})
        )
        return f"rel:{len(self.relations)}"

    async def recall(
        self,
        query: str,
        scopes: list[MemoryScope],
        *,
        limit: int = 10,
        kinds: set[MemorableType] | None = None,
    ) -> list[RecallResult]:
        if not scopes:
            from doppel_memory.models import MemoryIsolationError

            raise MemoryIsolationError("scopes required")
        allowed = {scope.group_id for scope in scopes}
        hits: list[RecallResult] = []
        for scope, message in self.events:
            if scope.group_id not in allowed:
                continue
            if not query or query in message.text:
                hits.append(
                    RecallResult(
                        fact=message.text,
                        kind=MemorableType.EVENT,
                        scope=scope,
                        source_event_id=message.event_id,
                    )
                )
        for scope, content, tags in self.backgrounds:
            if scope.group_id not in allowed:
                continue
            if not query or query in content:
                hits.append(
                    RecallResult(fact=content, kind=MemorableType.BACKGROUND, scope=scope)
                )
        return hits[:limit]

    async def list_recent_owner_messages(
        self, scope: MemoryScope, *, limit: int = 5
    ) -> list[ChatMessage]:
        samples = [
            message
            for event_scope, message in self.events
            if event_scope.group_id == scope.group_id and message.actor.value == "owner"
        ]
        return samples[-limit:]

    async def forget(self, memory_id: str) -> bool:
        self.forgotten.append(memory_id)
        return True

    async def health(self) -> dict[str, Any]:
        return {"enabled": True, "ok": True}
