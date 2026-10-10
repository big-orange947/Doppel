"""Opt-in source-coherent raw evidence, separate from owner facts and counts.

The host resolves real reply/thread/turn links, not semantic guesses. A bounded
window may displace lower-ranked raw hits; it is not a relevance or truth claim.
No model, index mutation, benchmark metadata convention or default policy here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from doppel_memory.high_config import HighConfigRetrieval, HighConfigRetrievalResult
from doppel_memory.models import Actor, MemoryIsolationError, MemoryRecord, MemoryScope
from doppel_memory.query import _observation_cutoff
from doppel_memory.store import MemoryStore


class RawContextResolver(Protocol):
    """Host-owned source links. No question, answer or relevance labels supplied.

    Return only linked records in the anchor's exact scope, within ``limit``.
    In group chats adjacency alone is not a reply link. Hosts must validate their
    source/thread mapping; Store reload verifies record integrity, not link truth.
    """

    async def resolve_context(
        self,
        scope: MemoryScope,
        anchor: MemoryRecord,
        *,
        observed_until: datetime,
        limit: int,
    ) -> Sequence[MemoryRecord]: ...


class SourceWindowConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    anchor_limit: int = Field(default=3, ge=1, le=20)
    neighbors_per_anchor: int = Field(default=2, ge=1, le=20)
    timeout_seconds: float = Field(default=5, gt=0, le=120)


class SourceContextLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scope_key: str
    anchor_memory_id: str
    linked_memory_id: str


class SourceWindowResult(HighConfigRetrievalResult):
    profile: str = "personal-high-config-source-window-v1"
    source_window_config: SourceWindowConfig
    source_context_links: list[SourceContextLink] = Field(default_factory=list)
    source_window_failures: int = 0
    source_window_rejections: int = 0
    source_window_added_ids: list[str] = Field(default_factory=list)
    source_window_displaced_ids: list[str] = Field(default_factory=list)
    source_link_semantics_certified: bool = False


async def expand_source_window(
    result: HighConfigRetrievalResult,
    store: MemoryStore,
    resolver: RawContextResolver,
    *,
    config: SourceWindowConfig | None = None,
    raw_output_limit: int = 20,
) -> SourceWindowResult:
    """Keep leading anchors, then verified neighbors, then trailing raw hits.

    Exact-scope violations propagate. Bad resolver responses degrade visibly;
    Store failures propagate. Copies prevent the resolver mutating input evidence.
    This operation never changes personal hits, graph paths, backing or counts.
    """
    policy = config or SourceWindowConfig()
    if isinstance(result, SourceWindowResult):
        raise TypeError("source window already expanded")
    if not 1 <= raw_output_limit <= 1000 or policy.anchor_limit > raw_output_limit:
        raise ValueError("invalid source-window output bound")
    allowed = {s.scope_key for s in result.base.plan.scopes}
    originals = result.raw_dialogue
    if len(originals) > raw_output_limit:
        raise ValueError("raw input exceeds frozen output bound")
    cutoff = _observation_cutoff(result.base.plan)
    neighbors: dict[str, MemoryRecord] = {}
    links: list[SourceContextLink] = []
    failures = rejections = 0
    stale_anchors: set[str] = set()
    for anchor in originals[: policy.anchor_limit]:
        if anchor.scope.scope_key not in allowed:
            raise MemoryIsolationError("source-window anchor escaped authorized scope")
        current = await store.get(anchor.scope, anchor.memory_id)
        if current is not None and current.scope != anchor.scope:
            raise MemoryIsolationError("source-window anchor Store scope mismatch")
        if current != anchor or not HighConfigRetrieval._raw_eligible(
            anchor, anchor.scope, cutoff
        ):
            rejections += 1
            stale_anchors.add(anchor.memory_id)
            continue
        try:
            resolved = await asyncio.wait_for(
                resolver.resolve_context(
                    anchor.scope.model_copy(deep=True),
                    anchor.model_copy(deep=True),
                    observed_until=cutoff,
                    limit=policy.neighbors_per_anchor,
                ),
                timeout=policy.timeout_seconds,
            )
        except MemoryIsolationError:
            raise
        except Exception:  # noqa: BLE001 - redact untrusted resolver exceptions
            failures += 1
            continue
        if (
            not isinstance(resolved, Sequence)
            or isinstance(resolved, (str, bytes))
            or len(resolved) > policy.neighbors_per_anchor
            or any(not isinstance(r, MemoryRecord) for r in resolved)
        ):
            failures += 1
            continue
        # Check the complete returned window before consuming any of its text.
        if any(r.scope != anchor.scope for r in resolved):
            raise MemoryIsolationError("source-window neighbor escaped anchor scope")
        for candidate in resolved:
            record = await store.get(anchor.scope, candidate.memory_id)
            if record is not None and record.scope != anchor.scope:
                raise MemoryIsolationError("source-window Store reload escaped scope")
            if (
                record is None
                or record != candidate
                or not HighConfigRetrieval._raw_eligible(record, anchor.scope, cutoff)
            ):
                rejections += 1
                continue
            if record.memory_id == anchor.memory_id:
                continue
            neighbors.setdefault(record.memory_id, record.model_copy(deep=True))
            link = SourceContextLink(
                scope_key=anchor.scope.scope_key,
                anchor_memory_id=anchor.memory_id,
                linked_memory_id=record.memory_id,
            )
            if link not in links:
                links.append(link)
    selected: dict[str, MemoryRecord] = {}
    for record in [
        *originals[: policy.anchor_limit],
        *neighbors.values(),
        *originals[policy.anchor_limit :],
    ]:
        if record.memory_id in stale_anchors:
            continue
        if len(selected) >= raw_output_limit:
            break
        selected.setdefault(record.memory_id, record.model_copy(deep=True))
    original_ids = {r.memory_id for r in originals}
    warnings = list(result.warnings)
    if failures:
        warnings.append("source_window_resolver_degraded")
    if rejections:
        warnings.append("source_window_records_rejected")
    return SourceWindowResult(
        **{
            **result.model_dump(),
            "profile": "personal-high-config-source-window-v1",
            "raw_dialogue": list(selected.values()),
            "warnings": warnings,
        },
        source_window_config=policy,
        source_context_links=[l for l in links if l.linked_memory_id in selected],
        source_window_failures=failures,
        source_window_rejections=rejections,
        source_window_added_ids=[k for k in selected if k not in original_ids],
        source_window_displaced_ids=[
            r.memory_id for r in originals if r.memory_id not in selected
        ],
    )


class SourceWindowRetrieval:
    """Explicit composition around an unchanged HighConfigRetrieval instance."""

    def __init__(
        self,
        retrieval: HighConfigRetrieval,
        resolver: RawContextResolver,
        *,
        config: SourceWindowConfig | None = None,
    ) -> None:
        self.retrieval, self.resolver = retrieval, resolver
        self.config = config or SourceWindowConfig()
        if self.config.anchor_limit > retrieval.raw_output_limit:
            raise ValueError("source-window anchors exceed raw output bound")

    async def query(
        self,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        now: datetime,
        calendar_timezone: str = "UTC",
        default_subject: str = Actor.OWNER,
        default_subject_id: str = "",
        allowed_subject_ids: Sequence[str] = (),
        trace_limit: int = 0,
        observed_until: datetime | None = None,
    ) -> SourceWindowResult:
        result = await self.retrieval.query(
            query,
            scopes,
            now=now,
            calendar_timezone=calendar_timezone,
            default_subject=default_subject,
            default_subject_id=default_subject_id,
            allowed_subject_ids=allowed_subject_ids,
            trace_limit=trace_limit,
            observed_until=observed_until,
        )
        return await expand_source_window(
            result,
            self.retrieval.store,
            self.resolver,
            config=self.config,
            raw_output_limit=self.retrieval.raw_output_limit,
        )
