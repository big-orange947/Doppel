# Opened raw-history diagnostic: BM25 and local reranking

This is the frozen [plan](public-context-bm25-rerank-plan-2026-10-07.md), not a new
blind/publication run or full Doppel/AML result. The original source/manifest,
selected three queries and full 145 sessions / 1,513 raw messages are unchanged.
Three reserved histories remain unrun. No labels, gold summaries, ontology,
entity/time/intent fields or scenario-specific aliases are passed to ranking.

## Execution

- Real PostgreSQL/pgvector and cached local FastEmbed 0.8.0,
  BGE-small-zh-v1.5, 512 dimensions (same embedding identity as the earlier run).
- Strict local BGE-reranker-v2-m3, SentenceTransformers 6.0.1,
  actual device `cuda:0`, raw logits with one sigmoid, token cap 8,192, batch 1.
- Nine ordering calls, 720 question/document pairs, **zero truncated pairs**;
  longest measured pair 3,180 tokenizer tokens. Model/config/tokenizer hashes are
  included in the ignored report; weights SHA-256:
  `d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286`.
- Zero LLM calls/tokens; no extractor, graph, natural Planner or answer reader.
- Eight real profiles / 24 query-profile combinations, all completed.
- 1,680 initial candidate Store/provenance validations and 420 final snapshot
  checks; no rejected candidate in this run. This is not, by itself, an
  adversarial multi-user privacy test; separate synthetic tests cover guards and
  revocation while ordering.
- Source/manifest hashes match the preceding pilot. The new report records actual
  source bytes including uncommitted code; its Git base is `a142551`, not a claim
  that its implementation was already clean/committed when it ran.

Artifact: `data/doppel/longmemeval-raw-context-bm25-rerank-v1.json` (ignored).
SHA-256: `e5ea0b669400f14ffe5eba1db88b0653b8936a2fa0ccebadd412a09d81c7710c`.
Raw runtime source SHA-256:
`a3bfd83708e6f761297786c97acdc3db3ccde813ad8982dcf0e649800c767000`.

## Micro-averaged annotation coverage

Denominators: five annotated raw turns and five annotated source-session
occurrences across three queries. Alternative valid unlabeled evidence is not
automatically treated as wrong. Session coverage does not imply exact-turn coverage
or correct final answers. Rankings are compared under the plan's explicit candidate
budgets, not under a claim that all sources fetch equally many items.

| Raw-only profile | Turn recall@5 | Turn recall@20 | Session recall@5 | Session recall@20 | Candidate-window turn coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Legacy substring | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 |
| Vector | 2/5 | 4/5 | 4/5 | 5/5 | 5/5 |
| Legacy substring + vector | 2/5 | 4/5 | 4/5 | 5/5 | 5/5 |
| BM25 | 4/5 | 5/5 | 5/5 | 5/5 | 5/5 |
| BM25 + vector RRF | 4/5 | 5/5 | 5/5 | 5/5 | 5/5 |
| Vector + reranker | **5/5** | 5/5 | 5/5 | 5/5 | 5/5 |
| BM25 + reranker | 4/5 | 5/5 | 5/5 | 5/5 | 5/5 |
| BM25 + vector RRF + reranker | 4/5 | 5/5 | 5/5 | 5/5 | 5/5 |

## Interpretation and limits

1. The old PostgreSQL Store substring behavior remains unchanged and yields no
   candidates for the three complete natural-language questions. BM25 is an opt-in
   generic token/term-frequency strategy, not hardcoded query intent handling.
2. All five annotated turns were already in vector's authorized candidate window.
   The missing top-20 annotation is therefore a ranking/window loss in this run,
   not proof of an absent vector candidate. Its CrossEncoder ordering recovers all
   five at top five without feeding the model annotated positions or answers.
3. More components do not automatically improve ordering. BM25's aggregate top-five
   result stays four of five after reranking; on `50635ada` BM25 initially puts both
   annotated turns in top five but reranking demotes one. That loss is retained,
   not hidden by cherry-picking the best rank per query or changing a threshold.
4. Three already opened questions are far too few for an overall "100% memory"
   claim or a justified new global default. The run compares raw-dialogue candidates
   only, not extraction, consolidation, graph paths, temporal validity of facts,
   natural planning or answers. No model/parameter tuning or question replacement
   was performed after observing these results.
5. BM25's reference complete-scope scan is bounded and rebuilds statistics per query;
   it is not a durable large-scale full-text index. Chinese character ngrams are
   not word segmentation or a measured Chinese quality guarantee. Tokenizer cap
   and input-character/timeout bounds remain explicit even though no truncation
   occurred here. GPU timing/stability is the previously deferred separate test.

Keep all profiles opt-in. Next, compose real derived-memory extraction/graph and
natural planning with this raw-context channel, then score evidence and a frozen
reader separately. Broader held-out validation is required before changing defaults.
