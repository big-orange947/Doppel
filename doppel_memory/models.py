"""Doppel public data models and backend-neutral protocol values."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Never, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return value.astimezone(UTC)


class ActorType(str, Enum):
    """Built-in IM speaker roles."""

    OWNER = "owner"
    CONTACT = "contact"
    AGENT = "agent"
    SYSTEM = "system"

    @classmethod
    def normalize(cls, raw: str | ActorType | None) -> ActorType:
        normalized = Actor.normalize(raw)
        try:
            return cls(normalized)
        except ValueError:
            return cls.SYSTEM


class Actor(str):
    """Open actor identifier with aliases for the built-in roles."""

    OWNER = ActorType.OWNER.value
    CONTACT = ActorType.CONTACT.value
    AGENT = ActorType.AGENT.value
    SYSTEM = ActorType.SYSTEM.value

    @classmethod
    def normalize(cls, raw: str | ActorType | None) -> str:
        value = (
            str(raw.value if isinstance(raw, ActorType) else raw or "").strip().lower()
        )
        aliases = {
            "human_self": cls.OWNER,
            "peer": cls.CONTACT,
            "internal": cls.SYSTEM,
        }
        return aliases.get(value, value or cls.SYSTEM)


class FactAuthority(str, Enum):
    """How strongly a memory may be treated as factual evidence."""

    HUMAN_SELF = "human_self"
    PEER_STATEMENT = "peer_statement"
    AGENT_OUTPUT = "agent_output"
    DERIVED_SUMMARY = "derived_summary"

    @classmethod
    def of(cls, actor: str | ActorType) -> FactAuthority:
        normalized = Actor.normalize(actor)
        if normalized == Actor.OWNER:
            return cls.HUMAN_SELF
        if normalized == Actor.CONTACT:
            return cls.PEER_STATEMENT
        if normalized == Actor.AGENT:
            return cls.AGENT_OUTPUT
        return cls.DERIVED_SUMMARY


class MemoryKind:
    """Open memory kind namespace; custom kinds are normalized strings."""

    EVENT = "event"
    BACKGROUND = "background"
    RELATION = "relation"
    STYLE = "style"
    FACT = "fact"

    @classmethod
    def normalize(cls, raw: str | None) -> str:
        value = str(raw or "").strip().lower()
        return (value or cls.EVENT)[:64]


class MemoryState(str, Enum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


ACTIVE_MEMORY_STATES = frozenset({MemoryState.CANDIDATE, MemoryState.CONFIRMED})


class WriteStatus(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    DUPLICATE = "duplicate"
    SKIPPED = "skipped"
    FAILED = "failed"


class _FrozenDimensions(dict[str, str]):
    """Serializable dict that keeps a frozen scope's identity stable."""

    @staticmethod
    def _immutable(*args: Any, **kwargs: Any) -> Never:
        raise TypeError("MemoryScope.extra_dimensions is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable

    def __copy__(self) -> _FrozenDimensions:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> _FrozenDimensions:
        return self


class MemoryScope(BaseModel):
    """Exact, immutable memory namespace.

    Stores always perform exact matching. Hierarchical expansion belongs to a
    ``ScopePolicy``. Every custom dimension participates in ``scope_key``.
    """

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    user_id: str
    agent_id: str
    platform: str = ""
    chat_type: str = ""
    chat_id: str = ""
    extra_dimensions: dict[str, str] = Field(
        default_factory=dict, serialization_alias="extraDimensions"
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_v02_alias(cls, value: Any) -> Any:
        if (
            isinstance(value, dict)
            and "extraDimensions" in value
            and "extra_dimensions" not in value
        ):
            value = dict(value)
            value["extra_dimensions"] = value.pop("extraDimensions")
        return value

    @field_validator(
        "user_id", "agent_id", "platform", "chat_type", "chat_id", mode="before"
    )
    @classmethod
    def _strip(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("extra_dimensions", mode="before")
    @classmethod
    def _normalize_dimensions(cls, value: Any) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_key, raw_value in dict(value or {}).items():
            key = str(raw_key or "").strip()
            item = str(raw_value or "").strip()
            if not key or not item:
                raise ValueError("extra dimension keys and values must be non-empty")
            normalized[key] = item
        return normalized

    @field_validator("extra_dimensions")
    @classmethod
    def _freeze_dimensions(cls, value: dict[str, str]) -> dict[str, str]:
        return _FrozenDimensions(value)

    @model_validator(mode="after")
    def _validate_shape(self) -> Self:
        if not self.user_id:
            raise ValueError("user_id is required")
        if not self.agent_id:
            raise ValueError("agent_id is required")
        if self.chat_type and not self.platform:
            raise ValueError("chat_type requires platform")
        if self.chat_id and not (self.platform and self.chat_type):
            raise ValueError("chat_id requires platform and chat_type")
        return self

    def _canonical_payload(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "chat_id": self.chat_id,
            "chat_type": self.chat_type,
            "extra_dimensions": dict(sorted(self.extra_dimensions.items())),
            "platform": self.platform,
            "user_id": self.user_id,
        }

    @property
    def scope_key(self) -> str:
        payload = json.dumps(
            self._canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return "dpl_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def group_id(self) -> str:
        """Compatibility alias for graph-oriented backends."""

        return self.scope_key

    @property
    def is_user_scope(self) -> bool:
        return not (
            self.platform or self.chat_type or self.chat_id or self.extra_dimensions
        )

    def user_scope(self) -> MemoryScope:
        return MemoryScope(user_id=self.user_id, agent_id=self.agent_id)

    def conversation(self) -> MemoryScope:
        return self

    def counterpart(self) -> MemoryScope:
        if not self.chat_id:
            return self
        return MemoryScope(
            user_id=self.user_id,
            agent_id=self.agent_id,
            platform=self.platform,
            chat_type="contact",
            chat_id=self.chat_id,
        )

    def with_chat(self, platform: str, chat_type: str, chat_id: str) -> MemoryScope:
        return MemoryScope(
            user_id=self.user_id,
            agent_id=self.agent_id,
            platform=platform,
            chat_type=chat_type,
            chat_id=chat_id,
        )

    def with_dimension(self, key: str, value: str) -> MemoryScope:
        dimensions = dict(self.extra_dimensions)
        dimensions[key] = value
        return MemoryScope(
            user_id=self.user_id,
            agent_id=self.agent_id,
            platform=self.platform,
            chat_type=self.chat_type,
            chat_id=self.chat_id,
            extra_dimensions=dimensions,
        )

    def matches(self, other: MemoryScope) -> bool:
        """Exact identity comparison retained for compatibility."""

        return self.scope_key == other.scope_key

    def describe(self) -> str:
        base = "/".join(
            part
            for part in (
                self.user_id,
                self.agent_id,
                self.platform,
                self.chat_type,
                self.chat_id,
            )
            if part
        )
        if not self.extra_dimensions:
            return base
        suffix = ",".join(
            f"{key}={value}" for key, value in sorted(self.extra_dimensions.items())
        )
        return f"{base}#{suffix}"


class ChatMessage(BaseModel):
    """Normalized IM event. Custom actors are preserved."""

    actor: str = Actor.SYSTEM
    text: str = ""
    at: datetime = Field(default_factory=utc_now)
    event_id: str = ""
    message_id: str = ""
    sender_id: str = ""
    message_type: str = "message"
    reply_to_id: str = ""
    quoted_message_id: str = ""
    thread_id: str = ""
    thread_root_id: str = ""
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("actor", mode="before")
    @classmethod
    def _normalize_actor(cls, value: Any) -> str:
        return Actor.normalize(value)

    @field_validator(
        "text",
        "event_id",
        "message_id",
        "sender_id",
        "message_type",
        "reply_to_id",
        "quoted_message_id",
        "thread_id",
        "thread_root_id",
        mode="before",
    )
    @classmethod
    def _strip_text_fields(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("at")
    @classmethod
    def _normalize_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @classmethod
    def of(
        cls,
        actor: str | ActorType,
        text: str,
        at: str | datetime,
        *,
        event_id: str = "",
        message_id: str = "",
        sender_id: str = "",
        message_type: str = "message",
        reply_to_id: str = "",
        quoted_message_id: str = "",
        thread_id: str = "",
        thread_root_id: str = "",
        attachments: list[dict[str, Any]] | None = None,
        raw: dict[str, Any] | None = None,
    ) -> ChatMessage:
        parsed_at = datetime.fromisoformat(at) if isinstance(at, str) else at
        return cls(
            actor=actor,
            text=text,
            at=parsed_at,
            event_id=event_id,
            message_id=message_id,
            sender_id=sender_id,
            message_type=message_type,
            reply_to_id=reply_to_id,
            quoted_message_id=quoted_message_id,
            thread_id=thread_id,
            thread_root_id=thread_root_id,
            attachments=attachments or [],
            raw=raw or {},
        )

    @property
    def identity_key(self) -> str:
        return self.message_id or self.event_id

    @property
    def fact_authority(self) -> FactAuthority:
        return FactAuthority.of(self.actor)

    def episode_line(self) -> str:
        metadata = [
            f"actor={self.actor}",
            f"authority={self.fact_authority.value}",
            f"at={self.at.isoformat()}",
        ]
        if self.message_type != "message":
            metadata.append(f"type={self.message_type}")
        if self.reply_to_id:
            metadata.append(f"reply={self.reply_to_id}")
        if self.quoted_message_id:
            metadata.append(f"quote={self.quoted_message_id}")
        if self.thread_id:
            metadata.append(f"thread={self.thread_id}")
        if self.thread_root_id:
            metadata.append(f"thread_root={self.thread_root_id}")
        body = f"[{' '.join(metadata)}] {self.text}"
        return body + (
            f" [attachments={len(self.attachments)}]" if self.attachments else ""
        )


class MemoryRecord(BaseModel):
    memory_id: str = ""
    kind: str = MemoryKind.EVENT
    scope: MemoryScope
    content: str = ""
    actor: str = ""
    authority: FactAuthority = FactAuthority.DERIVED_SUMMARY
    state: MemoryState = MemoryState.CONFIRMED
    tags: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    idempotency_key: str = ""
    source_event_id: str = ""
    source_message_id: str = ""
    extractor: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    version: int = Field(default=1, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind", mode="before")
    @classmethod
    def _normalize_kind(cls, value: Any) -> str:
        return MemoryKind.normalize(value)

    @field_validator("actor", mode="before")
    @classmethod
    def _normalize_optional_actor(cls, value: Any) -> str:
        return Actor.normalize(value) if value else ""

    @field_validator("created_at", "updated_at")
    @classmethod
    def _normalize_record_time(cls, value: datetime) -> datetime:
        return _utc(value)


class MemoryPage(BaseModel):
    """One exact-scope page; ``next_cursor`` is the durable read watermark."""

    records: list[MemoryRecord] = Field(default_factory=list)
    next_cursor: str = ""
    has_more: bool = False


class WriteResult(BaseModel):
    status: WriteStatus
    record: MemoryRecord | None = None
    error_code: str | None = None
    message: str | None = None

    @property
    def memory_id(self) -> str:
        return self.record.memory_id if self.record else ""

    @property
    def accepted(self) -> bool:
        return self.status in {WriteStatus.CREATED, WriteStatus.UPDATED}


class MemoryFilter(BaseModel):
    kinds: set[str] | None = None
    actors: set[str] | None = None
    authorities: set[FactAuthority] | None = None
    exclude_authorities: set[FactAuthority] | None = None
    exclude_actors: set[str] | None = None
    states: set[MemoryState] | None = None
    include_inactive: bool = False
    tags: set[str] | None = None
    importance_min: float | None = Field(default=None, ge=0.0, le=1.0)
    time_from: datetime | None = None
    time_to: datetime | None = None

    @field_validator("time_from", "time_to")
    @classmethod
    def _normalize_filter_time(cls, value: datetime | None) -> datetime | None:
        return _utc(value) if value is not None else None


class RecallResult(BaseModel):
    fact: str
    kind: str = MemoryKind.EVENT
    scope: MemoryScope | None = None
    memory_id: str = ""
    actor: str = ""
    authority: FactAuthority = FactAuthority.DERIVED_SUMMARY
    source_event_id: str = ""
    source_message_id: str = ""
    source_episode: str = ""
    extractor: str = ""
    extracted_at: datetime | None = None
    raw_text: str = ""
    derived_chain: list[str] = Field(default_factory=list)
    valid_at: datetime | None = None
    similarity: float = 0.0
    state: MemoryState = MemoryState.CONFIRMED

    def to_line(self) -> str:
        return self.fact.strip()


class StoreCapabilities(BaseModel):
    semantic_search: bool = False
    substring_search: bool = False
    full_text_search: bool = False
    temporal_search: bool = False
    graph_relations: bool = False
    metadata_filter: bool = False
    hard_delete: bool = False
    transactions: bool = False
    reranking: bool = False
    pagination: bool = False

    def require(self, capability: str) -> None:
        if not getattr(self, capability, False):
            raise NotImplementedError(
                f"backend does not support capability: {capability} "
                f"(capabilities={self.model_dump()})"
            )


class MemoryIsolationError(ValueError):
    """A scoped operation was attempted without an explicit valid scope."""


class MemoryStateConflictError(RuntimeError):
    """A lifecycle transition lost an optimistic concurrency race."""
