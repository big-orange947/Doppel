# Frozen non-graph follow-up: existing source ordinals 06–10

User stopped expensive graph authoring and approved a non-graph main evaluation
path. Preserve graph code, completed graph data, old scores and scope-06's partial
checkpoint (103 complete / one started). Do not resume authoring or repair/delete
it. No product-default or frozen high-config algorithm is silently changed.

This is a **new experiment**, not ten completed high-config pairs or a degraded
high-config score. Fixed remaining first-ten ordinals 06/07/08/09/10 are selected
before observing their answers. Existing source receipt SHA-256:
`a577fc794e17b79ec9d07e1444f2522e09deac1c2937a5a370e39da50c6dcdf4`.
Dataset, original times/roles, source-only ingestion/authority/quarantine/defaults
and local embeddings remain bound to the original cohort. No re-ingestion.

## Two fixed non-graph profiles

1. `raw_vector_reranked`: original raw-only vector baseline and strict local
   reranking, 80 candidates / 20 outputs, whole ranked prefix / 24,000 UTF-8 bytes.
2. `combined_lexical_vector_reranked`: original owner-derived memory plus attributed
   raw dialogue, production scoped-scan **BM25** (default k1=1.2/b=.75, generic
   NFKC/casefold words/Han unigram+bigrams, no alias/intent lists) + pgvector via
   production RRF (k=60, equal weights, no fallback), then the same reranking and
   packing caps. Scan existing exact-scope records before authorized-channel
   selection; choose at most 80 fused candidates for reranking. BM25 is a bounded
   reference scan, not a scalable persistent full-text index.

Local embedding remains BGE-small-zh-v1.5 / fastembed0.8.0 / 512 dimensions;
reranker BGE-reranker-v2-m3 on CUDA, max length8192, batch1, bound model artifacts.
No Graphiti/Neo4j connection, relation schema, LLM planner, exact-count certificate
or temporal-plan interpretation. Keep original timestamps/effective bounds for
Reader reasoning. This does not claim non-graph feature parity with the temporal
or relation engine. Existing helpers import optional graph packages but do not
connect to the graph; packaging decoupling is not part of this experiment.

Unchanged Reader v2 + reference-only task judge + citation judge, same original
DeepSeek flash/json_object/temp0/thinking-disabled configs and output caps.
**Three calls/profile/question, ten rows, thirty calls total maximum.** Alternate
profile order (even ordinal raw first, odd combined first). Failures stop and are
preserved, no retries, silent resume, tuning, answer-aware packing or resampling.
The reused answer helper does not expose its internal profile label or gold to
the Reader; this is tested. New profile names/caches/plans cannot overwrite old
live receipts. Exact cache-only replay compares semantic rows/ledger inventories,
with no retrieval rerun or original-receipt replacement.

## Frozen bindings before paid calls

- Preflight SHA-256:
  `833b2e3c2e40b5431cfc04c157aa0ba6a27af888483712dfd841ba7aa88afe95`.
- All ten plans canonical SHA-256:
  `af20236c129846817be8e9577ab268970c7268d20d01bc4911293859ed3ba6df`.
- New adapter SHA-256:
  `407bdb82ffbb779ad6031d638b6f67450027a89fbf50726d054663dd9a6b1cf0`.
- Run directory: `data/doppel/public-memory-nograph-06-10-v1/`.
- Preflight validates all five source certificates, read-only Store and complete
  current vector metadata. New code adds no scenario-specific behavior, public
  API/core/default/provider/prompt changes or stored memory writes.
- Targeted non-graph/baseline/lexical tests: 33 pass; Ruff repository check passes.

Report source preparation costs separately: existing source extraction/embedding
was already paid, so marginal follow-up cost is **not** full fresh-corpus cost.
Preserve missing-usage/failure accounting of the old graph experiment. Scores from
the two protocols must not be pooled into an apparent full-high-config success
rate. No official LongMemEval, independent blind, AML or publication acceptance.
