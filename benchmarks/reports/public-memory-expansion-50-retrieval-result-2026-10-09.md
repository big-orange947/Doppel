# Fifty-history retrieval diagnostic: six profiles complete

The frozen comparison completed all 300 rows (50 questions * six profiles) under
commit `f644d3a`. It used the existing BGE-small-zh-v1.5 vectors and local CUDA
BGE-reranker-v2-m3. The ten reserved histories remain unexecuted.

Result: `data/doppel/longmemeval-expansion-50-memory-comparison-v2.json`, SHA-256
`af98f44a9f73a71bb43acffb9a28e46e6ac319507c5283001b97cbdacc36eff7`.
The [frozen plan](public-memory-expansion-50-retrieval-plan-2026-10-09.md) binds
the source, manifest, ingestion report, corpus and candidate/context budgets.

## Evidence coverage

Percentages below are macro averages over the **49 questions with annotated
evidence**, covering 77 distinct annotated turns in total. The one no-answer
question has no evidence denominator and is not counted as automatic recall
success. These are source-provenance measures, not semantic answer accuracy.

| Profile | Candidate turn recall | Rank-5 turn recall | Packed turn recall | Packed session recall | All sessions covered |
| --- | ---: | ---: | ---: | ---: | ---: |
| raw_vector | 95.24% | 53.06% | 80.61% | 94.90% | 45/49 |
| raw_vector_reranked | 95.24% | 77.21% | 92.18% | 99.32% | 48/49 |
| memory_vector | 79.93% | 60.54% | 70.41% | 84.01% | 40/49 |
| memory_vector_reranked | 79.93% | 74.49% | 79.25% | 85.71% | 42/49 |
| combined_vector | 95.24% | 70.07% | 85.37% | 98.98% | 48/49 |
| combined_vector_reranked | 95.24% | 82.31% | 93.20% | 99.32% | 48/49 |

Micro packed-turn recall is 62/77 raw, 70/77 raw reranked, 58/77 memory,
65/77 memory reranked, 66/77 combined, and 71/77 combined reranked. Thus the best
packed result still misses six annotated turns. All annotated sessions are present
in the raw and combined 80-candidate pools, but a session hit alone does not prove
that every required turn or the actual answer is present.

Reranking improves packed macro turn coverage by 11.57 percentage points for raw,
8.84 for memory and 7.82 for combined. Combined reranked is only 1.02 points above
raw reranked; this small diagnostic difference does not establish a statistically
reliable advantage. Owner-memory alone has weaker coverage and excludes assistant
utterances by definition. Citation coverage for a derived summary does not show
whether that summary preserved every detail needed to answer the question.

## Validation and boundaries

- Corpus: 24,891 raw context records, 9,739 confirmed owner-memory context records,
  125 audited governance records. Five legitimate agent derivatives were source-
  validated and explicitly excluded from the owner-memory channel; two derived
  records are inactive. No source records were changed or removed.
- Store snapshots before/after match:
  `11aab45f1bdfaebeea23bee822e53e5cdd94aef24f68bb020d90e9eda35e9cc3`.
- Existing vector fingerprint/version and source identity gates all passed.
  Packed records and raw citation sources passed 8,269 revalidation checks.
- Reranker: 12,000 pairs, zero truncated pairs, longest pair 1,469 tokens,
  actual device `cuda:0`. This is not a deployment latency benchmark.
- Paid LLM calls/tokens: zero. Record/index writes: zero. The first failed artifact
  remains preserved; only the harness's legitimate-agent boundary was corrected.
- Scoped public development sample with shared sessions; full production Planner,
  Graphiti, Reader, Judge, AML-model profile and complete LongMemEval are not
  measured by this result. No case-specific retrieval rule was added.

The next stage keeps the three previously established reranked QA profiles and
uses the unchanged Reader v2 / primary-Judge prompts on these packed contexts.
Answer correctness, citation legality/support and unscored rows will be reported
separately, with five fixed ten-question batches.
