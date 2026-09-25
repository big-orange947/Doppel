# Combined retrieval V2 — first semantic reranking live result

This result was opened after commit `805d09f` froze the runner, profiles, and success
gate in `combined-semantic-rerank-preregistered-2026-09-25.md`. The frozen dataset,
labels, thresholds, candidate window, Store filters, and final context bound were not
changed after opening the result.

## Runtime and binding

- dataset fingerprint:
  `f35257ad354f5132c49f152b0b705fbba2cc7ce04dec4635237c91c505a84f6b`;
- 36 `semantic_nonrelation` queries over the original 36 owner scopes and 3,600
  memories;
- PostgreSQL authoritative Store plus pgvector;
- candidate embedding: FastEmbed `BAAI/bge-small-zh-v1.5`, 512 dimensions;
- local whole-memory reranker: `BAAI/bge-reranker-v2-m3`, SentenceTransformers 6.0.1,
  CUDA, sigmoid over raw logits, 64-candidate bound;
- zero LLM calls, external HTTP calls, or provider tokens;
- report SHA-256:
  `86009cb0246bf614cb6f355de7dde823798a56deb25e7a1fa7a54c072744c4e2`;
- dedicated PostgreSQL benchmark schema cleaned successfully.

## Result

| Profile | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR | p50 | p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| current baseline | 0.417 | 0.417 | 0.417 | 0.750 | 0.445 | 65.6 ms | 85.4 ms |
| expanded baseline | 0.417 | 0.417 | 0.417 | 0.750 | 0.445 | 65.6 ms | 85.4 ms |
| memory reranked | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | 257.2 ms | 316.0 ms |

The required memory was present in the unchanged first 64 raw candidates for all 36
queries. Before reranking, 15 were already in the top five, 12 were ranks 6–20, and
nine were ranks 21–64. None was an index or score-gate miss. Merely overfetching and
backfilling changed no quality metric; the gain came from candidate ordering.

All preregistered checks passed:

- 36/36 reranker operations completed;
- first-64 candidate membership changed in zero queries;
- zero cross-scope records;
- zero authority/lifecycle-ineligible exposed records;
- no final context exceeded 20 memories;
- baseline metrics reproduced exactly;
- backend cleanup completed.

## Interpretation and limit

For this corpus, replacing BGE-small is not required to repair the observed semantic
failure: its candidate recall is already complete at 64, while a local cross-encoder
correctly separates the owner's stable preference from repeated plans and third-party
mentions. The quality cost is latency: median query time rose by about 192 ms and p95
by about 231 ms. That supports an opt-in highest-quality profile, not an unconditional
lightweight default.

The perfect score is not a general memory-quality claim. These 36 cases contain 12
semantic phrasings repeated across three wording cycles, and the required memories
share one synthetic preference form. The result establishes component diagnosis and
safe runtime behavior. The next required test is the complete 144-query combined
suite, where whole-memory reranking must preserve one-hop, atomic two-hop, and temporal
path evidence while improving the semantic slice.
