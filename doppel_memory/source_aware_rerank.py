"""Opt-in metadata-aware relevance and source/text MMR, without authority changes."""

from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from doppel_memory.lexical import lexical_tokens
from doppel_memory.models import MemoryIsolationError, RecallResult
from doppel_memory.personal_rerank import (
    PersonalMemoryRerankConfig,
    PersonalMemoryReranker,
    PersonalMemoryRerankItem,
    PersonalMemoryRerankRequest,
    PersonalMemoryRerankSummary,
    score_personal_memories,
)


class SourceAwareRerankConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    include_metadata: bool = True
    diversity_weight: float = Field(default=0.0, ge=0, le=1, allow_inf_nan=False)
    max_candidates: int = Field(default=80, ge=1, le=1000)
    max_input_chars: int = Field(default=1_000_000, ge=1, le=10_000_000)
    timeout_seconds: float = Field(default=300, gt=0, le=300, allow_inf_nan=False)


def source_content(candidate: RecallResult) -> str:
    """Trusted attributes must originate in the caller's authorized Store reload.

    The supplied time is not relabelled as observation/effective time. There is
    no newest-wins rule or conversion of assistant text into an owner statement.
    IDs and scope keys are deliberately excluded from provider input.
    """
    return json.dumps(
        {
            "actor": candidate.actor,
            "speaker_role": {"owner": "user", "agent": "assistant"}.get(
                candidate.actor, candidate.actor
            ),
            "authority": candidate.authority.value,
            "candidate_time": candidate.valid_at.isoformat()
            if candidate.valid_at
            else None,
            "time_semantics": "provided candidate time; effective dates may differ in source text",
            "source_text": candidate.raw_text or candidate.fact,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _source(candidate: RecallResult) -> tuple[str, str]:
    if candidate.scope is None:
        raise MemoryIsolationError("source-aware reranking requires scoped candidates")
    return (
        candidate.scope.scope_key,
        candidate.source_event_id or candidate.source_message_id or candidate.memory_id,
    )


def mmr_order(
    candidates: Sequence[RecallResult],
    scores: Sequence[float],
    weight: float,
    limit: int,
) -> list[int]:
    """MMR utility=(1-weight)*relevance-weight*max_redundancy.

    Redundancy is1 for the same scoped source, otherwise lexical-token Jaccard.
    No speaker quota, role filtering, query keywords or recency boost is used.
    Stable ties retain input order. Selection never modifies candidate payloads.
    """
    groups = [_source(c) for c in candidates]
    tokens = [set(lexical_tokens(c.raw_text or c.fact)) for c in candidates]
    chosen: list[int] = []
    remaining = set(range(len(candidates)))
    redundancy = [0.0] * len(candidates)
    while remaining and len(chosen) < limit:
        best = max(
            remaining,
            key=lambda i: ((1 - weight) * scores[i] - weight * redundancy[i], -i),
        )
        chosen.append(best)
        remaining.remove(best)
        for index in remaining:
            union = tokens[index] | tokens[best]
            similar = (
                1.0
                if groups[index] == groups[best]
                else len(tokens[index] & tokens[best]) / len(union)
                if union
                else 0.0
            )
            redundancy[index] = max(redundancy[index], similar)
    return chosen


class SourceAwareReranker:
    """Existing Reranker protocol; caller still enforces scopes and fresh sources.

    Provider input is expanded only when explicitly enabled. Scores/MMR affect
    order, never source truth, lifecycle, count completeness or output scores.
    Failures are explicit; a failed model is not reported as a successful rerank.
    """

    name = "doppel.source-aware-reranker"
    version = "1:metadata-json+source-token-mmr"

    def __init__(
        self,
        provider: PersonalMemoryReranker,
        config: SourceAwareRerankConfig | None = None,
    ):
        self.provider = provider
        self.config = config or SourceAwareRerankConfig()
        self.last_summary: PersonalMemoryRerankSummary | None = None
        self.last_order: list[str] = []

    async def rerank(
        self, query: str, candidates: Sequence[RecallResult], *, limit: int
    ) -> Sequence[RecallResult]:
        if (
            type(limit) is not int
            or not 1 <= limit <= self.config.max_candidates
            or not query.strip()
        ):
            raise ValueError("nonblank query and bounded positive limit required")
        bound = [c.model_copy(deep=True) for c in candidates]
        keys = [(c.scope.scope_key if c.scope else None, c.memory_id) for c in bound]
        if any(c.scope is None or not c.memory_id for c in bound):
            raise MemoryIsolationError(
                "source-aware reranking requires scoped candidate IDs"
            )
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate scoped rerank candidate")
        request = PersonalMemoryRerankRequest(
            question=query,
            items=[
                PersonalMemoryRerankItem(
                    item_id=f"candidate-{i}",
                    content=source_content(c)
                    if self.config.include_metadata
                    else c.raw_text or c.fact,
                )
                for i, c in enumerate(bound)
            ],
        )
        request_snapshot = request.model_dump_json()
        identity = self.provider.name, self.provider.version
        scores, summary = await score_personal_memories(
            self.provider,
            request,
            PersonalMemoryRerankConfig(
                max_candidates=self.config.max_candidates,
                max_input_chars=self.config.max_input_chars,
                timeout_seconds=self.config.timeout_seconds,
            ),
            total_candidates=len(bound),
        )
        self.last_summary = summary
        if request_snapshot != request.model_dump_json() or identity != (
            self.provider.name,
            self.provider.version,
        ):
            raise RuntimeError("rerank provider changed bound request/identity")
        if summary.status not in {"completed", "not_run"}:
            raise RuntimeError(
                f"source-aware reranking did not complete: {summary.status}"
            )
        values = [scores[f"candidate-{i}"] for i in range(len(bound))]
        order = mmr_order(bound, values, self.config.diversity_weight, limit)
        self.last_order = [bound[i].memory_id for i in order]
        return [bound[i] for i in order]
