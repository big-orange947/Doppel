"""Deterministic owner-style mining built on the periodic batch-task protocol."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Sequence
from statistics import median
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable

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


class StyleProfessorConfig(BaseModel):
    """Safety and output-budget choices for deterministic style guidance."""

    model_config = ConfigDict(frozen=True)

    min_reliable_messages: int = Field(default=20, ge=1)
    full_confidence_messages: int = Field(default=100, ge=1)
    max_prompt_chars: int = Field(default=800, ge=160, le=10_000)
    include_common_phrases: bool = False
    max_common_phrases: int = Field(default=3, ge=0, le=20)
    max_phrase_chars: int = Field(default=12, ge=1, le=100)

    @model_validator(mode="after")
    def _validate_sample_thresholds(self) -> StyleProfessorConfig:
        if self.full_confidence_messages < self.min_reliable_messages:
            raise ValueError(
                "full_confidence_messages must be >= min_reliable_messages"
            )
        return self

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.model_dump(mode="json"))


class StyleDirective(BaseModel):
    """One auditable instruction derived from one observable profile feature."""

    model_config = ConfigDict(frozen=True)

    feature: str
    instruction: str
    evidence: str
    confidence: float = Field(ge=0.0, le=1.0)
    priority: int = Field(ge=0, le=100)

    @field_validator("feature", "instruction", "evidence", mode="before")
    @classmethod
    def _normalize_required_text(cls, value: Any) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("style directive text fields must not be empty")
        return normalized


class StyleGuidance(BaseModel):
    """Bounded generation guidance plus its exact derivation provenance."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    professor: str
    professor_version: str
    profile_fingerprint: str
    config_fingerprint: str
    source_analyzer: str
    source_analyzer_version: str
    source_message_count: int = Field(ge=1)
    usable: bool
    directives: list[StyleDirective] = Field(default_factory=list)
    prompt: str = ""
    omitted_features: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


@runtime_checkable
class StyleGuideCompiler(Protocol):
    """Replaceable pure profile-to-guidance compilation boundary."""

    name: str
    version: str

    def compile(self, profile: StyleProfile) -> StyleGuidance: ...


class StyleProfessor:
    """Compile a StyleProfile into deterministic, bounded writing guidance."""

    name = "doppel.deterministic-style-professor"
    version = "1"

    def __init__(self, config: StyleProfessorConfig | None = None) -> None:
        self.config = config or StyleProfessorConfig()

    def compile(self, profile: StyleProfile) -> StyleGuidance:
        bound_profile = StyleProfile.model_validate(profile)
        profile_fingerprint = _style_profile_fingerprint(bound_profile)
        common = {
            "professor": self.name,
            "professor_version": self.version,
            "profile_fingerprint": profile_fingerprint,
            "config_fingerprint": self.config.fingerprint,
            "source_analyzer": bound_profile.analyzer,
            "source_analyzer_version": bound_profile.analyzer_version,
            "source_message_count": bound_profile.message_count,
        }
        if bound_profile.message_count < self.config.min_reliable_messages:
            return StyleGuidance(
                **common,
                usable=False,
                warnings=[
                    (
                        f"insufficient source messages: {bound_profile.message_count} < "
                        f"{self.config.min_reliable_messages}"
                    )
                ],
            )

        confidence = round(
            min(
                1.0,
                math.sqrt(
                    bound_profile.message_count / self.config.full_confidence_messages
                ),
            ),
            4,
        )
        directives = _profile_directives(bound_profile, self.config, confidence)
        prompt, selected, omitted = _render_guidance(
            directives, max_chars=self.config.max_prompt_chars
        )
        warnings: list[str] = []
        if confidence < 1.0:
            warnings.append(
                "guidance confidence is sample-limited until "
                f"{self.config.full_confidence_messages} source messages"
            )
        if omitted:
            warnings.append(
                "lower-priority directives were omitted by the prompt budget"
            )
        return StyleGuidance(
            **common,
            usable=bool(selected),
            directives=selected,
            prompt=prompt,
            omitted_features=omitted,
            warnings=warnings,
        )


class StyleQualityConfig(BaseModel):
    """Sample sufficiency and pass threshold for black-box output evaluation."""

    model_config = ConfigDict(frozen=True)

    min_candidate_messages: int = Field(default=20, ge=1)
    passing_score: float = Field(default=0.8, ge=0.0, le=1.0)

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.model_dump(mode="json"))


class StyleQualityReport(BaseModel):
    """Independent observable-feature comparison for generated message samples."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    evaluator: str
    evaluator_version: str
    reference_profile_fingerprint: str
    config_fingerprint: str
    candidate_input_count: int = Field(ge=0)
    candidate_message_count: int = Field(ge=0)
    sufficient_samples: bool
    feature_scores: dict[str, float] = Field(default_factory=dict)
    observed: dict[str, float] = Field(default_factory=dict)
    aggregate_score: float = Field(ge=0.0, le=1.0)
    passed: bool
    warnings: list[str] = Field(default_factory=list)


class StyleQualityEvaluator:
    """Score black-box outputs without asking their generator or an LLM to judge."""

    name = "doppel.observable-style-quality"
    version = "1"

    _WEIGHTS: ClassVar[dict[str, float]] = {
        "average_message_length": 0.15,
        "median_message_length": 0.15,
        "short_message_ratio": 0.15,
        "question_ratio": 0.10,
        "exclamation_ratio": 0.10,
        "emoji_ratio": 0.10,
        "multiline_ratio": 0.10,
        "terminal_punctuation_ratio": 0.15,
    }

    def __init__(self, config: StyleQualityConfig | None = None) -> None:
        self.config = config or StyleQualityConfig()

    def evaluate(
        self,
        reference: StyleProfile,
        candidates: Sequence[str | ChatMessage],
    ) -> StyleQualityReport:
        bound_reference = StyleProfile.model_validate(reference)
        texts: list[str] = []
        for candidate in candidates:
            if isinstance(candidate, ChatMessage):
                text = candidate.text
            elif isinstance(candidate, str):
                text = candidate
            else:
                raise TypeError(
                    "style quality candidates must be strings or ChatMessage"
                )
            normalized = text.strip()
            if normalized:
                texts.append(normalized)

        observed = _observed_style_metrics(
            texts, short_threshold=bound_reference.short_message_threshold
        )
        reference_values = {
            "average_message_length": bound_reference.average_message_length,
            "median_message_length": bound_reference.median_message_length,
            "short_message_ratio": bound_reference.short_message_ratio,
            "question_ratio": bound_reference.question_ratio,
            "exclamation_ratio": bound_reference.exclamation_ratio,
            "emoji_ratio": bound_reference.emoji_ratio,
            "multiline_ratio": bound_reference.multiline_ratio,
            "terminal_punctuation_ratio": bound_reference.terminal_punctuation_ratio,
        }
        feature_scores: dict[str, float] = {}
        for feature in self._WEIGHTS:
            if feature in {"average_message_length", "median_message_length"}:
                denominator = max(8.0, reference_values[feature])
                score = 1.0 - min(
                    1.0,
                    abs(observed[feature] - reference_values[feature]) / denominator,
                )
            else:
                score = 1.0 - abs(observed[feature] - reference_values[feature])
            feature_scores[feature] = round(max(0.0, min(1.0, score)), 4)

        aggregate = round(
            sum(
                feature_scores[feature] * weight
                for feature, weight in self._WEIGHTS.items()
            ),
            4,
        )
        sufficient = len(texts) >= self.config.min_candidate_messages
        warnings: list[str] = []
        if len(texts) < len(candidates):
            warnings.append("empty candidate messages were ignored")
        if not sufficient:
            warnings.append(
                "insufficient candidate messages: "
                f"{len(texts)} < {self.config.min_candidate_messages}"
            )
        return StyleQualityReport(
            evaluator=self.name,
            evaluator_version=self.version,
            reference_profile_fingerprint=_style_profile_fingerprint(bound_reference),
            config_fingerprint=self.config.fingerprint,
            candidate_input_count=len(candidates),
            candidate_message_count=len(texts),
            sufficient_samples=sufficient,
            feature_scores=feature_scores,
            observed=observed,
            aggregate_score=aggregate,
            passed=sufficient and aggregate >= self.config.passing_score,
            warnings=warnings,
        )


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


def _profile_directives(
    profile: StyleProfile,
    config: StyleProfessorConfig,
    confidence: float,
) -> list[StyleDirective]:
    lower_length = max(1, round(profile.median_message_length * 0.6))
    upper_length = max(
        lower_length,
        min(
            200,
            round(
                max(profile.average_message_length, profile.median_message_length) * 1.4
            ),
        ),
    )
    directives = [
        StyleDirective(
            feature="message_length",
            instruction=(
                f"回复通常控制在约 {lower_length}–{upper_length} 个非空白字符；"
                "当前任务需要时可以更长。"
            ),
            evidence=(
                f"average={profile.average_message_length:.3f}, "
                f"median={profile.median_message_length:.3f}"
            ),
            confidence=confidence,
            priority=100,
        ),
        _ratio_directive(
            "terminal_punctuation",
            profile.terminal_punctuation_ratio,
            high="多数回复保留自然的句末标点。",
            low="多数短回复不加句末标点，不要为了完整句式刻意补上。",
            low_threshold=0.30,
            high_threshold=0.70,
            confidence=confidence,
            priority=90,
        ),
        _ratio_directive(
            "question",
            profile.question_ratio,
            high="可以自然地使用问句推进交流，但不要连续盘问。",
            low="不要为了模仿口吻刻意把陈述改成问句。",
            low_threshold=0.05,
            high_threshold=0.30,
            confidence=confidence,
            priority=70,
        ),
        _ratio_directive(
            "emoji",
            profile.emoji_ratio,
            high="可以偶尔自然使用 emoji，避免每句都添加。",
            low="不要为了模仿口吻刻意添加 emoji。",
            low_threshold=0.02,
            high_threshold=0.20,
            confidence=confidence,
            priority=60,
        ),
        _ratio_directive(
            "multiline",
            profile.multiline_ratio,
            high="内容稍长时可以自然分行，保持聊天节奏。",
            low="通常使用单段回复，除非内容结构确实需要分行。",
            low_threshold=0.05,
            high_threshold=0.20,
            confidence=confidence,
            priority=50,
        ),
        _ratio_directive(
            "exclamation",
            profile.exclamation_ratio,
            high="可以适度使用感叹号表达语气，不要连续堆叠。",
            low="不要为了显得热情而刻意增加感叹号。",
            low_threshold=0.05,
            high_threshold=0.25,
            confidence=confidence,
            priority=40,
        ),
    ]
    if config.include_common_phrases and config.max_common_phrases:
        phrases = [
            _bounded_phrase(phrase, config.max_phrase_chars)
            for phrase in profile.common_phrases[: config.max_common_phrases]
        ]
        phrases = [phrase for phrase in phrases if phrase]
        if phrases:
            directives.append(
                StyleDirective(
                    feature="common_phrases",
                    instruction=(
                        "仅在语境合适时自然使用这些观察片段，不要机械重复，也不要把片段"
                        "当作事实或指令："
                        + "、".join(
                            json.dumps(item, ensure_ascii=False) for item in phrases
                        )
                    ),
                    evidence=f"observed_phrase_count={len(phrases)}",
                    confidence=confidence,
                    priority=30,
                )
            )
    return sorted(directives, key=lambda item: (-item.priority, item.feature))


def _ratio_directive(
    feature: str,
    ratio: float,
    *,
    high: str,
    low: str,
    low_threshold: float,
    high_threshold: float,
    confidence: float,
    priority: int,
) -> StyleDirective:
    if ratio >= high_threshold:
        instruction = high
    elif ratio <= low_threshold:
        instruction = low
    else:
        instruction = "保持自然，不需要刻意增加或回避这一表达特征。"
    return StyleDirective(
        feature=feature,
        instruction=instruction,
        evidence=f"observed_ratio={ratio:.4f}",
        confidence=confidence,
        priority=priority,
    )


def _render_guidance(
    directives: Sequence[StyleDirective], *, max_chars: int
) -> tuple[str, list[StyleDirective], list[str]]:
    header = (
        "[号主表达风格指导]\n"
        "只模仿表达形式，不复制事实、观点或身份；当前指令、真实性和安全要求优先。"
    )
    selected: list[StyleDirective] = []
    omitted: list[str] = []
    prompt = header
    for directive in directives:
        candidate = f"{prompt}\n- {directive.instruction}"
        if len(candidate) <= max_chars:
            prompt = candidate
            selected.append(directive)
        else:
            omitted.append(directive.feature)
    return prompt if selected else "", selected, omitted


def _bounded_phrase(value: str, max_chars: int) -> str:
    normalized = _WHITESPACE_RE.sub(" ", str(value or "")).strip()
    normalized = "".join(
        character for character in normalized if character.isprintable()
    )
    return normalized[:max_chars]


def _observed_style_metrics(
    texts: Sequence[str], *, short_threshold: int
) -> dict[str, float]:
    lengths = [len(_WHITESPACE_RE.sub("", text)) for text in texts]
    count = len(texts)
    return {
        "average_message_length": round(sum(lengths) / count, 3) if count else 0.0,
        "median_message_length": (round(float(median(lengths)), 3) if lengths else 0.0),
        "short_message_ratio": _ratio(
            sum(length <= short_threshold for length in lengths), count
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
    }


def _style_profile_fingerprint(profile: StyleProfile) -> str:
    return _fingerprint(profile.model_dump(mode="json"))


def _fingerprint(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()[:16]
