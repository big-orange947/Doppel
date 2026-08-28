"""Evidence-bound reference intelligence for personal memory extraction.

The analyzer is replaceable and model-neutral.  It can only return structured
drafts; Doppel derives authority and target scope from trusted input, validates
every evidence reference, and emits ordinary ``MemoryProposal`` values.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
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
    MemoryState,
)
from doppel_memory.processing import MemoryProposal


class PersonalMemoryType:
    """Open personal-memory type namespace with recommended built-ins."""

    FACT = "fact"
    STATE = "state"
    EPISODE = "episode"
    PREFERENCE = "preference"
    RELATIONSHIP = "relationship"
    PLAN = "plan"
    COMMITMENT = "commitment"

    @classmethod
    def normalize(cls, raw: str | None) -> str:
        value = str(raw or "").strip().lower()
        if not value:
            raise ValueError("personal memory type is required")
        return value[:64]


class MemoryTemporalStatus:
    """Open temporal interpretation namespace with recommended built-ins."""

    TIMELESS = "timeless"
    CURRENT = "current"
    HISTORICAL = "historical"
    PLANNED = "planned"
    UNKNOWN = "unknown"

    @classmethod
    def normalize(cls, raw: str | None) -> str:
        value = str(raw or "").strip().lower()
        return (value or cls.UNKNOWN)[:64]


class PersonalMemoryDraft(BaseModel):
    """One analyzer-produced memory claim before trusted scope derivation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str
    memory_type: str = PersonalMemoryType.FACT
    topic_key: str = ""
    event_key: str = ""
    kind: str = MemoryKind.FACT
    subject: str = Actor.OWNER
    subject_id: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    temporal_status: str = MemoryTemporalStatus.UNKNOWN
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    evidence_ids: list[str] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content", mode="before")
    @classmethod
    def _require_content(cls, value: Any) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("personal memory content is required")
        return normalized

    @field_validator("memory_type", mode="before")
    @classmethod
    def _normalize_memory_type(cls, value: Any) -> str:
        return PersonalMemoryType.normalize(value)

    @field_validator("topic_key", mode="before")
    @classmethod
    def _normalize_topic_key(cls, value: Any) -> str:
        return str(value or "").strip().lower()[:128]

    @field_validator("event_key", mode="before")
    @classmethod
    def _normalize_event_key(cls, value: Any) -> str:
        return str(value or "").strip().lower()[:160]

    @field_validator("kind", mode="before")
    @classmethod
    def _normalize_kind(cls, value: Any) -> str:
        return MemoryKind.normalize(value)

    @field_validator("subject", mode="before")
    @classmethod
    def _normalize_subject(cls, value: Any) -> str:
        return Actor.normalize(value)

    @field_validator("subject_id", mode="before")
    @classmethod
    def _normalize_subject_id(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("temporal_status", mode="before")
    @classmethod
    def _normalize_temporal_status(cls, value: Any) -> str:
        return MemoryTemporalStatus.normalize(value)

    @field_validator("valid_from", "valid_to")
    @classmethod
    def _normalize_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("personal memory timestamps must include a timezone")
        return value.astimezone(UTC)

    @field_validator("evidence_ids")
    @classmethod
    def _normalize_evidence_ids(cls, value: list[str]) -> list[str]:
        normalized = [str(item or "").strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("evidence IDs must not be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("evidence IDs must be unique")
        return normalized

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: list[str]) -> list[str]:
        return list(
            dict.fromkeys(str(item).strip() for item in value if str(item).strip())
        )

    @model_validator(mode="after")
    def _validate_interval(self) -> PersonalMemoryDraft:
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not precede valid_from")
        if self.event_key and self.memory_type != PersonalMemoryType.EPISODE:
            raise ValueError("event_key is only valid for episode memories")
        return self


class PersonalMemoryAnalysisRequest(BaseModel):
    """Exact-scope normalized evidence supplied to an analyzer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: MemoryScope
    messages: list[ChatMessage] = Field(min_length=1)

    @model_validator(mode="after")
    def _require_stable_unique_evidence(self) -> PersonalMemoryAnalysisRequest:
        identities = [message.identity_key for message in self.messages]
        if any(not identity for identity in identities):
            raise ValueError("every analyzed message requires a message_id or event_id")
        if len(identities) != len(set(identities)):
            raise ValueError("analyzed message identities must be unique")
        return self


class PersonalMemoryAnalysis(BaseModel):
    """Validated structured output from a personal-memory analyzer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memories: list[PersonalMemoryDraft] = Field(default_factory=list)


class StructuredGenerationRequest(BaseModel):
    """Provider-neutral request for one schema-constrained generation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    instructions: str
    input: dict[str, Any]
    output_schema: dict[str, Any]


@runtime_checkable
class StructuredOutputModel(Protocol):
    """Minimal boundary implemented by a hosted or local structured model."""

    name: str
    version: str

    async def generate(
        self, request: StructuredGenerationRequest
    ) -> Mapping[str, Any] | BaseModel: ...


@runtime_checkable
class PersonalMemoryAnalyzer(Protocol):
    """Turn a bounded evidence slice into structured drafts; never writes Store."""

    name: str
    version: str

    async def analyze(
        self, request: PersonalMemoryAnalysisRequest
    ) -> PersonalMemoryAnalysis: ...


REFERENCE_PERSONAL_MEMORY_INSTRUCTIONS = """\
You extract durable personal information from normalized conversation evidence.
Return only claims directly supported by the supplied evidence IDs. Prefer precision
and an empty memories list over guessing. Distinguish the owner, contact, agent, and
system; never turn agent suggestions or acknowledgements into owner facts. Extract
personal facts, current states, episodes, preferences, relationships, plans, and
commitments only when useful beyond the immediate utterance. Keep temporary states and
historical events distinct from timeless facts. Preserve explicit temporal bounds when
the evidence provides them. When a claim belongs to one stable mutable slot, provide a
lowercase topic_key such as residence.primary or preference.favorite-color; omit it
when no precise slot is justified. For an episode, provide event_key only when the
evidence identifies one stable real-world event; repeated mentions of the same event
must use the same key, while separate events must not share one. Omit it when uncertain.
Do not choose a storage scope, memory ID, authority, or lifecycle action: Doppel derives
those from trusted input. Do not consolidate conflicts or silently discard old facts;
that is a separate audited stage.
"""


class ReferencePersonalMemoryAnalyzer:
    """Reference prompt and schema around any structured-output model provider."""

    name = "doppel.reference-personal-memory-analyzer"
    version = "1"

    def __init__(self, model: StructuredOutputModel) -> None:
        self.model = model
        _require_identity(model, "structured output model")

    async def analyze(
        self, request: PersonalMemoryAnalysisRequest
    ) -> PersonalMemoryAnalysis:
        bound = PersonalMemoryAnalysisRequest.model_validate(request)
        payload = {
            "scope": bound.scope.describe(),
            "messages": [
                {
                    "evidence_id": message.identity_key,
                    "actor": message.actor,
                    "sender_id": message.sender_id,
                    "at": message.at.isoformat(),
                    "message_type": message.message_type,
                    "text": message.text,
                    "parts": [part.model_dump(mode="json") for part in message.parts],
                }
                for message in bound.messages
            ],
        }
        raw = await self.model.generate(
            StructuredGenerationRequest(
                instructions=REFERENCE_PERSONAL_MEMORY_INSTRUCTIONS,
                input=payload,
                output_schema=PersonalMemoryAnalysis.model_json_schema(),
            )
        )
        if isinstance(raw, BaseModel):
            raw = raw.model_dump(warnings=False)
        return PersonalMemoryAnalysis.model_validate(raw)


class PersonalMemoryExtractorConfig(BaseModel):
    """High-precision gates shared by online and periodic extraction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_target_scope: Literal["conversation", "user"] = "user"
    minimum_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    max_memories: int = Field(default=8, ge=1, le=100)
    allowed_source_actors: set[str] = Field(
        default_factory=lambda: {Actor.OWNER, Actor.CONTACT}
    )
    require_subject_matches_source_actor: bool = True
    proposed_state: MemoryState = MemoryState.CANDIDATE

    @field_validator("allowed_source_actors", mode="before")
    @classmethod
    def _normalize_actors(cls, value: Any) -> set[str]:
        normalized = {Actor.normalize(item) for item in set(value or ())}
        if not normalized:
            raise ValueError("allowed_source_actors must not be empty")
        return normalized

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.model_dump(mode="json"))


class PersonalMemoryMinerConfig(PersonalMemoryExtractorConfig):
    """Bounded history-reading configuration for contextual extraction."""

    page_size: int = Field(default=200, ge=1, le=2_000)
    max_messages: int = Field(default=500, ge=1, le=50_000)


class PersonalMemoryEvidenceError(ValueError):
    """Analyzer output cannot be bound safely to the supplied evidence."""


class PersonalMemoryExtractor:
    """Online high-precision extractor for one self-contained IM event."""

    name = "doppel.personal-memory-extractor"
    version = "1"

    def __init__(
        self,
        analyzer: PersonalMemoryAnalyzer,
        config: PersonalMemoryExtractorConfig | None = None,
    ) -> None:
        self.analyzer = analyzer
        self.config = config or PersonalMemoryExtractorConfig()
        _require_identity(analyzer, "personal memory analyzer")

    async def process(
        self, scope: MemoryScope, message: ChatMessage
    ) -> Sequence[MemoryProposal]:
        if message.actor not in self.config.allowed_source_actors:
            return []
        request = PersonalMemoryAnalysisRequest(scope=scope, messages=[message])
        analysis = await self.analyzer.analyze(request)
        return _analysis_to_proposals(
            request,
            analysis,
            analyzer=self.analyzer,
            processor=self.name,
            processor_version=self.version,
            config=self.config,
        )


class PersonalMemoryMiner:
    """Periodic contextual extractor over one exact-scope history window."""

    name = "doppel.personal-memory-miner"
    version = "1"
    checkpoint_schema_version = 1

    def __init__(
        self,
        analyzer: PersonalMemoryAnalyzer,
        config: PersonalMemoryMinerConfig | None = None,
    ) -> None:
        self.analyzer = analyzer
        self.config = config or PersonalMemoryMinerConfig()
        _require_identity(analyzer, "personal memory analyzer")

    @property
    def checkpoint_key(self) -> str:
        return (
            f"{self.name}:{self.version}:{self.config.fingerprint}:"
            f"{self.analyzer.name}:{self.analyzer.version}"
        )

    async def propose(self, context: BatchTaskContext) -> BatchProposalPlan:
        cursor = context.checkpoint.cursor
        messages: list[ChatMessage] = []
        truncated = False
        while len(messages) < self.config.max_messages:
            remaining = self.config.max_messages - len(messages)
            page = await context.history.read(
                cursor=cursor,
                limit=min(self.config.page_size, remaining),
                actors=set(self.config.allowed_source_actors),
                time_from=context.window.start,
                time_to=context.window.end,
            )
            messages.extend(
                message
                for message in page.messages
                if message.actor in self.config.allowed_source_actors
                and message.identity_key
                and bool(message.text.strip() or message.parts)
            )
            cursor = page.next_cursor
            if not page.has_more:
                break
            if len(messages) >= self.config.max_messages:
                truncated = True
                break

        proposals: list[MemoryProposal] = []
        if messages:
            request = PersonalMemoryAnalysisRequest(
                scope=context.scope, messages=messages
            )
            analysis = await self.analyzer.analyze(request)
            proposals = _analysis_to_proposals(
                request,
                analysis,
                analyzer=self.analyzer,
                processor=self.name,
                processor_version=self.version,
                config=self.config,
            )
        return BatchProposalPlan(
            proposals=proposals,
            next_checkpoint=BatchCheckpoint(
                cursor=cursor,
                metadata={
                    "window_end": context.window.end.isoformat(),
                    "eligible_messages": len(messages),
                    "proposals": len(proposals),
                    "truncated": truncated,
                    "config_fingerprint": self.config.fingerprint,
                    "analyzer": self.analyzer.name,
                    "analyzer_version": self.analyzer.version,
                },
            ),
        )


def _analysis_to_proposals(
    request: PersonalMemoryAnalysisRequest,
    raw_analysis: PersonalMemoryAnalysis,
    *,
    analyzer: PersonalMemoryAnalyzer,
    processor: str,
    processor_version: str,
    config: PersonalMemoryExtractorConfig,
) -> list[MemoryProposal]:
    analysis = PersonalMemoryAnalysis.model_validate(raw_analysis)
    if len(analysis.memories) > config.max_memories:
        raise PersonalMemoryEvidenceError(
            f"analyzer returned {len(analysis.memories)} memories; "
            f"maximum is {config.max_memories}"
        )
    evidence = {message.identity_key: message for message in request.messages}
    proposals: list[MemoryProposal] = []
    seen: set[str] = set()
    ranked_drafts = sorted(
        enumerate(analysis.memories), key=lambda item: (-item[1].confidence, item[0])
    )
    for _, draft in ranked_drafts:
        unknown = set(draft.evidence_ids).difference(evidence)
        if unknown:
            raise PersonalMemoryEvidenceError(
                f"memory references unknown evidence IDs: {sorted(unknown)}"
            )
        bound_messages = [evidence[item] for item in draft.evidence_ids]
        source_actors = {message.actor for message in bound_messages}
        if not source_actors.issubset(config.allowed_source_actors):
            raise PersonalMemoryEvidenceError(
                "memory references an actor excluded by extraction policy"
            )
        if len(source_actors) != 1:
            raise PersonalMemoryEvidenceError(
                "one memory draft must use evidence from exactly one source actor"
            )
        source_actor = next(iter(source_actors))
        if (
            config.require_subject_matches_source_actor
            and draft.subject != source_actor
        ):
            raise PersonalMemoryEvidenceError(
                f"memory subject {draft.subject!r} does not match evidence actor "
                f"{source_actor!r}"
            )
        if draft.confidence < config.minimum_confidence:
            continue
        subject_id = _subject_id(draft, request.scope, bound_messages)
        target_scope = _target_scope(
            request.scope, draft.subject, config.owner_target_scope
        )
        primary = max(bound_messages, key=lambda item: (item.at, item.identity_key))
        identity_payload = {
            "analyzer": f"{analyzer.name}:{analyzer.version}",
            "scope": target_scope.scope_key,
            "content": draft.content,
            "memory_type": draft.memory_type,
            "topic_key": draft.topic_key,
            "event_key": draft.event_key,
            "subject": draft.subject,
            "subject_id": subject_id,
            "evidence_ids": sorted(draft.evidence_ids),
        }
        identity = _fingerprint(identity_payload)
        if identity in seen:
            continue
        seen.add(identity)
        evidence_metadata = [
            {
                "evidence_id": message.identity_key,
                "message_id": message.message_id,
                "event_id": message.event_id,
                "actor": message.actor,
                "sender_id": message.sender_id,
                "at": message.at.isoformat(),
            }
            for message in bound_messages
        ]
        metadata = dict(draft.metadata)
        metadata.update(
            {
                "personal_memory_type": draft.memory_type,
                "topic_key": draft.topic_key,
                "event_key": draft.event_key,
                "subject": draft.subject,
                "subject_id": subject_id,
                "temporal_status": draft.temporal_status,
                "valid_from": (
                    draft.valid_from.isoformat() if draft.valid_from else None
                ),
                "valid_to": draft.valid_to.isoformat() if draft.valid_to else None,
                "evidence": evidence_metadata,
                "source_scope_key": request.scope.scope_key,
                "analyzer": analyzer.name,
                "analyzer_version": analyzer.version,
                "config_fingerprint": config.fingerprint,
            }
        )
        proposals.append(
            MemoryProposal(
                scope=target_scope,
                content=draft.content,
                kind=draft.kind,
                actor=source_actor,
                authority=FactAuthority.of(source_actor),
                confidence=draft.confidence,
                proposed_state=config.proposed_state,
                tags=list(
                    dict.fromkeys(["personal-memory", draft.memory_type, *draft.tags])
                ),
                importance=draft.importance,
                idempotency_key=f"personal-memory:{identity}",
                source_event_id=primary.event_id,
                source_message_id=primary.message_id,
                processor=processor,
                processor_version=processor_version,
                derived_chain=[f"event:{item}" for item in draft.evidence_ids],
                created_at=primary.at,
                metadata=metadata,
            )
        )
    return proposals


def _subject_id(
    draft: PersonalMemoryDraft,
    scope: MemoryScope,
    messages: Sequence[ChatMessage],
) -> str:
    if draft.subject == Actor.CONTACT:
        known = {message.sender_id for message in messages if message.sender_id}
        if len(known) != 1:
            raise PersonalMemoryEvidenceError(
                "contact subject requires exactly one trusted evidence sender_id"
            )
        trusted_subject_id = next(iter(known))
        if draft.subject_id and draft.subject_id != trusted_subject_id:
            raise PersonalMemoryEvidenceError(
                "contact subject_id is not present in the bound evidence"
            )
        return trusted_subject_id
    if draft.subject_id:
        if draft.subject == Actor.OWNER and draft.subject_id != scope.user_id:
            raise PersonalMemoryEvidenceError(
                "owner subject_id must match the trusted scope user_id"
            )
        if draft.subject == Actor.AGENT and draft.subject_id != scope.agent_id:
            raise PersonalMemoryEvidenceError(
                "agent subject_id must match the trusted scope agent_id"
            )
        return draft.subject_id
    if draft.subject == Actor.OWNER:
        return scope.user_id
    if draft.subject == Actor.AGENT:
        return scope.agent_id
    return ""


def _target_scope(
    source: MemoryScope,
    subject: str,
    owner_target_scope: Literal["conversation", "user"],
) -> MemoryScope:
    if subject == Actor.OWNER and owner_target_scope == "user":
        return source.user_scope()
    return source


def _require_identity(component: Any, label: str) -> None:
    if not str(getattr(component, "name", "") or "").strip():
        raise ValueError(f"{label} name must not be empty")
    if not str(getattr(component, "version", "") or "").strip():
        raise ValueError(f"{label} version must not be empty")


def _fingerprint(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
