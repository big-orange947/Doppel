"""Opt-in source-bound passages over attributed historical dialogue.

This composition does not change normal recall/search_evidence, persist
fragments, summarize sources, or claim that a fragment answers a question.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, deque
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryIsolationError,
    MemoryRecord,
    MemoryScope,
    RecallResult,
)
from doppel_memory.passages import TextSpanConfig, iter_text_spans
from doppel_memory.retriever import Reranker
from integrations.aml.context import AttributedContextRetriever, ContextSnippet


class AttributedPassage(ContextSnippet):
    # Keep the historical-dialogue channel: a substring is not a personal fact.
    passage_id: str
    source_text_sha256: str
    source_char_count: int
    start: int
    end: int
    offset_unit: Literal["unicode-codepoint"] = "unicode-codepoint"


class PassageSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passages: list[AttributedPassage]
    source_count: int
    candidates_seen: int
    candidate_budget_exhausted: bool
    rejected: dict[str, int]
    final_store_checks: int


class PassageRetrievalConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    source_limit: int = Field(default=20, ge=1, le=1000)
    max_passages: int = Field(default=80, ge=1, le=10000)
    max_chars: int = Field(default=1200, ge=1)
    overlap_chars: int = Field(default=160, ge=0)

    def span_config(self) -> TextSpanConfig:
        return TextSpanConfig(self.max_chars, self.overlap_chars)


def _make_passages(sources, config):
    """Round-robin source windows, bounded before any optional model call."""
    queue = deque()
    for source in sources:
        queue.append(
            (
                source,
                iter(iter_text_spans(source.text, config.span_config())),
                hashlib.sha256(source.text.encode("utf-8")).hexdigest(),
            )
        )
    candidates = []
    while queue and len(candidates) < config.max_passages:
        source, spans, digest = queue.popleft()
        span = next(spans, None)
        if span is None:
            continue
        identity = json.dumps(
            [
                source.scope_key,
                source.memory_id,
                source.evidence_id,
                digest,
                span.start,
                span.end,
            ],
            ensure_ascii=False,
        )
        candidates.append(
            AttributedPassage(
                **source.model_dump(exclude={"text"}),
                text=span.text,
                passage_id="span-" + hashlib.sha256(identity.encode()).hexdigest(),
                source_text_sha256=digest,
                source_char_count=len(source.text),
                start=span.start,
                end=span.end,
            )
        )
        queue.append((source, spans, digest))
    exhausted = any(next(spans, None) is not None for _, spans, _ in queue)
    return candidates, exhausted


class AttributedPassageRetriever:
    """Reuse authorized source search; only optional fragment ordering is new.

    Reranker IDs are passage IDs, not original memory IDs. Only its order is
    consumed. Source identity/role/text always come from revalidated snapshots.
    Instances inherit the source retriever's Store/resolver, never wider scopes.
    """

    def __init__(
        self,
        source_retriever: AttributedContextRetriever,
        *,
        config: PassageRetrievalConfig | None = None,
        reranker: Reranker | None = None,
    ):
        self.source_retriever = source_retriever
        self.config = config or PassageRetrievalConfig()
        self.config.span_config()
        self.reranker = reranker

    async def _snapshot(
        self, scope: MemoryScope, source: ContextSnippet
    ) -> MemoryRecord | None:
        scope = scope.model_copy(deep=True)
        expected = scope.scope_key
        if source.scope_key != expected:
            raise MemoryIsolationError("passage source escaped bound scope")
        record = await self.source_retriever.store.get(scope, source.memory_id)
        if scope.scope_key != expected:
            raise MemoryIsolationError("passage Store changed bound scope")
        if record is None:
            return None
        if record.scope.scope_key != scope.scope_key:
            raise MemoryIsolationError("passage Store escaped bound scope")
        raw = record.metadata.get("raw", {})
        actor = Actor.OWNER if source.role == "user" else Actor.AGENT
        if (
            not isinstance(raw, dict)
            or record.actor != actor
            or record.authority != FactAuthority.of(actor)
            or record.state != "confirmed"
            or record.kind != "event"
            or record.extractor != "ingestor"
            or record.source_event_id != source.evidence_id
            or record.actor != source.actor
            or record.authority != source.authority
            or record.created_at != source.at
            or raw.get("source_text") != source.text
            or record.content != source.text.strip()
            or raw.get("transport_role") != source.role
            or raw.get("session_id") != source.session_id
            or raw.get("turn_index") != source.transport_turn_index
        ):
            return None
        original = await self.source_retriever.resolve_event(scope, source.evidence_id)
        if scope.scope_key != expected:
            raise MemoryIsolationError("passage resolver changed bound scope")
        if original is None or original.model_dump(mode="json") != record.model_dump(
            mode="json"
        ):
            return None
        return record.model_copy(deep=True)

    async def resolve_original(
        self, scope: MemoryScope, passage: AttributedPassage
    ) -> str:
        """Reload original and verify hash/offsets; never return stale or alien text."""
        bound = scope.model_copy(deep=True)
        expected = bound.scope_key
        if passage.scope_key != bound.scope_key:
            raise MemoryIsolationError("passage resolution escaped bound scope")
        record = await self.source_retriever.store.get(bound, passage.memory_id)
        if bound.scope_key != expected:
            raise MemoryIsolationError("passage resolution Store changed scope")
        if record is None or record.scope.scope_key != bound.scope_key:
            raise ValueError("passage original unavailable")
        raw = record.metadata.get("raw")
        if not isinstance(raw, dict) or not isinstance(raw.get("source_text"), str):
            raise TypeError("passage original unavailable")
        text = raw["source_text"]
        source = ContextSnippet.model_validate(
            passage.model_dump(
                include=set(ContextSnippet.model_fields), exclude={"text"}
            )
            | {"text": text}
        )
        if (
            await self._snapshot(bound, source) is None
            or hashlib.sha256(text.encode("utf-8")).hexdigest()
            != passage.source_text_sha256
            or passage.source_char_count != len(text)
            or not 0 <= passage.start < passage.end <= len(text)
            or text[passage.start : passage.end] != passage.text
        ):
            raise ValueError("passage source/hash/offset mismatch")
        return text

    async def search(
        self, scope: MemoryScope, query: str, *, limit: int = 20
    ) -> PassageSearchResult:
        if type(limit) is not int or not 1 <= limit <= self.config.max_passages:
            raise ValueError("passage limit exceeds configured bound")
        bound = scope.model_copy(deep=True)
        expected = bound.scope_key
        result = await self.source_retriever.search(
            bound, query, limit=self.config.source_limit
        )
        if bound.scope_key != expected:
            raise MemoryIsolationError("source search changed passage scope")
        sources, snapshots, rejected = {}, {}, Counter(result.rejected)
        for source in result.snippets:
            snapshot = await self._snapshot(bound, source)
            if snapshot is None:
                rejected["source_changed_before_splitting"] += 1
                continue
            if source.memory_id in sources:
                raise ValueError("duplicate passage source")
            sources[source.memory_id], snapshots[source.memory_id] = source, snapshot
        candidates, exhausted = _make_passages(list(sources.values()), self.config)
        by_id = {p.passage_id: p for p in candidates}
        ordering = [
            RecallResult(
                scope=bound.model_copy(deep=True),
                memory_id=p.passage_id,
                fact=p.text,
                raw_text=p.text,
                actor=p.actor,
                authority=p.authority,
                source_event_id=p.evidence_id,
                valid_at=p.at,
                similarity=p.similarity,
            )
            for p in candidates
        ]
        if self.reranker is not None and ordering:
            ordering = list(await self.reranker.rerank(query, ordering, limit=limit))
        if bound.scope_key != expected:
            raise MemoryIsolationError("passage ordering changed scope")
        selected, seen, checked = [], set(), {}
        for candidate in ordering:
            if candidate.scope is None or candidate.scope.scope_key != expected:
                raise MemoryIsolationError("passage reranker escaped bound scope")
            if candidate.memory_id not in by_id:
                raise ValueError("passage reranker introduced noncandidate")
            if candidate.memory_id in seen:
                continue
            seen.add(candidate.memory_id)
            passage = by_id[candidate.memory_id]
            if passage.memory_id not in checked:
                fresh = await self._snapshot(bound, sources[passage.memory_id])
                checked[passage.memory_id] = fresh is not None and fresh.model_dump(
                    mode="json"
                ) == snapshots[passage.memory_id].model_dump(mode="json")
            if not checked[passage.memory_id]:
                rejected["source_changed_after_passage_ordering"] += 1
                continue
            selected.append(passage)
            if len(selected) == limit:
                break
        return PassageSearchResult(
            passages=selected,
            source_count=len(sources),
            candidates_seen=len(candidates),
            candidate_budget_exhausted=exhausted,
            rejected=dict(rejected),
            final_store_checks=len(checked),
        )
