# Optional personal-memory reranking (provisional)

The default query path is unchanged. A host may pass a `memory_reranker` to
`PersonalMemoryQueryEngine` or `DoppelClient.query_personal_memory` when a local
cross-encoder should reorder the final authorized candidate window.

```python
from doppel_memory import (
    PersonalMemoryQueryEngine,
    PersonalMemoryRerankConfig,
)

engine = PersonalMemoryQueryEngine(
    store,
    semantic_index=semantic_index,
    relation_index=relation_index,
    memory_reranker=my_reranker,
    rerank_config=PersonalMemoryRerankConfig(
        max_candidates=64,
        max_input_chars=100_000,
        timeout_seconds=30,
    ),
)
```

The stage runs only after authoritative Store reload and the scope, subject,
authority, lifecycle, temporal, score, and optional evidence-verification gates.
The provider receives only the raw question and request-local `item_N` identifiers
paired with authorized memory content. It does not receive a scope key, user ID,
subject ID, memory ID, lifecycle state, source metadata, or provenance.

The provider must return exactly one normalized `0..1` score for every offered
opaque ID. Doppel validates the complete binding and uses the scores only to reorder
the bounded prefix. The provider cannot add a candidate, remove one, bypass a gate,
change a record, or affect exact counts. Score ties preserve the engine's baseline
order. `PersonalMemoryQueryHit.score` remains the transparent baseline fusion score;
the cross-encoder score is recorded separately as `memory_reranker_score`, as a
`memory_reranker_score:` reason, and in an opt-in query trace.

Timeouts, provider exceptions, duplicate/missing/unknown IDs, invalid scores, or an
input-character limit preserve the baseline order. Provider exception text is never
returned. Inspect `result.memory_reranking` and the content-free warning to distinguish
`completed`, `unavailable`, `limit_exceeded`, and `not_run`. A reranker outage is a
quality degradation, not an incomplete or unsafe Store read, so it does not set
`result.complete=False`.

The question and memory content can still be sensitive. Remote-provider permission,
transport, retention, billing, and redaction remain host responsibilities. Prefer a
local cross-encoder for the highest-configuration self-hosted profile. The protocol
does not pick a model or enable one by default.
