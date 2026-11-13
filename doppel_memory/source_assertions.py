"""Experimental clause records with separately assembled original context."""

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from doppel_memory.intelligence import (
    PersonalMemoryAnalysis,
    PersonalMemoryAnalysisRequest,
)
from doppel_memory.models import Actor, FactAuthority, MemoryRecord
from doppel_memory.source_clauses import (
    INSTRUCTIONS,
    SourceClauseDraft,
    SourceClausePersonalMemoryAnalyzer,
)

ASSERTION_INSTRUCTIONS = INSTRUCTIONS.replace(
    "The host preserves the WHOLE source message as memory content; the clause is\n"
    "an audit annotation, not a replacement for its qualifying context.",
    "The host stores the exact clause as content and references the whole source\n"
    "separately. Clauses must be trimmed and occur exactly once in their source.\n"
    "Preserve qualifying context in each clause; source references do not prove meaning.",
)


class AssertionDiagnostics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    total: int
    accepted: int
    rejected: list[dict[str, int | str]]


def source_digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SourceAssertionPersonalMemoryAnalyzer(SourceClausePersonalMemoryAnalyzer):
    """Opt-in exact clauses; isolate only when a diagnostic sink is required.

    Does not repair invalid annotations, verify clause semantics, or supply full
    context automatically to ordinary query callers. Use assemble_source_assertions.
    """

    name = "doppel.source-assertion-personal-memory-analyzer"

    def __init__(
        self,
        model,
        *,
        invalid_policy: Literal["reject_batch", "isolate"] = "reject_batch",
        diagnostics_observer: Callable[[AssertionDiagnostics], None] | None = None,
        **limits,
    ):
        if invalid_policy not in {"reject_batch", "isolate"} or (
            invalid_policy == "isolate" and diagnostics_observer is None
        ):
            raise ValueError("isolation requires an explicit diagnostic sink")
        super().__init__(model, **limits)
        self.invalid_policy, self.observer = invalid_policy, diagnostics_observer
        self.version = (
            "1."
            + source_digest(
                json.dumps(
                    {
                        "parent": self.version,
                        "policy": invalid_policy,
                        "format": "source-assertion.v1",
                        "instructions": ASSERTION_INSTRUCTIONS,
                    },
                    sort_keys=True,
                )
            )[:16]
        )

    def _generation(self, bound):
        generation = super()._generation(bound)
        return generation.model_copy(update={"instructions": ASSERTION_INSTRUCTIONS})

    async def analyze(self, request):
        bound = PersonalMemoryAnalysisRequest.model_validate(request)
        raw = await self.model.generate(self._generation(bound))
        raw = raw.model_dump() if isinstance(raw, BaseModel) else raw
        if (
            not isinstance(raw, Mapping)
            or set(raw) != {"memories"}
            or not isinstance(raw["memories"], list)
        ):
            raise ValueError("invalid assertion response envelope")
        if len(raw["memories"]) > self.max_memories:
            raise ValueError("assertion count exceeds bound; no truncation")
        sources = {m.identity_key: m for m in bound.messages}
        accepted, rejected = [], []
        for index, item in enumerate(raw["memories"]):
            reason = "schema_validation"
            try:
                draft = SourceClauseDraft.model_validate(item)
                reason = "source_or_annotation_validation"
                memory = self._convert(draft, sources)
                source = sources[draft.evidence_id]
                start = source.text.find(draft.clause)
                if (
                    draft.clause != draft.clause.strip()
                    or source.text.find(draft.clause, start + 1) != -1
                ):
                    raise ValueError("ambiguous or untrimmed assertion span")
                accepted.append(
                    memory.model_copy(
                        update={
                            "content": draft.clause,
                            "metadata": {
                                "source_assertion": {
                                    "format": "source-assertion.v1",
                                    "evidence_id": source.identity_key,
                                    "start": start,
                                    "end": start + len(draft.clause),
                                    "source_sha256": source_digest(source.text),
                                    "semantic_support_verified": False,
                                }
                            },
                        }
                    )
                )
            except (ValueError, ValidationError):
                if self.invalid_policy == "reject_batch":
                    raise ValueError(
                        "invalid source assertion; batch rejected"
                    ) from None
                rejected.append({"index": index, "reason": reason})
        report = AssertionDiagnostics(
            total=len(raw["memories"]), accepted=len(accepted), rejected=rejected
        )
        if self.observer is not None:
            self.observer(
                report
            )  # no analysis returned if diagnostic publication fails
        return PersonalMemoryAnalysis(memories=accepted)


def assemble_source_assertions(
    request: PersonalMemoryAnalysisRequest, records: Sequence[MemoryRecord]
) -> dict:
    """Host supplies authorized original messages and authoritative Store records.

    No Store lookup, authorization, semantic review or record-count certification.
    Revalidate sources/spans/identity here; publish nothing on any mismatch.
    """
    bound = PersonalMemoryAnalysisRequest.model_validate(request)
    sources = {m.identity_key: m for m in bound.messages}
    used, claims, seen = {}, [], set()
    for record in records:
        if (
            record.memory_id in seen
            or not record.memory_id
            or record.scope != bound.scope
            or record.state.value not in {"candidate", "confirmed"}
        ):
            raise ValueError("invalid assertion record identity/scope/state")
        seen.add(record.memory_id)
        ref = record.metadata.get("source_assertion", {})
        source = sources.get(ref.get("evidence_id"))
        if (
            source is None
            or ref.get("format") != "source-assertion.v1"
            or ref.get("semantic_support_verified") is not False
        ):
            raise ValueError("invalid assertion source reference")
        start, end = ref.get("start"), ref.get("end")
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(source.text)
            or ref.get("source_sha256") != source_digest(source.text)
            or source.text[start:end] != record.content
        ):
            raise ValueError("assertion span/source mismatch")
        subject_id = (
            bound.scope.user_id
            if source.actor == Actor.OWNER
            else bound.scope.agent_id
            if source.actor == Actor.AGENT
            else source.sender_id
            if source.actor == Actor.CONTACT
            else ""
        )
        if (
            record.actor != source.actor
            or record.authority != FactAuthority.of(source.actor)
            or record.created_at != source.at
            or record.metadata.get("source_scope_key") != bound.scope.scope_key
            or record.metadata.get("subject") != source.actor
            or record.metadata.get("subject_id") != subject_id
        ):
            raise ValueError("assertion source perspective mismatch")
        evidence = record.metadata.get("evidence", [])
        if (
            not isinstance(evidence, list)
            or len(evidence) != 1
            or not isinstance(evidence[0], dict)
            or any(
                evidence[0].get(k) != v
                for k, v in {
                    "evidence_id": source.identity_key,
                    "actor": source.actor,
                    "sender_id": source.sender_id,
                    "at": source.at.isoformat(),
                }.items()
            )
        ):
            raise ValueError("assertion evidence binding mismatch")
        used[source.identity_key] = source.model_dump(
            mode="json", exclude={"raw", "attachments", "parts"}
        )
        claims.append(
            {
                "memory_id": record.memory_id,
                "content": record.content,
                "source_ref": dict(ref),
                "actor": record.actor,
                "subject_id": subject_id,
                "state": record.state.value,
            }
        )
    return {
        "format": "source-assertion-context.v1",
        "claims": claims,
        "sources": used,
        "semantic_support_verified": False,
    }
