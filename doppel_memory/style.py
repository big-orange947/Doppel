"""Deterministic owner-style mining built on the periodic batch-task protocol."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Sequence
from statistics import median
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from doppel_memory.batch import (
    BatchCheckpoint,
    BatchProposalPlan,
    BatchTaskContext,
)
from doppel_memory.models import (
    Actor,
    ChatMessage,
    FactAuthority,
    MemoryKind,
    MemoryScope,
)
from doppel_memory.processing import MemoryProposal

_EMOJI_RE = re.compile("[\U0001f1e6-\U0001f1ff\U0001f300-\U0001faff\u2600-\u27bf]")
_SEGMENT_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")
_TERMINAL_PUNCTUATION = frozenset("。！？!?…~～")


class StyleMinerConfig(BaseModel):
    """Explicit sampling and feature choices for one StyleMiner identity."""

    model_config = ConfigDict(frozen=True)

    min_messages: int = Field(default=20, ge=1)
    page_size: int = Field(default=500, ge=1)
    accepted_message_types: frozenset[str] = Field(
        default_factory=lambda: frozenset({"message", "text"})
    )
    target_scope: Literal["conversation", "user"] = "conversation"
    short_message_chars: int = Field(default=12, ge=1)
    phrase_ngram_min: int = Field(default=2, ge=1, le=8)
    phrase_ngram_max: int = Field(default=4, ge=1, le=8)
    min_phrase_messages: int = Field(default=3, ge=2)
    min_phrase_ratio: float = Field(default=0.1, gt=0.0, le=1.0)
    max_common_phrases: int = Field(default=8, ge=0, le=50)
    max_source_ids: int = Field(default=100, ge=0, le=2_000)

    @field_validator("accepted_message_types", mode="before")
    @classmethod
    def _normalize_message_types(cls, value: Any) -> frozenset[str]:
        normalized = frozenset(
            str(item or "").strip().lower() for item in (value or ())
        )
        if not normalized or "" in normalized:
            raise ValueError("accepted_message_types must contain non-empty values")
        return normalized

    @model_validator(mode="after")
    def _validate_ngrams(self) -> StyleMinerConfig:
        if self.phrase_ngram_max < self.phrase_ngram_min:
            raise ValueError("phrase_ngram_max must be >= phrase_ngram_min")
        return self

    @property
    def fingerprint(self) -> str:
        values = self.model_dump(mode="json")
        values["accepted_message_types"] = sorted(self.accepted_message_types)
        payload = json.dumps(
            values,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(payload).hexdigest()[:16]


class StyleProfile(BaseModel):
    """Transparent aggregate features; never a claim about user identity or intent."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    analyzer: str
    analyzer_version: str
    message_count: int = Field(ge=1)
    character_count: int = Field(ge=0)
    average_message_length: float = Field(ge=0.0)
    median_message_length: float = Field(ge=0.0)
    short_message_threshold: int = Field(ge=1)
    short_message_ratio: float = Field(ge=0.0, le=1.0)
    question_ratio: float = Field(ge=0.0, le=1.0)
    exclamation_ratio: float = Field(ge=0.0, le=1.0)
    emoji_ratio: float = Field(ge=0.0, le=1.0)
    multiline_ratio: float = Field(ge=0.0, le=1.0)
    terminal_punctuation_ratio: float = Field(ge=0.0, le=1.0)
    common_phrases: list[str] = Field(default_factory=list)
    summary: str


@runtime_checkable
class StyleAnalyzer(Protocol):
    """Replaceable analysis boundary; implementations may call models or services."""

    name: str
    version: str

    async def analyze(
        self,
        messages: Sequence[ChatMessage],
        *,
        config: StyleMinerConfig,
    ) -> StyleProfile | None: ...


class DeterministicStyleAnalyzer:
    """Language-light reference analyzer with inspectable aggregate metrics."""

    name = "doppel.deterministic-style"
    version = "1"

    async def analyze(
        self,
        messages: Sequence[ChatMessage],
        *,
        config: StyleMinerConfig,
    ) -> StyleProfile | None:
        texts = [message.text.strip() for message in messages if message.text.strip()]
        if len(texts) < config.min_messages:
            return None

        lengths = [len(_WHITESPACE_RE.sub("", text)) for text in texts]
        count = len(texts)
        common_phrases = _mine_common_phrases(texts, config)
        values: dict[str, Any] = {
            "schema_version": 1,
            "analyzer": self.name,
            "analyzer_version": self.version,
            "message_count": count,
            "character_count": sum(lengths),
            "average_message_length": round(sum(lengths) / count, 3),
            "median_message_length": round(float(median(lengths)), 3),
            "short_message_threshold": config.short_message_chars,
            "short_message_ratio": _ratio(
                sum(length <= config.short_message_chars for length in lengths), count
            ),
            "question_ratio": _ratio(
                sum("?" in text or "？" in text for text in texts), count
            ),
            "exclamation_ratio": _ratio(
                sum("!" in text or "！" in text for text in texts), count
            ),
            "emoji_ratio": _ratio(
                sum(bool(_EMOJI_RE.search(text)) for text in texts), count
            ),
            "multiline_ratio": _ratio(sum("\n" in text for text in texts), count),
            "terminal_punctuation_ratio": _ratio(
                sum(text[-1] in _TERMINAL_PUNCTUATION for text in texts), count
            ),
            "common_phrases": common_phrases,
        }
        values["summary"] = _render_summary(values)
        return StyleProfile.model_validate(values)


class StyleMiner:
    """Aggregate owner text from one closed history window into a style proposal."""

    name = "doppel.style-miner"
    version = "1"
    checkpoint_schema_version = 1

    def __init__(
        self,
        config: StyleMinerConfig | None = None,
        *,
        analyzer: StyleAnalyzer | None = None,
    ) -> None:
        self.config = config or StyleMinerConfig()
        self.analyzer = analyzer or DeterministicStyleAnalyzer()
        if not str(getattr(self.analyzer, "name", "") or "").strip():
            raise ValueError("style analyzer name must not be empty")
        if not str(getattr(self.analyzer, "version", "") or "").strip():
            raise ValueError("style analyzer version must not be empty")

    @property
    def checkpoint_key(self) -> str:
        """Host key changes with feature, target, or analyzer semantics."""
        return (
            f"{self.name}:{self.version}:{self.config.fingerprint}:"
            f"{self.analyzer.name}:{self.analyzer.version}"
        )

    async def propose(self, context: BatchTaskContext) -> BatchProposalPlan:
        cursor = context.checkpoint.cursor
        messages: list[ChatMessage] = []
        messages_seen = 0
        while True:
            page = await context.history.read(
                cursor=cursor,
                limit=self.config.page_size,
                actors={Actor.OWNER},
                time_from=context.window.start,
                time_to=context.window.end,
            )
            messages_seen += len(page.messages)
            messages.extend(
                message for message in page.messages if self._accepts(message)
            )
            cursor = page.next_cursor
            if not page.has_more:
                break

        profile: StyleProfile | None = None
        if len(messages) >= self.config.min_messages:
            raw_profile = await self.analyzer.analyze(messages, config=self.config)
            if raw_profile is not None:
                profile = StyleProfile.model_validate(raw_profile)
                if (
                    profile.analyzer != self.analyzer.name
                    or profile.analyzer_version != self.analyzer.version
                ):
                    raise ValueError(
                        "style profile analyzer identity does not match the configured "
                        "analyzer"
                    )
                if profile.message_count > len(messages):
                    raise ValueError(
                        "style profile message_count exceeds the supplied messages"
                    )
        proposals: list[MemoryProposal] = []
        if profile is not None:
            target_scope = self._target_scope(context.scope)
            proposals.append(
                MemoryProposal(
                    scope=target_scope,
                    kind=MemoryKind.STYLE,
                    content=profile.summary,
                    actor=Actor.OWNER,
                    authority=FactAuthority.DERIVED_SUMMARY,
                    tags=["style", "owner-style", self.analyzer.name],
                    importance=0.7,
                    idempotency_key=self._idempotency_key(context, target_scope),
                    processor=self.name,
                    processor_version=self.version,
                    created_at=context.window.end,
                    derived_chain=[
                        f"event:{message.identity_key}"
                        for message in messages
                        if message.identity_key
                    ][: self.config.max_source_ids],
                    metadata={
                        "style_profile": profile.model_dump(mode="json"),
                        "window": context.window.model_dump(mode="json"),
                        "source_scope_key": context.scope.scope_key,
                        "config_fingerprint": self.config.fingerprint,
                        "analyzer": self.analyzer.name,
                        "analyzer_version": self.analyzer.version,
                    },
                )
            )

        return BatchProposalPlan(
            proposals=proposals,
            next_checkpoint=BatchCheckpoint(
                cursor=cursor,
                metadata={
                    "window_end": context.window.end.isoformat(),
                    "messages_seen": messages_seen,
                    "eligible_messages": len(messages),
                    "profile_created": profile is not None,
                    "config_fingerprint": self.config.fingerprint,
                    "analyzer": self.analyzer.name,
                    "analyzer_version": self.analyzer.version,
                },
            ),
        )

    def _accepts(self, message: ChatMessage) -> bool:
        return (
            message.actor == Actor.OWNER
            and message.message_type.lower() in self.config.accepted_message_types
            and bool(message.text.strip())
        )

    def _target_scope(self, source_scope: MemoryScope) -> MemoryScope:
        if self.config.target_scope == "user":
            return source_scope.user_scope()
        return source_scope

    def _idempotency_key(
        self, context: BatchTaskContext, target_scope: MemoryScope
    ) -> str:
        payload = json.dumps(
            {
                "analyzer": self.analyzer.name,
                "analyzer_version": self.analyzer.version,
                "config": self.config.fingerprint,
                "source_scope": context.scope.scope_key,
                "target_scope": target_scope.scope_key,
                "window_end": context.window.end.isoformat(),
                "window_start": context.window.start.isoformat(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return f"style:{hashlib.sha256(payload).hexdigest()}"


def _mine_common_phrases(texts: Sequence[str], config: StyleMinerConfig) -> list[str]:
    if config.max_common_phrases == 0:
        return []
    document_frequency: Counter[str] = Counter()
    for text in texts:
        seen: set[str] = set()
        for segment in _SEGMENT_RE.findall(text.lower()):
            for size in range(config.phrase_ngram_min, config.phrase_ngram_max + 1):
                seen.update(
                    segment[index : index + size]
                    for index in range(len(segment) - size + 1)
                )
        document_frequency.update(seen)

    minimum = max(
        config.min_phrase_messages,
        math.ceil(len(texts) * config.min_phrase_ratio),
    )
    candidates = sorted(
        (
            (phrase, frequency)
            for phrase, frequency in document_frequency.items()
            if frequency >= minimum
        ),
        key=lambda item: (-item[1], -len(item[0]), item[0]),
    )
    selected: list[str] = []
    for phrase, _ in candidates:
        if any(phrase in existing or existing in phrase for existing in selected):
            continue
        selected.append(phrase)
        if len(selected) >= config.max_common_phrases:
            break
    return selected


def _ratio(matches: int, total: int) -> float:
    return round(matches / total, 4) if total else 0.0


def _render_summary(values: dict[str, Any]) -> str:
    summary = (
        f"基于 {values['message_count']} 条号主文本：平均 "
        f"{values['average_message_length']:.1f} 字，中位数 "
        f"{values['median_message_length']:.1f} 字，"
        f"不超过 {values['short_message_threshold']} 字占 "
        f"{values['short_message_ratio']:.0%}；问句 "
        f"{values['question_ratio']:.0%}，感叹 "
        f"{values['exclamation_ratio']:.0%}，emoji "
        f"{values['emoji_ratio']:.0%}，多行 "
        f"{values['multiline_ratio']:.0%}，句末标点 "
        f"{values['terminal_punctuation_ratio']:.0%}"
    )
    phrases = values["common_phrases"]
    if phrases:
        summary += "；高频片段：" + "、".join(phrases)
    return summary
