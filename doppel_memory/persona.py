"""Persona 材料：结构化组装 + 可替换 renderer（框架不替开发者决定最终 prompt）。

- ``MaterialBundle``：结构化材料（events/background/relations/style profile/guidance/provenance）。
- ``render(renderer)``：默认 DefaultPromptRenderer，可替换（JSON/XML/ChatML/LangChain Document）。
- ``persona_preset``：针对常见 IM Agent 场景的 scope 策略（owner_persona 等），
  底层仍是显式 scopes 的通用检索。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from doppel_memory.models import MemoryFilter, MemoryKind, MemoryScope, RecallResult
from doppel_memory.retriever import Retriever
from doppel_memory.store import MemoryStore
from doppel_memory.style import StyleGuidance, StyleGuideCompiler, StyleProfile


class PromptRenderer(Protocol):
    def render(self, bundle: MaterialBundle) -> str: ...


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
    provenance: list[dict[str, Any]] = field(default_factory=list)
    style_profile: StyleProfile | None = None
    style_guidance: StyleGuidance | None = None

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
        if bundle.style_guidance is not None and bundle.style_guidance.prompt:
            lines.append(bundle.style_guidance.prompt)
        elif bundle.style_summary:
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
    ) -> list[MemoryScope]: ...


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
    """材料装配器：检索 → 分组 → 可选风格编译 → provenance。"""

    def __init__(
        self, retriever: Retriever, *, store: MemoryStore | None = None
    ) -> None:
        self._retriever = retriever
        self._store = store

    async def build(
        self,
        scope: MemoryScope,
        query: str = "",
        *,
        scopes: list[MemoryScope] | None = None,
        memory_limit: int = 10,
        style_sample_limit: int = 5,
        policy: ScopePolicy | None = None,
        style_professor: StyleGuideCompiler | None = None,
    ) -> MaterialBundle:
        search_scopes = (
            scopes
            if scopes is not None
            else (policy or OwnerPersonaPolicy()).resolve_scopes(scope, query)
        )
        results = await self._retriever.recall(query, search_scopes, limit=memory_limit)
        style_results = [
            item
            for item in await self._retriever.recall(
                "",
                search_scopes,
                filters=MemoryFilter(kinds={MemoryKind.STYLE}),
                limit=1,
            )
            if item.kind == MemoryKind.STYLE
        ]
        events: list[RecallResult] = []
        background: list[RecallResult] = []
        relations: list[RecallResult] = []
        for item in results:
            if item.kind == "background":
                background.append(item)
            elif item.kind == "relation":
                relations.append(item)
            elif item.kind == MemoryKind.STYLE:
                continue
            else:
                events.append(item)
        style_samples: list[str] = []
        if scope.chat_id:
            style_samples = await self._retriever.owner_style_samples(
                scope, limit=style_sample_limit
            )
        provenance_results = list(results)
        known_memory_ids = {item.memory_id for item in provenance_results}
        provenance_results.extend(
            item for item in style_results if item.memory_id not in known_memory_ids
        )
        provenance = [
            {
                "memory_id": item.memory_id,
                "scope_key": item.scope.scope_key if item.scope else "",
                "kind": item.kind,
                "actor": item.actor,
                "authority": item.authority.value if item.authority else "",
                "state": item.state.value,
                "source_event_id": item.source_event_id,
                "source_message_id": item.source_message_id,
                "source_episode": item.source_episode,
                "extractor": item.extractor,
                "extracted_at": item.extracted_at.isoformat()
                if item.extracted_at
                else "",
            }
            for item in provenance_results
        ]
        style_profile: StyleProfile | None = None
        style_guidance: StyleGuidance | None = None
        if style_results and self._store is not None:
            style_result = style_results[0]
            if style_result.scope is not None and style_result.memory_id:
                style_record = await self._store.get(
                    style_result.scope, style_result.memory_id
                )
                if style_record is not None:
                    raw_profile = style_record.metadata.get("style_profile")
                    if raw_profile is not None:
                        try:
                            style_profile = StyleProfile.model_validate(raw_profile)
                        except Exception:  # noqa: BLE001 - legacy/custom style metadata
                            style_profile = None
        if style_profile is not None and style_professor is not None:
            style_guidance = StyleGuidance.model_validate(
                style_professor.compile(style_profile)
            )
        return MaterialBundle(
            scope=scope,
            query=query,
            events=events,
            background=background,
            relations=relations,
            style_samples=style_samples,
            style_summary=style_results[0].fact if style_results else "",
            provenance=provenance,
            style_profile=style_profile,
            style_guidance=style_guidance,
        )
