"""Opt-in read-only source neighborhoods before model selection, never facts."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doppel_memory.models import MemoryIsolationError, MemoryScope, RecallResult
from doppel_memory.source_aware_rerank import source_content
from doppel_memory.source_order import SourceOrderResolver, SourcePosition
from doppel_memory.store import MemoryStore
from integrations.aml.context import (
    AttributedContextRetriever,
    ContextSnippet,
    EventResolver,
)


class NeighborhoodConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    before: int = Field(default=1, ge=0, le=4)
    after: int = Field(default=1, ge=0, le=4)
    max_anchors: int = Field(default=80, ge=1, le=1000)
    max_candidates: int = Field(default=240, ge=1, le=1000)
    max_content_bytes: int = Field(default=300_000, ge=1)
    timeout_seconds: float = Field(default=30, gt=0, le=300, allow_inf_nan=False)

    @model_validator(mode="after")
    def _keep_anchor_capacity(self):
        if self.max_candidates < self.max_anchors:
            raise ValueError("candidate capacity must retain the allowed anchor window")
        return self


class NeighborhoodLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    anchor_memory_id: str
    neighbor_memory_id: str
    offset: int


class NeighborhoodResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snippets: list[ContextSnippet]
    links: list[NeighborhoodLink]
    anchor_count: int
    added_count: int
    content_bytes: int
    candidate_budget_exhausted: bool
    unvisited_anchors: int
    rejected: dict[str, int]
    final_store_checks: int


def as_candidate(scope: MemoryScope, snippet: ContextSnippet) -> RecallResult:
    if snippet.scope_key != scope.scope_key:
        raise MemoryIsolationError("neighborhood snippet escaped requested scope")
    return RecallResult(
        scope=scope.model_copy(deep=True),
        memory_id=snippet.memory_id,
        fact=snippet.text,
        raw_text=snippet.text,
        source_event_id=snippet.evidence_id,
        actor=snippet.actor,
        authority=snippet.authority,
        valid_at=snippet.at,
        similarity=snippet.similarity,
    )


class _Ids:
    def __init__(self, scope, identities):
        self.scope_key, self.identities = scope.scope_key, identities

    async def search(self, store, query, scopes, *, filters=None, limit=10):
        if len(scopes) != 1 or scopes[0].scope_key != self.scope_key:
            raise MemoryIsolationError("neighborhood ID lookup escaped scope")
        return [
            RecallResult(
                scope=scopes[0].model_copy(deep=True),
                memory_id=key,
                fact="untrusted",
                similarity=score,
            )
            for key, score in self.identities[:limit]
        ]


class AttributedNeighborhoodExpander:
    """Only current authorized originals are returned; no ranking or LLM calls.

    The host's source-order index is a trusted input, not reconstructed from
    transport chunk indices or timestamps. Resolver replies still undergo exact
    scope/session/offset/ID checks and fresh Store/provenance validation.
    """

    def __init__(
        self,
        store: MemoryStore,
        *,
        resolve_event: EventResolver,
        source_order: SourceOrderResolver,
        config: NeighborhoodConfig | None = None,
    ):
        self.store, self.resolve_event, self.source_order = (
            store,
            resolve_event,
            source_order,
        )
        self.config = config or NeighborhoodConfig()

    async def _current(self, scope, identities):
        if not identities:
            return [], {}, 0
        result = await AttributedContextRetriever(
            self.store,
            strategy=_Ids(scope, identities),
            resolve_event=self.resolve_event,
            candidate_multiplier=1,
        ).search(scope, "source neighborhood validation", limit=len(identities))
        return result.snippets, result.rejected, result.final_store_checks

    async def _locate(self, scope, memory_id):
        call_scope = scope.model_copy(deep=True)
        result = await self.source_order.locate(call_scope, memory_id)
        if call_scope.scope_key != scope.scope_key:
            raise MemoryIsolationError("source-order resolver changed scope")
        if result is None:
            return None
        position = SourcePosition.model_validate(result)
        if position.scope_key != scope.scope_key or position.memory_id != memory_id:
            raise MemoryIsolationError(
                "source-order lookup escaped exact scope or identity"
            )
        return position.model_copy(deep=True)

    @staticmethod
    def _position_matches(position, snippet):
        if (
            position.session_id != snippet.session_id
            or position.evidence_id != snippet.evidence_id
        ):
            raise MemoryIsolationError(
                "source position differs from authoritative session/evidence"
            )

    def _size(self, scope, snippet):
        return len(source_content(as_candidate(scope, snippet)).encode("utf-8"))

    @staticmethod
    def _remember(position, by_id, by_order):
        order = (position.session_id, position.ordinal)
        if position.memory_id in by_id and by_id[position.memory_id] != position:
            raise ValueError("source identity changed position during expansion")
        if order in by_order and by_order[order] != position.memory_id:
            raise ValueError("different source IDs share one session ordinal")
        by_id[position.memory_id] = position
        by_order[order] = position.memory_id

    async def expand(
        self, scope: MemoryScope, anchors: Sequence[ContextSnippet]
    ) -> NeighborhoodResult:
        bound = scope.model_copy(deep=True)
        inputs = [a.model_copy(deep=True) for a in anchors]
        if len(inputs) > self.config.max_anchors:
            raise ValueError("anchor window exceeds configured bound")
        if any(a.scope_key != bound.scope_key for a in inputs):
            raise MemoryIsolationError("neighborhood anchors escaped requested scope")
        if len({a.memory_id for a in inputs}) != len(inputs):
            raise ValueError("duplicate neighborhood anchor ID")
        return await asyncio.wait_for(
            self._expand(bound, inputs), timeout=self.config.timeout_seconds
        )

    async def _expand(self, scope, inputs):
        current, rejected, checks = await self._current(
            scope, [(a.memory_id, a.similarity) for a in inputs]
        )
        rejected = Counter(rejected)
        snapshots = {a.memory_id: a for a in inputs}
        anchors = []
        for item in current:
            if item != snapshots[item.memory_id]:
                rejected["changed_anchor"] += 1
            else:
                anchors.append(item)
        pool = {a.memory_id: a for a in anchors}
        size = sum(self._size(scope, s) for s in anchors)
        if size > self.config.max_content_bytes:
            raise ValueError("anchor content exceeds configured byte budget")
        positions, by_order, links, unvisited, exhausted = {}, {}, [], 0, False
        for index, anchor in enumerate(anchors):
            if len(pool) >= self.config.max_candidates:
                exhausted, unvisited = True, len(anchors) - index
                break
            position = await self._locate(scope, anchor.memory_id)
            if position is None:
                rejected["position_unavailable"] += 1
                continue
            self._position_matches(position, anchor)
            self._remember(position, positions, by_order)
            call_scope, call_position = (
                scope.model_copy(deep=True),
                position.model_copy(deep=True),
            )
            refs = await self.source_order.neighbors(
                call_scope,
                call_position,
                before=self.config.before,
                after=self.config.after,
            )
            if call_scope.scope_key != scope.scope_key or call_position != position:
                raise MemoryIsolationError(
                    "neighborhood resolver changed bound scope/anchor"
                )
            if len(refs) > self.config.before + self.config.after:
                raise ValueError("resolver returned an oversized neighborhood")
            refs = [
                SourcePosition.model_validate(r).model_copy(deep=True) for r in refs
            ]
            ordinals, ids = set(), set()
            for ref in refs:
                if (
                    ref.scope_key != scope.scope_key
                    or ref.session_id != position.session_id
                ):
                    raise MemoryIsolationError("neighbor escaped exact scope/session")
                offset = ref.ordinal - position.ordinal
                if (
                    offset == 0
                    or not -self.config.before <= offset <= self.config.after
                ):
                    raise ValueError("neighbor offset outside requested source window")
                if ref.ordinal in ordinals or ref.memory_id in ids:
                    raise ValueError("duplicate neighbor source position/ID")
                ordinals.add(ref.ordinal)
                ids.add(ref.memory_id)
            anchor_ordinal = position.ordinal
            for ref in sorted(
                refs, key=lambda r: (abs(r.ordinal - anchor_ordinal), r.ordinal)
            ):
                actual = await self._locate(scope, ref.memory_id)
                if actual != ref:
                    raise ValueError(
                        "neighbor does not match explicit source-order lookup"
                    )
                found, errors, checked = await self._current(
                    scope, [(ref.memory_id, 0.0)]
                )
                checks += checked
                rejected.update(errors)
                if not found:
                    continue
                item = found[0]
                self._position_matches(ref, item)
                if item.memory_id not in pool:
                    if len(pool) >= self.config.max_candidates:
                        exhausted = True
                        rejected["candidate_budget_skip"] += 1
                        continue
                    cost = self._size(scope, item)
                    if size + cost > self.config.max_content_bytes:
                        rejected["byte_budget_skip"] += 1
                        continue
                    pool[item.memory_id] = item
                    size += cost
                self._remember(ref, positions, by_order)
                links.append(
                    NeighborhoodLink(
                        anchor_memory_id=anchor.memory_id,
                        neighbor_memory_id=item.memory_id,
                        offset=ref.ordinal - position.ordinal,
                    )
                )
        # Source order is checked before the final Store reload, not inferred from it.
        changed_order = set()
        for key, position in positions.items():
            if await self._locate(scope, key) != position:
                changed_order.add(key)
                rejected["source_order_changed"] += 1
        final, errors, checked = await self._current(
            scope,
            [
                (key, item.similarity)
                for key, item in pool.items()
                if key not in changed_order
            ],
        )
        checks += checked
        rejected.update(errors)
        stable = []
        for item in final:
            if item != pool[item.memory_id]:
                rejected["changed_after_expansion"] += 1
            else:
                stable.append(item)
        keys, anchor_keys = (
            {s.memory_id for s in stable},
            {a.memory_id for a in anchors},
        )
        live_links = [
            link
            for link in links
            if link.anchor_memory_id in keys and link.neighbor_memory_id in keys
        ]
        supported = anchor_keys | {link.neighbor_memory_id for link in live_links}
        rejected["orphaned_after_anchor_change"] += sum(
            s.memory_id not in supported for s in stable
        )
        stable = [s for s in stable if s.memory_id in supported]
        keys = {s.memory_id for s in stable}
        return NeighborhoodResult(
            snippets=stable,
            links=[link for link in live_links if link.neighbor_memory_id in keys],
            anchor_count=len(anchors),
            added_count=len(keys - anchor_keys),
            content_bytes=sum(self._size(scope, s) for s in stable),
            candidate_budget_exhausted=exhausted,
            unvisited_anchors=unvisited,
            rejected={k: v for k, v in rejected.items() if v},
            final_store_checks=checks,
        )
