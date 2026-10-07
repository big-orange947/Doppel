"""Bounded backend-neutral BM25 reference strategy, opt-in beside Store search.

This implementation reads a complete filtered corpus in each exact scope on
every query. It is not a persistent full-text index and is not suitable for
unbounded production histories. No aliases, domain keywords or gold labels are
used. Consumers still reload candidates from their authoritative Store.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from doppel_memory.in_memory_store import _matches
from doppel_memory.models import (
    MemoryFilter,
    MemoryIsolationError,
    MemoryRecord,
    MemoryScope,
    RecallResult,
)
from doppel_memory.store import MemoryStore

_TOKENS = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+|[^\W_\u3400-\u4dbf\u4e00-\u9fff]+")


def lexical_tokens(text: str) -> list[str]:
    """NFKC/casefold word tokens; Han unigrams+bigrams, not word segmentation.

    No stop-word/alias list, stemming, translation or intent interpretation.
    Punctuation separates tokens; repeated query tokens are scored once.
    """
    result = []
    for token in _TOKENS.findall(unicodedata.normalize("NFKC", text).casefold()):
        if "\u3400" <= token[0] <= "\u9fff":
            result.extend(f"h:{character}" for character in token)
            result.extend(f"h:{token[i : i + 2]}" for i in range(len(token) - 1))
        else:
            result.append(f"w:{token}")
    return result


class BM25ReadLimitError(RuntimeError):
    """A complete scoped corpus could not be read; no partial ranking returned."""


class BM25Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    k1: float = Field(default=1.2, gt=0, le=10, allow_inf_nan=False)
    b: float = Field(default=0.75, ge=0, le=1, allow_inf_nan=False)
    page_size: int = Field(default=200, ge=1, le=2000, strict=True)
    max_records_per_scope: int = Field(default=50_000, ge=1, strict=True)
    max_pages_per_scope: int = Field(default=1000, ge=1, strict=True)


class BM25RetrievalStrategy:
    """Positive-IDF BM25 over content only, with per-scope corpus statistics.

    IDF = log(1 + (N - df + .5)/(df + .5)). Query terms are a set. Scores
    are mapped monotonically by s/(1+s) to RecallResult.similarity, not a
    calibrated relevance probability. No-match documents are never returned.
    Changing another scope cannot alter scores in an existing scope.
    """

    name = "doppel.scoped-scan-bm25"
    version = "1:nfkc-casefold-words-han-unigram-bigram"

    def __init__(self, config: BM25Config | None = None) -> None:
        self.config = config or BM25Config()

    async def search(
        self,
        store: MemoryStore,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> Sequence[RecallResult]:
        if not scopes:
            raise MemoryIsolationError("BM25 search requires explicit exact scopes")
        if type(limit) is not int:
            raise ValueError("BM25 limit must be an integer")
        if limit <= 0:
            return []
        terms = set(lexical_tokens(query))
        if not terms:
            return []
        store.capabilities.require("pagination")
        bound_filters = (filters or MemoryFilter()).model_copy(deep=True)
        bound_scopes = {s.scope_key: s.model_copy(deep=True) for s in scopes}
        ranked: list[tuple[float, MemoryRecord]] = []
        for key, scope in sorted(bound_scopes.items()):
            records: list[MemoryRecord] = []
            seen_ids, seen_cursors = set(), {""}
            cursor = ""
            scanned = 0
            for _ in range(self.config.max_pages_per_scope):
                page = await store.scan(
                    scope.model_copy(deep=True),
                    filters=bound_filters.model_copy(deep=True),
                    cursor=cursor,
                    limit=self.config.page_size,
                )
                scanned += len(page.records)
                if scanned > self.config.max_records_per_scope:
                    raise BM25ReadLimitError("BM25 scoped record bound exceeded")
                for record in page.records:
                    if record.scope.scope_key != key:
                        raise MemoryIsolationError("BM25 scan escaped requested scope")
                    if not record.memory_id or record.memory_id in seen_ids:
                        raise BM25ReadLimitError(
                            "BM25 scan returned missing/duplicate identity"
                        )
                    seen_ids.add(record.memory_id)
                    # Enforce the filter again; a custom Store is not trusted to apply it.
                    if _matches(record, bound_filters):
                        records.append(record.model_copy(deep=True))
                if not page.has_more:
                    break
                if not page.next_cursor or page.next_cursor in seen_cursors:
                    raise BM25ReadLimitError("BM25 scan cursor made no progress")
                seen_cursors.add(page.next_cursor)
                cursor = page.next_cursor
            else:
                raise BM25ReadLimitError("BM25 scoped page bound exceeded")
            frequencies = [
                Counter(lexical_tokens(record.content)) for record in records
            ]
            lengths = [sum(freq.values()) for freq in frequencies]
            average_length = sum(lengths) / len(records) if records else 0
            if not average_length:
                continue
            document_frequency = Counter(term for freq in frequencies for term in freq)
            for record, freq, length in zip(records, frequencies, lengths, strict=True):
                score = 0.0
                for term in sorted(terms):
                    count = freq[term]
                    if not count:
                        continue
                    df = document_frequency[term]
                    idf = math.log1p((len(records) - df + 0.5) / (df + 0.5))
                    denominator = count + self.config.k1 * (
                        1 - self.config.b + self.config.b * length / average_length
                    )
                    score += idf * count * (self.config.k1 + 1) / denominator
                if score > 0:
                    ranked.append((score, record))
        ranked.sort(
            key=lambda item: (-item[0], item[1].scope.scope_key, item[1].memory_id)
        )
        return [
            RecallResult(
                fact=record.content,
                memory_id=record.memory_id,
                scope=record.scope,
                kind=record.kind,
                actor=record.actor,
                authority=record.authority,
                state=record.state,
                source_event_id=record.source_event_id,
                source_message_id=record.source_message_id,
                extractor=record.extractor,
                raw_text=record.content,
                valid_at=record.created_at,
                extracted_at=record.updated_at,
                similarity=score / (1 + score),
            )
            for score, record in ranked[:limit]
        ]
