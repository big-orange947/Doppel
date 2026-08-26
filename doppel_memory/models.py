"""Doppel 核心数据模型：scope 隔离、归一化消息、五类记忆。

设计原则：
- 一切记忆以 ``MemoryScope`` 为第一隔离键；写入/检索必须携带 scope。
- ``actor`` 区分说话人（owner/contact/agent/system），风格只学 owner。
- 所有记忆可溯源到原始消息（event_id / message_id）。
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ActorType(str, Enum):
    """消息/记忆的说话人类型。"""

    OWNER = "owner"  # 号主本人（风格样本的唯一来源）
    CONTACT = "contact"  # 联系人/对方
    AGENT = "agent"  # 机器人代理代发
    SYSTEM = "system"  # 系统事件

    @classmethod
    def normalize(cls, raw: str | None) -> ActorType:
        value = str(raw or "").strip().upper()
        mapping = {
            "OWNER": cls.OWNER,
            "HUMAN_SELF": cls.OWNER,
            "CONTACT": cls.CONTACT,
            "PEER": cls.CONTACT,
            "AGENT": cls.AGENT,
            "SYSTEM": cls.SYSTEM,
            "INTERNAL": cls.SYSTEM,
        }
        return mapping.get(value, cls.SYSTEM)


class FactAuthority(str, Enum):
    """记忆/事件的事实权威：决定能否作为现实证据与风格样本。"""

    HUMAN_SELF = "human_self"  # 号主本人陈述：高权威 + 风格样本
    PEER_STATEMENT = "peer_statement"  # 联系人陈述：低权威（需交叉确认）
    AGENT_OUTPUT = "agent_output"  # 代理代发：不作为证据、不作为风格样本
    DERIVED_SUMMARY = "derived_summary"  # 派生摘要：仅衔接

    @classmethod
    def of(cls, actor: ActorType) -> FactAuthority:
        if actor is ActorType.OWNER:
            return cls.HUMAN_SELF
        if actor is ActorType.CONTACT:
            return cls.PEER_STATEMENT
        if actor is ActorType.AGENT:
            return cls.AGENT_OUTPUT
        return cls.DERIVED_SUMMARY


class MemorableType(str, Enum):
    EVENT = "event"
    BACKGROUND = "background"
    RELATION = "relation"
    STYLE = "style"
    FACT = "fact"


def _normalize_group_token(value: str | None) -> str:
    """规范化为 Graphiti 允许的 group_id（字母数字/短横线/下划线）。"""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", str(value or "").strip())


class MemoryScope(BaseModel):
    """记忆隔离键：user_id + agent_id + platform + chat_type + chat_id。

    - 会话级：五元组齐全（事件/风格/关系）。
    - 用户级：只有 user_id + agent_id（背景事实、全局偏好）。
    """

    user_id: str
    agent_id: str = ""
    platform: str = ""
    chat_type: str = ""
    chat_id: str = ""

    @field_validator("user_id", "agent_id", "platform", "chat_type", "chat_id")
    @classmethod
    def _strip(cls, value: str) -> str:
        return str(value or "").strip()

    @property
    def group_id(self) -> str:
        """图谱命名空间：会话级 scope 归一化。"""
        parts = [
            self.user_id,
            self.agent_id,
            self.platform,
            self.chat_type,
            self.chat_id,
        ]
        return _normalize_group_token(":".join(part for part in parts if part))

    @property
    def is_user_scope(self) -> bool:
        """是否用户级（只有 user/agent，无会话维度）。"""
        return not (self.platform or self.chat_type or self.chat_id)

    def user_scope(self) -> MemoryScope:
        """返回同用户/账号的用户级 scope（全局层检索用）。"""
        return MemoryScope(user_id=self.user_id, agent_id=self.agent_id)

    def with_chat(self, platform: str, chat_type: str, chat_id: str) -> MemoryScope:
        """在用户级 scope 上补全会话维度。"""
        return MemoryScope(
            user_id=self.user_id,
            agent_id=self.agent_id,
            platform=platform,
            chat_type=chat_type,
            chat_id=chat_id,
        )

    def describe(self) -> str:
        return self.group_id or f"{self.user_id}:{self.agent_id}"


class ChatMessage(BaseModel):
    """归一化聊天消息（接入方负责把平台消息转成此结构）。"""

    actor: ActorType = ActorType.SYSTEM
    text: str = ""
    at: str = Field(default="", description="ISO-8601 时间（with timezone）")
    event_id: str = Field(default="", description="统一事件 ID（幂等键之一）")
    message_id: str = Field(default="", description="平台消息 ID（幂等键之一）")
    raw: dict[str, Any] = Field(default_factory=dict, description="平台原始字段（不入图谱正文）")

    @field_validator("text")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return str(value or "").strip()

    @classmethod
    def of(
        cls,
        actor: str | ActorType,
        text: str,
        at: str,
        *,
        event_id: str = "",
        message_id: str = "",
    ) -> ChatMessage:
        return cls(
            actor=ActorType.normalize(actor),
            text=text,
            at=at,
            event_id=event_id,
            message_id=message_id,
        )

    @property
    def identity_key(self) -> str:
        """幂等键：message_id 优先，其次 event_id。"""
        return str(self.message_id or self.event_id or "").strip()

    @property
    def fact_authority(self) -> FactAuthority:
        return FactAuthority.of(self.actor)

    def episode_line(self) -> str:
        """写入图谱的一行正文（带说话人与时间标记）。"""
        authority = self.fact_authority.value
        return f"[actor={self.actor.value} authority={authority} at={self.at}] {self.text}"


class BackgroundFact(BaseModel):
    """主动注入的号主背景（聊天以外）：职业、关系、项目、偏好。"""

    content: str
    tags: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    scope: MemoryScope
    source: str = Field(default="manual", description="manual/console/extract/import")
    memory_id: str = Field(default="")
    created_at: str = Field(default="")


class RelationFact(BaseModel):
    """与某人的关系记忆：称呼、关系、沟通偏好。"""

    counterpart: str = Field(default="", description="对方标识（chat_id/名称）")
    relationship: str = Field(default="", description="前同事/同学/客户...")
    address: str = Field(default="", description="怎么称呼对方")
    communication_preference: str = Field(default="")
    scope: MemoryScope
    memory_id: str = Field(default="")
    created_at: str = Field(default="")


class StyleProfile(BaseModel):
    """号主表达风格画像（S2：StyleMiner 词频 + StyleProfessor 反思）。"""

    scope: MemoryScope
    summary: str = Field(default="", description="风格画像摘要（语气/结构/尺度）")
    catchphrases: list[str] = Field(default_factory=list, description="口头禅 top-N")
    avg_message_length: float = Field(default=0.0)
    punctuation: dict[str, float] = Field(default_factory=dict, description="句号/感叹/问号频率")
    emoji_frequency: float = Field(default=0.0)
    sample_count: int = Field(default=0, description="有效样本数（只计 owner 消息）")
    confirmed: bool = Field(default=False, description="是否已确认生效")
    memory_id: str = Field(default="")
    updated_at: str = Field(default="")

    @property
    def ready(self) -> bool:
        """样本不足时不参与 few-shot 注入（防止失真）。"""
        return self.sample_count >= 30


class RecallResult(BaseModel):
    """一次检索召回的记忆片段（低权威，仅供上下文线索）。"""

    fact: str
    kind: MemorableType = MemorableType.EVENT
    scope: MemoryScope | None = None
    memory_id: str = Field(default="")
    source_event_id: str = Field(default="")
    source_episode: str = Field(default="")
    valid_at: str = Field(default="")
    similarity: float = Field(default=0.0, description="检索相关度（后端提供则填）")

    def to_line(self) -> str:
        return self.fact.strip()


class MemoryIsolationError(ValueError):
    """检索/写入缺少或越权 scope 时抛出，防止记忆串台。"""
