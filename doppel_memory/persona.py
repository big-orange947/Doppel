"""Persona 材料：结构化组装 + 可替换 renderer（框架不替开发者决定最终 prompt）。

- ``MaterialBundle``：结构化材料（events/background/relations/style_samples/provenance）。
- ``render(renderer)``：默认 DefaultPromptRenderer，可替换（JSON/XML/ChatML/LangChain Document）。
- ``persona_preset``：针对常见 IM Agent 场景的 scope 策略（owner_persona 等），
  底层仍是显式 scopes 的通用检索。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from doppel_memory.models import MemoryScope, RecallResult
from doppel_memory.retriever import Retriever


class PromptRenderer(Protocol):
    def render(self, bundle: MaterialBundle) -> str:
        ...


@dataclass
class MaterialBundle:
    """一次材料装配的结构化结果（接入方自行决定如何消费）。"""

    scope: MemoryScope
    query: str = ""
    events: list[RecallResult] = field(default_factory=list)
    background: list[RecallResult] = field(default_factory=list)
    relations: list[RecallResult] = field(default_factory=list)
    style_samples: list[str] = field(default_factory=list)
    style_summary: str = field(default="")
    provenance: list[dict] = field(default_factory=list)

    def render(self, renderer: PromptRenderer | None = None) -> str:
        renderer = renderer or DefaultPromptRenderer()
        return renderer.render(self)


class DefaultPromptRenderer:
    """默认模板（可替换）：把材料渲染为可拼进系统 prompt 的文本块。"""

    def render(self, bundle: MaterialBundle) -> str:
        lines: list[str] = ["[号主视角记忆材料]"]
        if bundle.relations:
            lines.append("与对方的关系与称呼：")
            lines.extend(f"- {item.to_line()}" for item in bundle.relations[:3])
        if bundle.background:
            lines.append("背景：")
            lines.extend(f"- {item.to_line()}" for item in bundle.background[:5])
        if bundle.style_summary:
            lines.append(f"号主风格：{bundle.style_summary}")
        if bundle.style_samples:
            lines.append("号主最近原话（学口吻不学内容）：")
            lines.extend(f"- {sample}" for sample in bundle.style_samples)
        if bundle.events:
            lines.append("相关记忆线索（低权威，以实际对话为准）：")
            lines.extend(f"- {item.to_line()}" for item in bundle.events[:8])
        if len(lines) == 1:
            return ""
        return "\n".join(lines)


class ScopePolicy(Protocol):
    """检索 scope 策略：决定"这一轮应该检索哪些 namespace"，框架不硬编码。"""

    def resolve_scopes(
        self, scope: MemoryScope, query: str = ""
    ) -> list[MemoryScope]:
        ...


class OwnerPersonaPolicy:
    """owner_persona preset：会话级 + 联系人级 + 用户全局层。"""

    def resolve_scopes(self, scope: MemoryScope, query: str = "") -> list[MemoryScope]:
        scopes = [scope]
        counterpart = scope.counterpart()
        if counterpart.group_id != scope.group_id:
            scopes.append(counterpart)
        user_scope = scope.user_scope()
        if user_scope.group_id != scope.group_id:
            scopes.append(user_scope)
        return scopes


class PersonaMaterialsBuilder:
    """材料装配器：检索 → 按 kind 分组 → 附风格样本与 provenance。"""

    def __init__(self, retriever: Retriever) -> None:
        self._retriever = retriever

    async def build(
        self,
        scope: MemoryScope,
        query: str = "",
        *,
        scopes: list[MemoryScope] | None = None,
        memory_limit: int = 10,
        style_sample_limit: int = 5,
        policy: ScopePolicy | None = None,
    ) -> MaterialBundle:
        search_scopes = scopes or (policy or OwnerPersonaPolicy()).resolve_scopes(scope, query)
        results = await self._retriever.recall(
            query, search_scopes, limit=memory_limit
        )
        events: list[RecallResult] = []
        background: list[RecallResult] = []
        relations: list[RecallResult] = []
        for item in results:
            if item.kind == "background":
                background.append(item)
            elif item.kind == "relation":
                relations.append(item)
            else:
                events.append(item)
        style_samples: list[str] = []
        if scope.chat_id:
            style_samples = await self._retriever.owner_style_samples(
                scope, limit=style_sample_limit
            )
        provenance = [
            {
                "memory_id": item.memory_id,
                "kind": item.kind,
                "actor": item.actor,
                "authority": item.authority.value if item.authority else "",
                "source_event_id": item.source_event_id,
                "source_message_id": item.source_message_id,
                "extractor": item.extractor,
            }
            for item in results
        ]
        return MaterialBundle(
            scope=scope,
            query=query,
            events=events,
            background=background,
            relations=relations,
            style_samples=style_samples,
            provenance=provenance,
        )
