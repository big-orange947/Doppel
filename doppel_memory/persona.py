"""Persona 注入：把记忆材料组装成"号主视角"上下文块。

Doppel 只提供"材料"：how to prompt 由接入方决定（插在哪、多长、优先级）。
``PersonaMaterials.to_prompt_block()`` 是默认模板，可被接入方覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from doppel_memory.models import MemoryScope, RecallResult
from doppel_memory.retriever import Retriever


@dataclass
class PersonaMaterials:
    """一次人格注入的完整材料（记忆属于低权威线索，接入方自行决定权重）。"""

    scope: MemoryScope
    query: str = ""
    memories: list[RecallResult] = field(default_factory=list)
    style_samples: list[str] = field(default_factory=list)
    style_summary: str = field(default="")
    relation: str = field(default="")
    background: list[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        """默认注入模板；风格/关系为空时自动省略对应小节。"""
        lines: list[str] = ["[号主视角记忆材料]"]
        if self.relation:
            lines.append(f"与对方的关系：{self.relation}")
        if self.background:
            lines.append("背景：" + "；".join(self.background))
        if self.style_summary:
            lines.append(f"号主风格：{self.style_summary}")
        if self.style_samples:
            lines.append("号主最近原话（学口吻不学内容）：")
            lines.extend(f"- {sample}" for sample in self.style_samples)
        if self.memories:
            lines.append("相关记忆线索（低权威，需以实际对话为准）：")
            lines.extend(f"- {item.to_line()}" for item in self.memories[:8])
        if len(lines) == 1:
            return ""
        return "\n".join(lines)


class PersonaInjector:
    """生成回复前的记忆材料装配器（S1：线索 + 风格样本；S2 补风格画像）。"""

    def __init__(self, retriever: Retriever) -> None:
        self._retriever = retriever

    async def inject(
        self,
        scope: MemoryScope,
        query: str = "",
        *,
        memory_limit: int = 10,
        style_sample_limit: int = 5,
    ) -> PersonaMaterials:
        memories = await self._retriever.recall(
            query or "", [scope, scope.user_scope()], limit=memory_limit
        )
        style_samples = []
        if scope.chat_id:
            style_samples = await self._retriever.owner_style_samples(
                scope, limit=style_sample_limit
            )
        return PersonaMaterials(
            scope=scope,
            query=query,
            memories=memories,
            style_samples=style_samples,
        )
