"""Opt-in fusion of retrieval order and complete reranker order, without new facts."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence

from doppel_memory.models import MemoryIsolationError, RecallResult
from doppel_memory.retriever import Reranker


def rank_fusion_order(permutation: Sequence[int], *, rrf_k: int = 60) -> list[int]:
    """Equal-weight RRF of input positions and a complete second permutation.

    No relevance probabilities, length/speaker/date heuristics or source payloads
    enter this calculation. Stable ties keep the original retrieval position.
    """
    if type(rrf_k) is not int or rrf_k < 1:
        raise ValueError("rrf_k must be a positive integer")
    size = len(permutation)
    if any(type(i) is not int for i in permutation) or set(permutation) != set(
        range(size)
    ):
        raise ValueError("complete unique reranker permutation required")
    ranks = {index: rank for rank, index in enumerate(permutation, start=1)}
    return sorted(
        range(size),
        key=lambda index: (
            -(1 / (rrf_k + index + 1) + 1 / (rrf_k + ranks[index])),
            index,
        ),
    )


def _key(candidate: RecallResult) -> tuple[str, str]:
    if candidate.scope is None or not candidate.memory_id:
        raise MemoryIsolationError("rank fusion requires explicit scoped candidate IDs")
    return candidate.scope.scope_key, candidate.memory_id


def _payload(candidate: RecallResult):
    # A delegate may attach its own relevance score. Fusion does not use it or
    # export it as a new similarity/probability; all other fields must match.
    return candidate.model_dump(mode="json", exclude={"similarity"})


class RankFusionReranker:
    """Bounded Reranker wrapper; never a scope authorization or evidence gate.

    The caller must already authorize the input set and reload final sources.
    Distinct scoped IDs remain distinct, even when their memory_id strings match.
    Delegates that intentionally filter candidates are incompatible: this adapter
    requires the complete ordering, not an invented bottom rank for missing items.
    """

    def __init__(
        self,
        delegate: Reranker,
        *,
        rrf_k: int = 60,
        max_candidates: int = 80,
        timeout_seconds: float = 300,
    ) -> None:
        rank_fusion_order([], rrf_k=rrf_k)
        if type(max_candidates) is not int or not 1 <= max_candidates <= 1000:
            raise ValueError("max_candidates must be an integer in1..1000")
        if (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 300
        ):
            raise ValueError("timeout_seconds must be finite in(0,300]")
        self.delegate, self.rrf_k = delegate, rrf_k
        self.max_candidates, self.timeout_seconds = max_candidates, timeout_seconds

    async def rerank(
        self, query: str, candidates: Sequence[RecallResult], *, limit: int
    ) -> Sequence[RecallResult]:
        if (
            not query.strip()
            or type(limit) is not int
            or not 1 <= limit <= self.max_candidates
        ):
            raise ValueError("nonblank query and bounded positive limit required")
        if len(candidates) > self.max_candidates:
            raise ValueError("rank fusion candidate cap exceeded")
        bound = [candidate.model_copy(deep=True) for candidate in candidates]
        keys = [_key(candidate) for candidate in bound]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate scoped candidate identity")
        if not bound:
            return []
        positions = {key: index for index, key in enumerate(keys)}
        borrowed = [candidate.model_copy(deep=True) for candidate in bound]
        ordered = list(
            await asyncio.wait_for(
                self.delegate.rerank(query, borrowed, limit=len(bound)),
                timeout=self.timeout_seconds,
            )
        )
        if len(ordered) != len(bound) or [_payload(c) for c in borrowed] != [
            _payload(c) for c in bound
        ]:
            raise ValueError("reranker filtered candidates or mutated source payloads")
        permutation = []
        for candidate in ordered:
            key = _key(candidate)
            if key not in positions:
                raise MemoryIsolationError(
                    "reranker returned an unbound scoped identity"
                )
            index = positions[key]
            if _payload(candidate) != _payload(bound[index]) or not math.isfinite(
                candidate.similarity
            ):
                raise ValueError(
                    "reranker changed source payload or returned invalid score"
                )
            permutation.append(index)
        order = rank_fusion_order(permutation, rrf_k=self.rrf_k)
        return [bound[index].model_copy(deep=True) for index in order[:limit]]
