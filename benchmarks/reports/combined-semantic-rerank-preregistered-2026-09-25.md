# Combined retrieval V2 — semantic overfetch and reranking preregistration

This protocol was frozen after the first bounded-exploration live result exposed the
semantic-only weakness and before opening any result from the local whole-memory
reranker on this corpus. The frozen V2 dataset, labels, Store filters, embedding
baseline, and 20-item final context bound remain unchanged.

## Prior observation

The exploration-enhanced hybrid reached 0.854 evidence recall@5 overall but only
0.417 on the 36 `semantic_nonrelation` queries. Inspection of the already-opened
baseline ranks showed 15 required memories in the top five, 12 at ranks 11–12, and
nine absent from the final top 20. Dense, repeated same-scope distractors occupy those
positions. This observation selects the component under test; it does not change any
query, label, threshold, or fixture.

## Frozen profiles

1. **current baseline** — the existing BGE-small lexical/vector order truncated to 20
   before authoritative Store-backed assembly;
2. **expanded baseline** — the same order overfetched to 100, Store-revalidated, then
   truncated to 20, isolating overfetch/backfill from model reranking;
3. **memory reranked** — the same retrieved candidate order with only the first 64
   authorized candidates offered to the already-implemented reorder-only personal
   memory reranker, then Store-revalidated and bounded to 20.

The model is the already downloaded local `BAAI/bge-reranker-v2-m3` evaluated through
SentenceTransformers with one explicit sigmoid over raw logits. No LLM, external HTTP,
or paid provider is involved. Reranking receives only the raw question, opaque
request-local item IDs, and candidate content. It receives no scope key, memory ID,
authority, lifecycle state, or expected answer.

## Frozen success gate

- reproduce the opened current-baseline recall@5 `0.416667`, recall@10 `0.416667`,
  and recall@20 `0.750000`;
- required-evidence candidate recall within the unchanged first 64 raw candidates is
  at least `0.90`;
- memory-reranked recall@5 is at least `0.75`;
- memory-reranked recall@10 is at least `0.85`;
- memory-reranked MRR does not regress from the current baseline;
- reranking changes order only: the first-64 membership must be identical before and
  after reranking for every query;
- all 36 reranker operations complete rather than silently degrading;
- zero exposed cross-scope or authority/lifecycle-ineligible records;
- no final query exposes more than 20 candidates;
- the dedicated PostgreSQL benchmark schema is cleaned after the run.

Latency is reported at p50/p95/p99 but is not gated in this first quality experiment.
The result cannot justify changing Doppel's default model: it answers the narrower
question of whether the current semantic weakness is primarily candidate recall or
ranking under dense same-scope distractors.
