"""Doppel 核心数据模型：scope 隔离、归一化消息、开放式记忆类型。

设计原则（v0.2 修订）：
- 一切记忆以 ``MemoryScope`` 为第一隔离键；写入/检索必须携带 scope。
- ``actor`` 区分说话人（owner/contact/agent/system），开发者可扩展。
- 记忆类型开放式：内置常量是标准协议，自定义类型可透传与过滤。
- 所有记忆可溯源（provenance）：原消息 → 事件 → 提取器 → 记录。
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ActorType(str, Enum):
    """消息/记忆的说话人类型（开发者可扩展为自定义字符串，见 ``ActorOf``）。"""

    OWNER = "owner"  # 号主本人（风格样本的唯一来源）
    CONTACT = "contact"  # 联系人/对方
    AGENT = "agent"  # 机器人代理代发
    SYSTEM = "system"  # 系统事件

    @classmethod
    def normalize(cls, raw: str | ActorType | None) -> ActorType:
        if isinstance(raw, cls):
            return raw
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


class Actor(str):
    """说话人字符串：内置类型 + 开发者自定义透传（如 ``"moderator"``）。"""

    OWNER = ActorType.OWNER.value
    CONTACT = ActorType.CONTACT.value
    AGENT = ActorType.AGENT.value
    SYSTEM = ActorType.SYSTEM.value


class FactAuthority(str, Enum):
    """记忆/事件的事实权威：决定能否作为现实证据与风格样本。"""

    HUMAN_SELF = "human_self"  # 号主本人陈述：高权威 + 风格样本
    PEER_STATEMENT = "peer_statement"  # 联系人陈述：低权威（需交叉确认）
    AGENT_OUTPUT = "agent_output"  # 代理代发：不作为证据、不作为风格样本
    DERIVED_SUMMARY = "derived_summary"  # 派生摘要：仅衔接

    @classmethod
    def of(cls, actor: str | ActorType) -> FactAuthority:
        normalized = ActorType.normalize(actor)
        if normalized is ActorType.OWNER:
            return cls.HUMAN_SELF
        if normalized is ActorType.CONTACT:
            return cls.PEER_STATEMENT
        if normalized is ActorType.AGENT:
            return cls.AGENT_OUTPUT
        return cls.DERIVED_SUMMARY


class MemoryKind:
    """开放式记忆类型：内置常量是标准协议，自定义类型可透传与过滤。

    例如：``MemoryKind("my_project.custom_kind")``。
    """

    EVENT = "event"
    BACKGROUND = "background"
    RELATION = "relation"
    STYLE = "style"
    FACT = "fact"

    _BUILTIN = {EVENT, BACKGROUND, RELATION, STYLE, FACT}

    @classmethod
    def normalize(cls, raw: str | None) -> str:
        value = str(raw or "").strip().lower()
        if not value:
            return cls.EVENT
        return value if len(value) <= 64 else value[:64]


class MemoryState(str, Enum):
    """记忆生命周期状态（是否人工确认由开发者决定）。"""

    CANDIDATE = "candidate"  # 自动提取，未确认
    CONFIRMED = "confirmed"  # 已确认（入高可信）
    REJECTED = "rejected"  # 已拒绝
    SUPERSEDED = "superseded"  # 被新事实取代
    EXPIRED = "expired"  # 过期


def _normalize_group_token(value: str | None) -> str:
    """规范化为 Graphiti 允许的 group_id（字母数字/短横线/下划线）。"""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", str(value or "").strip())


class MemoryScope(BaseModel):
    """记忆隔离键。

    强类型字段：user_id（owner）+ agent_id + platform + chat_type + chat_id。
    扩展维度：``extra_dimensions``（thread/topic/counterpart 等），透传与过滤可用，
    不进入 group_id（避免既有命名空间被破坏）。

    - 会话级：五元组齐全（事件/风格/关系）。
    - 用户级：只有 user_id + agent_id（背景事实、全局偏好）。
    - 联系人级：platform + chat_type=private + chat_id=对方（counterpart scope）。
    """

    user_id: str
    agent_id: str = ""
    platform: str = ""
    chat_type: str = ""
    chat_id: str = ""
    extra_dimensions: dict[str, str] = Field(default_factory=dict, alias="extraDimensions")

    model_config = {"populate_by_name": True}

    @field_validator("user_id", "agent_id", "platform", "chat_type", "chat_id")
    @classmethod
    def _strip(cls, value: str) -> str:
        return str(value or "").strip()

    @property
    def group_id(self) -> str:
        """图谱命名空间：基于强类型字段的会话级 scope（extra 不参与）。"""
        parts = [self.user_id, self.agent_id, self.platform, self.chat_type, self.chat_id]
        return _normalize_group_token(":".join(part for part in parts if part))

    @property
    def is_user_scope(self) -> bool:
        return not (self.platform or self.chat_type or self.chat_id)

    def user_scope(self) -> MemoryScope:
        return MemoryScope(user_id=self.user_id, agent_id=self.agent_id)

    def conversation(self) -> MemoryScope:
        """会话级 scope（self 即会话时返回自身）。"""
        return self

    def counterpart(self) -> MemoryScope:
        """联系人级 scope：私聊对方，或从 chat_id 推导。"""
        if self.chat_type == "private" and self.chat_id:
            return MemoryScope(
                user_id=self.user_id,
                agent_id=self.agent_id,
                platform=self.platform,
                chat_type="contact",
                chat_id=self.chat_id,
            )
        return self.with_chat(self.platform, "contact", self.chat_id) if self.chat_id else self

    def with_chat(self, platform: str, chat_type: str, chat_id: str) -> MemoryScope:
        return MemoryScope(
            user_id=self.user_id,
            agent_id=self.agent_id,
            platform=platform,
            chat_type=chat_type,
            chat_id=chat_id,
        )

    def with_dimension(self, key: str, value: str) -> MemoryScope:
        dims = dict(self.extra_dimensions)
        dims[key] = value
        return MemoryScope(
            user_id=self.user_id,
            agent_id=self.agent_id,
            platform=self.platform,
            chat_type=self.chat_type,
            chat_id=self.chat_id,
            extra_dimensions=dims,
        )

    def matches(self, other: MemoryScope) -> bool:
        """scope 归属判断：other 的所有非空强类型字段必须与 self 一致。"""
        if self.user_id != other.user_id or self.agent_id != other.agent_id:
            return False
        for attr in ("platform", "chat_type", "chat_id"):
            mine = getattr(self, attr)
            theirs = getattr(other, attr)
            if theirs and mine != theirs:
                return False
        return True

    def describe(self) -> str:
        return self.group_id or f"{self.user_id}:{self.agent_id}"


class ChatMessage(BaseModel):
    """归一化聊天消息（IM 标准化：说话人/标识/时间/消息关系/附件元数据）。"""

    actor: ActorType = ActorType.SYSTEM
    text: str = ""
    at: str = Field(default="", description="ISO-8601 时间（with timezone）")
    event_id: str = Field(default="", description="统一事件 ID（幂等键之一）")
    message_id: str = Field(default="", description="平台消息 ID（幂等键之一）")
    message_type: str = Field(default="message", description="message/image/file/reply...")
    reply_to_id: str = Field(default="", description="被回复的消息 ID（IM 回复关系）")
    quoted_message_id: str = Field(default="", description="引用的消息 ID")
    attachments: list[dict[str, Any]] = Field(default_factory=list, description="附件元数据")
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
        message_type: str = "message",
        reply_to_id: str = "",
        quoted_message_id: str = "",
        attachments: list[dict[str, Any]] | None = None,
    ) -> ChatMessage:
        return cls(
            actor=ActorType.normalize(actor),
            text=text,
            at=at,
            event_id=event_id,
            message_id=message_id,
            message_type=message_type,
            reply_to_id=reply_to_id,
            quoted_message_id=quoted_message_id,
            attachments=attachments or [],
        )

    @property
    def identity_key(self) -> str:
        """幂等键：message_id 优先，其次 event_id。"""
        return str(self.message_id or self.event_id or "").strip()

    @property
    def fact_authority(self) -> FactAuthority:
        return FactAuthority.of(self.actor)

    def episode_line(self) -> str:
        authority = self.fact_authority.value
        meta = []
        if self.message_type != "message":
            meta.append(f"type={self.message_type}")
        if self.reply_to_id:
            meta.append(f"reply={self.reply_to_id}")
        if self.quoted_message_id:
            meta.append(f"quote={self.quoted_message_id}")
        meta_part = f" {' '.join(meta)}" if meta else ""
        return (
            f"[actor={self.actor.value} authority={authority} at={self.at}{meta_part}] {self.text}"
            + (f" [attachments={len(self.attachments)}]" if self.attachments else "")
        )


class MemoryRecord(BaseModel):
    """统一记忆记录：所有后端写入返回的结构（带生命周期与溯源）。"""

    memory_id: str = ""
    kind: str = MemoryKind.EVENT
    scope: MemoryScope
    content: str = ""
    actor: str = ""
    authority: FactAuthority = FactAuthority.DERIVED_SUMMARY
    state: MemoryState = MemoryState.CONFIRMED
    tags: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    source_event_id: str = Field(default="")
    source_message_id: str = Field(default="")
    extractor: str = Field(default="", description="产生该记忆的提取器/写入器")
    created_at: str = Field(default="")
    updated_at: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryFilter(BaseModel):
    """检索过滤条件（全部可选，None 表示不限）。"""

    kinds: set[str] | None = None
    actors: set[str] | None = None
    authorities: set[FactAuthority] | None = None
    exclude_authorities: set[FactAuthority] | None = None
    exclude_actors: set[str] | None = None
    states: set[MemoryState] | None = None
    tags: set[str] | None = None
    importance_min: float | None = Field(default=None, ge=0.0, le=1.0)
    time_from: str | None = Field(default=None, description="ISO-8601 起（含）")
    time_to: str | None = Field(default=None, description="ISO-8601 止（含）")


class RecallResult(BaseModel):
    """一次检索召回的记忆片段（低权威，仅供上下文线索，带完整 provenance）。"""

    fact: str
    kind: str = MemoryKind.EVENT
    scope: MemoryScope | None = None
    memory_id: str = Field(default="")
    # ---- provenance（可回溯到原始消息/事件/提取器） ----
    actor: str = Field(default="")
    authority: FactAuthority = FactAuthority.DERIVED_SUMMARY
    source_event_id: str = Field(default="")
    source_message_id: str = Field(default="")
    source_episode: str = Field(default="")
    extractor: str = Field(default="", description="提取器/写入器标识")
    extracted_at: str = Field(default="")
    raw_text: str = Field(default="", description="原始消息文本（可溯源）")
    derived_chain: list[str] = Field(default_factory=list, description="派生链路")
    # ---- 时间与相关性 ----
    valid_at: str = Field(default="")
    similarity: float = Field(default=0.0)
    state: MemoryState = MemoryState.CONFIRMED

    def to_line(self) -> str:
        return self.fact.strip()


class StoreCapabilities(BaseModel):
    """后端能力声明：不支持的操作应明确报错，而不是假装成功。"""

    semantic_search: bool = False
    full_text_search: bool = False
    temporal_search: bool = False
    graph_relations: bool = False
    metadata_filter: bool = False
    hard_delete: bool = False
    transactions: bool = False
    reranking: bool = False

    def require(self, capability: str) -> None:
        if not getattr(self, capability, False):
            raise NotImplementedError(
                f"backed does not support capability: {capability} (capabilities={self.model_dump()})"
            )


class MemoryIsolationError(ValueError):
    """检索/写入缺少或越权 scope 时抛出，防止记忆串台。"""
