"""Read-only temporal interpretation of exact-scope analyzer proposals.

This does not write Store, approve facts, resolve semantic conflicts, or infer
effective dates from observation dates. Host-supplied messages/identity bindings
must already be authorized; a scope string is not an access-control credential.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from doppel_memory.consolidation import (
    ConsolidationDecision,
    ConsolidationInput,
    DeterministicMemoryConsolidator,
)
from doppel_memory.intelligence import (
    MemoryTemporalStatus,
    PersonalMemoryAnalysisRequest,
    PersonalMemoryRevisionKind,
    PersonalMemoryType,
)
from doppel_memory.models import Actor, FactAuthority, MemoryState
from doppel_memory.processing import MemoryProposal


class TransientViewError(ValueError):
    """A proposal cannot be bound safely to the supplied source window."""


class TransientEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: str
    actor: str
    authority: FactAuthority
    sender_id: str
    observed_at: datetime
    text: str


class TransientMemoryClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    claim_id: str
    content: str
    actor: str
    authority: FactAuthority
    subject: str
    subject_id: str
    state: Literal["candidate"] = "candidate"
    confidence: float
    memory_type: str
    topic_key: str
    event_key: str
    revision_kind: str
    temporal_status: str
    first_observed_at: datetime
    last_observed_at: datetime
    observed_after_reference: bool
    valid_from: datetime | None
    valid_to: datetime | None
    validity_at_reference: Literal[
        "unknown", "within_explicit_bounds", "outside_explicit_bounds"
    ]
    evidence: tuple[TransientEvidence, ...]


class TransientMemoryView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    format: Literal["doppel.transient-memory-view.v1"] = (
        "doppel.transient-memory-view.v1"
    )
    scope_key: str
    reference_time: datetime
    observed_until: datetime
    claims: tuple[TransientMemoryClaim, ...]
    advisory_consolidation: tuple[ConsolidationDecision, ...]
    consolidation_applied: Literal[False] = False
    semantic_evidence_verified: Literal[False] = False


def _time(value: datetime | str | None, *, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    try:
        result = datetime.fromisoformat(value) if isinstance(value, str) else value
        if not isinstance(result, datetime) or result.tzinfo is None:
            raise ValueError
        return result.astimezone(UTC)
    except (ValueError, TypeError) as error:
        raise TransientViewError("timestamps must be timezone-aware") from error


class TransientMemoryViewBuilder:
    """Bound candidate proposals and call the existing pure consolidator.

    Exact-scope only: no cross-scope promotion or automatic retrieval. Reference
    time and observation horizon are separate; omitted horizon means strict
    reference-time availability. Raise rather than silently drop unavailable
    sources. All merge/correction/conflict decisions are advisory and no record is
    changed. Even `within_explicit_bounds` does not prove a claim is factually true.
    """

    def __init__(self, *, max_messages: int = 500, max_claims: int = 100) -> None:
        if any(type(n) is not int or n < 1 for n in (max_messages, max_claims)):
            raise ValueError("transient view limits must be positive integers")
        self.max_messages, self.max_claims = max_messages, max_claims

    async def build(
        self,
        request: PersonalMemoryAnalysisRequest,
        proposals: Sequence[MemoryProposal],
        *,
        reference_time: datetime,
        observed_until: datetime | None = None,
    ) -> TransientMemoryView:
        bound = PersonalMemoryAnalysisRequest.model_validate(request)
        if len(bound.messages) > self.max_messages or len(proposals) > self.max_claims:
            raise TransientViewError("transient source/claim limit exceeded")
        reference = _time(reference_time)
        horizon = _time(
            observed_until if observed_until is not None else reference_time
        )
        assert reference is not None and horizon is not None
        if horizon < reference:
            raise TransientViewError("observation horizon precedes reference time")
        if any(message.at > horizon for message in bound.messages):
            raise TransientViewError("source observation outside authorized horizon")
        sources = {m.identity_key: m for m in bound.messages}
        claims, records, seen = [], [], set()
        for raw in proposals:
            proposal = MemoryProposal.model_validate(raw)
            if (
                proposal.scope != bound.scope
                or proposal.proposed_state != MemoryState.CANDIDATE
                or not proposal.content
            ):
                raise TransientViewError("exact-scope candidate proposals required")
            meta = proposal.metadata
            if any(
                not isinstance(meta.get(key), str)
                for key in (
                    "subject",
                    "subject_id",
                    "personal_memory_type",
                    "topic_key",
                    "event_key",
                    "revision_kind",
                    "temporal_status",
                )
            ):
                raise TransientViewError("normalized claim metadata required")
            if (
                meta["event_key"]
                and meta["personal_memory_type"] != PersonalMemoryType.EPISODE
            ):
                raise TransientViewError("event key requires an episode claim")
            evidence = meta.get("evidence")
            if (
                meta.get("source_scope_key") != bound.scope.scope_key
                or not isinstance(evidence, list)
                or not evidence
            ):
                raise TransientViewError("bound original evidence required")
            normalized, evidence_ids = [], set()
            for item in evidence:
                if not isinstance(item, dict):
                    raise TransientViewError("invalid source binding")
                identity = item.get("evidence_id")
                if not isinstance(identity, str):
                    raise TransientViewError("invalid evidence identity")
                source = sources.get(identity)
                if source is None or identity in evidence_ids:
                    raise TransientViewError("unknown or duplicate evidence")
                if (
                    source.actor != proposal.actor
                    or item.get("actor") != source.actor
                    or item.get("message_id") != source.message_id
                    or item.get("event_id") != source.event_id
                    or item.get("sender_id") != source.sender_id
                    or _time(item.get("at")) != source.at
                ):
                    raise TransientViewError("source identity/actor/time mismatch")
                evidence_ids.add(identity)
                normalized.append(
                    TransientEvidence(
                        evidence_id=identity,
                        actor=source.actor,
                        authority=FactAuthority.of(source.actor),
                        sender_id=source.sender_id,
                        observed_at=source.at,
                        text=source.text,
                    )
                )
            actor = proposal.actor
            if (
                actor not in {Actor.OWNER, Actor.AGENT, Actor.CONTACT}
                or proposal.authority != FactAuthority.of(actor)
                or meta.get("subject") != actor
            ):
                raise TransientViewError("subject/source authority mismatch")
            subject_id = (
                bound.scope.user_id if actor == Actor.OWNER else bound.scope.agent_id
            )
            if actor == Actor.CONTACT:
                senders = {e.sender_id for e in normalized}
                if len(senders) != 1 or not next(iter(senders)):
                    raise TransientViewError("contact requires one trusted sender")
                subject_id = next(iter(senders))
            if meta.get("subject_id") != subject_id:
                raise TransientViewError("subject identity mismatch")
            normalized.sort(key=lambda e: (e.observed_at, e.evidence_id))
            first, last = normalized[0].observed_at, normalized[-1].observed_at
            if proposal.created_at != last:
                raise TransientViewError("proposal observation clock mismatch")
            start, end = (
                _time(meta.get("valid_from"), optional=True),
                _time(meta.get("valid_to"), optional=True),
            )
            if start and end and end < start:
                raise TransientViewError("reversed effective interval")
            validity = "unknown"
            if start is not None or end is not None:
                validity = (
                    "outside_explicit_bounds"
                    if (start and reference < start) or (end and reference > end)
                    else "within_explicit_bounds"
                )
            # Canonical source/claim identity, not a fresh random Store ID.
            encoded = json.dumps(
                proposal.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            identity = "transient-" + hashlib.sha256(encoded).hexdigest()
            if identity in seen:
                raise TransientViewError("duplicate proposal identity")
            seen.add(identity)
            claims.append(
                TransientMemoryClaim(
                    claim_id=identity,
                    content=proposal.content,
                    actor=actor,
                    authority=proposal.authority,
                    subject=actor,
                    subject_id=subject_id,
                    confidence=proposal.confidence,
                    memory_type=PersonalMemoryType.normalize(
                        meta.get("personal_memory_type")
                    ),
                    topic_key=str(meta.get("topic_key") or ""),
                    event_key=str(meta.get("event_key") or ""),
                    revision_kind=PersonalMemoryRevisionKind.normalize(
                        meta.get("revision_kind")
                    ),
                    temporal_status=MemoryTemporalStatus.normalize(
                        meta.get("temporal_status")
                    ),
                    first_observed_at=first,
                    last_observed_at=last,
                    observed_after_reference=last > reference,
                    valid_from=start,
                    valid_to=end,
                    validity_at_reference=validity,
                    evidence=tuple(normalized),
                )
            )
            records.append(
                proposal.to_record().model_copy(update={"memory_id": identity})
            )
        # Existing conservative governance logic; no ConsolidationRunner/Store,
        # state transition, canonical-record write or deletion is performed.
        analysis = await DeterministicMemoryConsolidator().consolidate(
            ConsolidationInput(scope=bound.scope, records=records)
        )
        return TransientMemoryView(
            scope_key=bound.scope.scope_key,
            reference_time=reference,
            observed_until=horizon,
            claims=tuple(claims),
            advisory_consolidation=tuple(analysis.decisions),
        )
