"""Attributed historical dialogue, separate from personal-fact query results.

Hosts supply a candidate strategy (for example lexical/vector RRF) and exact
scope event resolver. Every returned snippet comes from the authoritative Store,
not cached candidate text. This repository composition is not an AML server.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryFilter,
    MemoryIsolationError,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    RecallResult,
)
from doppel_memory.retriever import Reranker, RetrievalStrategy
from doppel_memory.store import MemoryStore

EventResolver = Callable[[MemoryScope, str], Awaitable[MemoryRecord | None]]


class ContextSnippet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: Literal["historical-dialogue-context"] = "historical-dialogue-context"
    scope_key: str
    memory_id: str
    evidence_id: str
    role: Literal["user", "assistant"]
    actor: str
    authority: FactAuthority
    session_id: str
    transport_turn_index: int
    at: datetime
    text: str
    similarity: float


class ContextSearchResult(BaseModel):
    snippets: list[ContextSnippet]
    candidates_seen: int
    revalidated: int
    rejected: dict[str, int]
    candidate_evidence_ids: list[str]
    final_store_checks: int


class AttributedContextRetriever:
    def __init__(
        self,
        store: MemoryStore,
        *,
        strategy: RetrievalStrategy,
        resolve_event: EventResolver,
        reranker: Reranker | None = None,
        candidate_multiplier: int = 4,
    ) -> None:
        if type(candidate_multiplier) is not int or candidate_multiplier < 1:
            raise ValueError("candidate_multiplier must be positive")
        self.store, self.strategy = store, strategy
        self.resolve_event, self.reranker = resolve_event, reranker
        self.candidate_multiplier = candidate_multiplier

    async def search(
        self, scope: MemoryScope, query: str, *, limit: int = 10
    ) -> ContextSearchResult:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("context limit must be between 1 and 1000")
        if not query.strip():
            raise ValueError("context query must be nonempty")
        bound_scope = scope.model_copy(deep=True)
        expected_scope_key = bound_scope.scope_key
        candidates = await self.strategy.search(
            self.store,
            query,
            [bound_scope],
            filters=MemoryFilter(
                kinds={MemoryKind.EVENT}, states={MemoryState.CONFIRMED}
            ),
            limit=limit * self.candidate_multiplier,
        )
        rejected: Counter[str] = Counter()
        if bound_scope.scope_key != expected_scope_key:
            raise MemoryIsolationError("context strategy changed the bound scope")
        snippets: dict[str, ContextSnippet] = {}
        snapshots: dict[str, MemoryRecord] = {}
        validated: list[RecallResult] = []
        for candidate in candidates:
            if (
                candidate.scope is None
                or candidate.scope.scope_key != bound_scope.scope_key
            ):
                raise MemoryIsolationError("context candidate escaped requested scope")
            if not candidate.memory_id:
                rejected["missing_memory_id"] += 1
                continue
            if candidate.memory_id in snippets:
                rejected["duplicate"] += 1
                continue
            record = await self.store.get(bound_scope, candidate.memory_id)
            if record is None:
                rejected["missing_store_record"] += 1
                continue
            if record.scope.scope_key != bound_scope.scope_key:
                raise MemoryIsolationError(
                    "context Store reload escaped requested scope"
                )
            if record.state != MemoryState.CONFIRMED:
                rejected["inactive_or_unconfirmed"] += 1
                continue
            if record.kind != MemoryKind.EVENT or record.extractor != "ingestor":
                rejected["not_raw_event"] += 1
                continue
            raw = record.metadata.get("raw")
            if not isinstance(raw, dict) or (
                not isinstance(raw.get("transport_role"), str)
                or raw.get("transport_role") not in {"user", "assistant"}
                or not isinstance(raw.get("source_text"), str)
                or not isinstance(raw.get("session_id"), str)
                or not raw["session_id"]
                or type(raw.get("turn_index")) is not int
                or raw["turn_index"] < 0
                or raw["source_text"].strip() != record.content
                or record.actor not in {Actor.OWNER, Actor.AGENT, Actor.SYSTEM}
                or record.authority != FactAuthority.of(record.actor)
            ):
                rejected["invalid_attribution"] += 1
                continue
            source = await self.resolve_event(bound_scope, record.source_event_id)
            if (
                source is None
                or source.memory_id != record.memory_id
                or (
                    source.scope.scope_key != bound_scope.scope_key
                    or source.model_dump(mode="json") != record.model_dump(mode="json")
                    or not record.source_event_id
                )
            ):
                rejected["unresolved_provenance"] += 1
                continue
            if not math.isfinite(candidate.similarity):
                rejected["invalid_similarity"] += 1
                continue
            snippet = ContextSnippet(
                scope_key=bound_scope.scope_key,
                memory_id=record.memory_id,
                evidence_id=record.source_event_id,
                role=raw["transport_role"],
                actor=record.actor,
                authority=record.authority,
                session_id=raw["session_id"],
                transport_turn_index=raw["turn_index"],
                at=record.created_at,
                text=raw["source_text"],
                similarity=candidate.similarity,
            )
            snippets[record.memory_id] = snippet
            snapshots[record.memory_id] = record.model_copy(deep=True)
            validated.append(
                RecallResult(
                    scope=bound_scope,
                    memory_id=record.memory_id,
                    fact=record.content,
                    actor=record.actor,
                    authority=record.authority,
                    kind=record.kind,
                    source_event_id=record.source_event_id,
                    raw_text=raw["source_text"],
                    valid_at=record.created_at,
                    similarity=candidate.similarity,
                )
            )
        ordered = validated
        if self.reranker is not None:
            ordered = list(await self.reranker.rerank(query, validated, limit=limit))
        result, seen = [], set()
        final_checks = 0
        if bound_scope.scope_key != expected_scope_key:
            raise MemoryIsolationError("context reranker changed the bound scope")
        for candidate in ordered:
            if (
                candidate.scope is None
                or candidate.scope.scope_key != bound_scope.scope_key
            ):
                raise MemoryIsolationError("context reranker escaped requested scope")
            if candidate.memory_id not in snippets:
                raise ValueError("context reranker introduced a noncandidate record")
            if candidate.memory_id not in seen:
                seen.add(candidate.memory_id)
                # Optional neural ordering may await a slow model. Never return a
                # snapshot revoked/changed in the authoritative Store meanwhile.
                refreshed = await self.store.get(bound_scope, candidate.memory_id)
                final_checks += 1
                if refreshed is None or refreshed.model_dump(mode="json") != snapshots[
                    candidate.memory_id
                ].model_dump(mode="json"):
                    rejected["changed_after_ordering"] += 1
                    continue
                # Only order is consumed. Reranker-supplied text/role is never trusted.
                result.append(snippets[candidate.memory_id])
                if len(result) >= limit:
                    break
        return ContextSearchResult(
            snippets=result[:limit],
            candidates_seen=len(candidates),
            revalidated=len(snippets),
            rejected=dict(rejected),
            candidate_evidence_ids=[
                snippet.evidence_id for snippet in snippets.values()
            ],
            final_store_checks=final_checks,
        )
