"""Question/gold-free adapters for the opt-in public-memory high-config pilot.

Packing uses whole validated records and fixed cyclic channel quotas. Source
position labels belong to scoring only; none influence ordering or selection.
"""

from __future__ import annotations

from itertools import zip_longest

from benchmarks.public_memory_comparison import (
    CONTEXT_BYTE_LIMIT,
    ITEM_LIMIT,
    check_raw,
    context_item,
    encoded,
)
from doppel_memory.models import MemoryIsolationError
from doppel_memory.personal_rerank import (
    PersonalMemoryRerankItem,
    PersonalMemoryRerankRequest,
)
from doppel_memory.relation import RelationRerankScore


class JournalSourceResolver:
    """Resolve exact-scope evidence events through an immutable source journal."""

    def __init__(self, store, sources):
        self.store, self.sources = store, sources

    async def resolve_event(self, scope, evidence_id):
        source = self.sources.get((scope.scope_key, evidence_id))
        if source is None:
            return None
        record = await self.store.get(scope, source.memory_id)
        if record is None:
            return None
        if record.scope != scope:
            raise MemoryIsolationError("journal source scope mismatch")
        check_raw(record, source, evidence_id)
        return record


class LocalRelationCrossEncoder:
    """Use the same content-only local scorer for paths, never metadata hints."""

    def __init__(self, provider):
        self.provider = provider
        self.name, self.version = provider.name, provider.version

    async def rerank(self, request):
        scores = await self.provider.rerank(
            PersonalMemoryRerankRequest(
                question=request.query_text,
                items=[
                    PersonalMemoryRerankItem(item_id=i.item_id, content=i.fact)
                    for i in request.items
                ],
            )
        )
        return [RelationRerankScore(item_id=s.item_id, score=s.score) for s in scores]


def pack_channels(channels, *, item_limit=ITEM_LIMIT, byte_limit=CONTEXT_BYTE_LIMIT):
    """Stable round-robin memory/raw/backing with whole-item fit, no truncation.

    A record eligible in two channels occupies one slot; report every provenance
    channel separately. Oversized items are skipped, not shortened or substituted.
    This is a fixed host policy, not a learned answer-aware packer.
    """
    if item_limit < 1 or byte_limit < 2:
        raise ValueError("positive item limit and JSON byte budget required")
    selected, observations, seen = [], [], set()
    names = ("memory", "raw", "backing")
    for rank, row in enumerate(zip_longest(*(channels.get(n, []) for n in names)), 1):
        for name, item in zip(names, row, strict=True):
            if item is None:
                continue
            identity = item["memory_id"]
            decision = "selected"
            if identity in seen:
                decision = "duplicate"
            elif len(selected) >= item_limit:
                decision = "item_budget"
            elif len(encoded([*selected, item])) > byte_limit:
                decision = "byte_budget"
            if decision == "selected":
                selected.append(item)
                seen.add(identity)
            observations.append(
                {
                    "channel": name,
                    "rank": rank,
                    "memory_id": identity,
                    "decision": decision,
                }
            )
    return selected, {
        "policy": "whole-item-memory-raw-backing-round-robin-v1",
        "item_limit": item_limit,
        "byte_limit": byte_limit,
        "encoded_bytes": len(encoded(selected)),
        "observations": observations,
        "text_truncated": False,
    }


def prepare_context(result, records, sources):
    memories = (
        [c.record for c in result.hybrid.assembly.candidates]
        if result.hybrid
        else [h.record for h in result.base.hits]
    )
    channels = {}
    for name, candidates in (
        ("memory", memories),
        ("raw", result.raw_dialogue),
        ("backing", result.backing_sources),
    ):
        items = []
        for record in candidates:
            authoritative = records.get(record.memory_id)
            if authoritative != record:
                raise ValueError("retrieval record differs from source snapshot")
            item = context_item(record, records, sources)
            if item is not None:
                items.append(item)
        channels[name] = items
    packed, audit = pack_channels(channels)
    audit["channel_candidate_counts"] = {k: len(v) for k, v in channels.items()}
    return packed, audit
