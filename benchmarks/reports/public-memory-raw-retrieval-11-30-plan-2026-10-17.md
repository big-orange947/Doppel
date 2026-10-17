# Frozen twenty-question raw retrieval expansion, zero LLM budget

Continue the original prospective selection at diagnostic ordinals11–30. No
resampling, prior-ten reuse, reserved-history access or outcome-conditioned rules.
Parent manifest remains unchanged; validate every selected history group, turn
count, chunk count and source payload hash before queries. Full S histories,
not evidence-only oracle inputs. Same original source SHA-256 as prior runs.

-20 histories /9,883 original messages, all original roles/time/source positions.
- Public strata: assistant3, multi-session3, preference3, no-answer3, user3,
  temporal3, knowledge-update2. Exact history grouping is not independence from
  shared filler sessions, model pretraining or public benchmark exposure.
- New namespace `longmemeval-nograph-retrieval-11-30-v1` and dedicated PostgreSQL
  schema `raw_evidence_df11c519b425`; no existing Store/journal/cache reset/deletion.
- Plan fingerprint:
  `3a05d32254ba6dcc339e7e0127b09acdd1d884c51d5c5b9aa7dbc520c932d405`.
- Preflight SHA-256:
  `e5b897414b3455464c6229cecd5abb7eb10f25b5be1922a43b1de5c9fd012dab`.
- Adapter SHA-256:
  `26bf9a9e8fb10c73389ad47649207a835176be1ff34eab89fac00fe03a925440`.

Reuse unchanged `public_context_baseline.run_baseline`, RawHistoryHost and
AttributedContextRetriever; no new core algorithms/prompts/model providers. Eight
fixed profiles: legacy Store substring, vector, legacy hybrid, BM25, BM25/vector,
plus vector/BM25/BM25-vector with strict local reranking. Primary comparison is
vector-reranked vs BM25-vector-reranked on **raw-only** sources; auxiliary profiles
explain candidate/ordering differences rather than promote a selected winner.

Same local fastembed BGE-small-zh-v1.5/512 and CUDA BGE-reranker-v2-m3,
max length8192/batch1, model artifact SHA-256
`d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286`.
BM25 remains bounded scoped-scan reference strategy with default generic tokens;
production RRF60/equal weights/no fallback. Final window80/output20; legacy
Store hybrid retains its declared320-per-source auxiliary window. No gold or
labels enter ingestion/ranking. Authoritative scope/role/provenance revalidation
and final post-reranking Store checks are mandatory.

**Zero paid LLM calls/tokens.** No extraction, graph/Neo4j, Planner, Reader or
judge. Remove conventional provider-key environment variables from the child.
Local embedding/reranking still consumes hardware/time; no idle-GPU latency claim.
Four five-history block receipts are saved independently; stop on failure, retain
dedicated raw/index data, no automatic reset/retry or overwrite of previous output.

Report labelled evidence recall at5/20 and candidate80 separately. No labelled
evidence denominator means undefined recall, not success/abstention. Do not call
these QA accuracy, exact-count/time-planning certification, full Doppel memory
intelligence, complete50/500 results, blind-independent, official AML or release
acceptance. Eight auxiliary profiles are not eight independent question sets.
Targeted wrapper/raw-host/context-guard tests14 pass; Ruff repository passes.
