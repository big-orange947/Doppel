# Optional retrieval/reranker rank fusion

`doppel_memory.rank_fusion.RankFusionReranker` wraps an existing `Reranker`.
It asks the delegate for the complete ordering of the bounded input set and
combines that ranking with the original retrieval ranking using equal-weight
reciprocal-rank fusion:

`score(i) = 1 / (k + retrieval_rank(i)) + 1 / (k + reranker_rank(i))`.

Ranks start at1, default `k=60`. Ties retain original retrieval order. No score
calibration, actor/length/recency preference, question category rule, role quota,
entity mapping, LLM or new evidence is added by the fusion calculation itself.
The delegate still has its own inference cost. Requesting the full order may
cost more than a delegate's early-exit top-k; this adapter does not promise free
inference or better quality. Neither rank's relevance is a truth probability.

```python
from doppel_memory.rank_fusion import RankFusionReranker

ranker = RankFusionReranker(existing_reranker, max_candidates=80, rrf_k=60)
# Supply ranker wherever the existing Reranker protocol is supported.
# The caller's authorized retrieval order becomes the first ranking.
```

This is module-only and **not enabled in any default runtime/service preset**.
The [fixed local50 comparison](../benchmarks/reports/public-memory-rank-fusion-result-2026-10-23.md)
finds a small net annotation gain but a packing regression and no new QA score.
No conclusion from this adapter changes old QA
grades or promotes a new recommended default.

## Boundaries

- Caller must authorize candidates and revalidate final sources in its Store;
  the adapter is not a permission check or a persistent source of truth.
- Every candidate needs explicit scope and memory ID. Identity is the pair,
  so identical memory-ID strings across independently authorized scopes do not
  collapse. Missing/duplicate identities fail; no cross-scope ID guessing.
- Delegate must return every input exactly once, even if final output requests
  fewer items. Filtering delegates are incompatible and fail explicitly.
- Source text, actor, authority, provenance, state, times and other source fields
  may not change. Delegate-specific similarity scores may change, but are not
  fused/exported: returned items retain their original source scores/payloads.
- Input/output snapshots are independent copies. Unknown IDs, altered source
  payloads, duplicate/partial output, invalid scores, provider errors and timeout
  fail explicitly, not as an undocumented identity-order fallback.
- Default candidate cap80, configurable up to1000, timeout at most300 seconds.
  A timeout cancels the coroutine; it is not a hard preemption guarantee for a
  delegate's background GPU/thread computation.

Fusion trades one ranking's mistakes against another's and can worsen results.
Keep candidate count, source/item/byte budgets, source payloads and QA model fixed
when evaluating it; do not tune k/weights on opened questions until a desired
score appears.
