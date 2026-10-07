# Opened diagnostic: generic BM25 and local context reranking

Freeze this configuration before inspecting this comparison's results. This is
the already opened three-history diagnostic, **not a new blind/publication set**.
Do not replace questions, change labels, add question-specific aliases or adjust
parameters in response to these three scores. Preserve all earlier failed baselines.

- Same official LongMemEval cleaned-S SHA-256 and manifest as
  [the public pilot](../../docs/public-memory-pilot.md).
- Same diagnostic IDs `50635ada`, `0100672e`, `cc539528`: full supplied histories,
  145 sessions / 1,513 messages. Reserved histories remain unexecuted.
- Raw-only PostgreSQL/pgvector and cached BGE-small-zh-v1.5, 512 dimensions.
- Keep legacy substring/vector/RRF profiles. Add module-only opt-in BM25 and
  BM25/vector RRF, plus strict local reranking of BM25, vector and BM25/vector.
- BM25: `k1=1.2`, `b=0.75`; NFKC/casefold word tokens, Han unigrams/bigrams;
  positive IDF, unique query terms, content only, no aliases/stopword/intent lists.
  Complete per-scope scan, bounded at 50,000 records / 1,000 pages. Fail rather than
  rank a partial corpus. This reference strategy is not a persistent search index.
- Final candidate window 80, result window 20. New BM25/vector RRF fetches at most
  80 per source before fusion; legacy RRF retains its declared 320-per-source
  behavior. The sources need not produce equally many matching candidates.
- Local BGE-reranker-v2-m3, CrossEncoder, raw-logit sigmoid exactly once, CUDA,
  token cap 8,192, batch size 1; no domain/relation/role metadata injected into
  scoring. Record actual token truncation and model file hashes. Zero LLM calls.
- Production score validation: at most 80 items / 1,000,000 chars / 300 seconds
  per ordering call. Invalid/missing/duplicate scores or limits fail the reranked
  profile instead of labeling unchanged base order a successful rerank.
- Return original role/authority/source after Store/provenance checks. Recheck
  authoritative snapshots after ordering to catch intervening revocation/change.
- Report annotated turn/session recall at 5/20 and candidate-window coverage
  separately, with explicit denominators. Corpus and scoring annotations are
  isolated from ranking. No QA, graph, natural Planner or full Doppel/AML claim.
- Search timing is observational only, not the deferred highest-config GPU
  warm-latency benchmark. Do not infer generalization from only three questions.
