# Complete the same uniform50 baseline, no algorithm tuning

Fixed complement of the completed11–40 run: ordinals01–10 and41–50, in parent
order. All are opened development questions; no fresh/independent, highest-config,
official LongMemEval or AML claim. Keep the ten reserved histories untouched.
Do not change Reader, judge, embedding/reranker, source limits, packing or labels.

## Protocol and source projection

Same affordable raw-only contract: local bge-small-zh-v1.5/512, production
BM25/vector equal-weight RRF60/no fallback, candidate80, BGE-reranker-v2-m3
sentence-transformers6.0.1/max8192/batch1/CUDA, top20 original messages, ranked-fit
24000 UTF-8 JSON bytes/max20. Same Reader v2 and DeepSeek task judge as uniform30.
No graph, new extraction, ingestion/reindex, LLM selection or model downloads.

Reuse41–45 original frozen80 pools and46–50 neighborhood pools' first80 preserved
original anchors, NOT a prefix of the separately recomputed wider nativeN pools.
Revalidate every candidate against original raw source/Store. Run local BGE on
all20 pools; at most1600 pairs. For01–10 only, retrieve original80 from existing
PostgreSQL vectors and production BM25 (at most10 local query embeddings).

The first schema contains both ingestor events and derived EVENT memories.
An evaluation-only RawOnlyStore subclass adds a bound extractor=ingestor SQL
predicate via the existing filter builder, before BM25 corpus statistics and
vector LIMIT. That makes the logical eligible corpus match the other raw-only
schemas; filtering derived results *after* candidate80 would be a different,
starved baseline. No DB/view creation, persisted tags, roles or query exceptions.
Authoritative full-corpus hashes are checked via a separate unchanged read-only
Store; runtime source mapping validates all raw events, not derived summaries.
This channel projection is evaluation composition, not a core API/default change.

Preparation uses only local models/read-only DB. Verify exact BGE identity against
the frozen30 retrieval report and complete raw source mappings/full corpus hashes.
Save actual80 pools/top20 positions, whole packed contexts, source checks and
exact Reader request hashes before paid calls. Paid phase reloads and validates
original context and corpus before/after, without reranking or source mutation.

## Paid budget, reporting and aggregation

Reader≤20/max2048 output tokens; task judge≤20/max1024; at most40 new paid calls,
per-request canonical bytes≤100000 and per-stage cumulative≤2000000. Same
deepseek-v4-flash/json_object/temperature0/thinking disabled; no automatic retry,
repair or budget extension. Durable ledger/caches/per-row receipts; stop first
failure and preserve it. Environment-only key; never persist it. These are
attempt/byte bounds, not a currency or aggregate token guarantee.

Report20 result, then merge exact fixed ordinals with original30 once each.
Require compatible profile/limits/packing/QA configs, unchanged shared code and
exact disjoint50 ordinal/case IDs. Do not reuse best historical grades or replace
new failures. Report positive tasks/negative variants/types separately, candidate/
returned/packed annotation coverage and actual combined QA cost (excluding sunk
ingestion/local model costs). Preserve old30 answers unchanged. Frame the result
as uniform *logical* baseline over existing scoped stores, not identical physical
schemas, a latency benchmark, or proof that public data is model-unseen.

Runner: `python -m benchmarks.public_memory_uniform_completion`; prepare/answers
require exact frozen preflight for execution; aggregate is zero-paid and binds
the completed20 report, its contexts and immutable30 parents. Artifacts ignored.

Preparation preflight v2 fingerprint:
`daf28e1470510935dd03e4fccc0f8514cce9925161e65c8fdc8cdb9f913579d5`.
Local file:`data/doppel/uniform-qa-completion-prepare-preflight-v2.json`.
V1 was an unexecuted zero-call development preflight before aggregate guards
were finalized; preserve it, do not treat it as a failed provider attempt.
Eleven offline tests pass (mixed-source attribution/fake QA/gold separation,
raw SQL predicate, fixed complement, same-profile aggregation); new runner
Pyright zero errors; Ruff repository/format checks pass. CUDA availability and
sentence-transformers6.0.1 were read-only checked before this freeze.

## Actual-context supplement, still zero paid calls

All20 source histories pass full-corpus/runtime mapping validation and every
candidate window contains80 authorized raw originals. Local reranker processes
1600 pairs, zero truncated, longest4107 tokens (below8192). Packed context bytes
468949 total; Reader request bytes568032 total,max28969. No DB/source/index writes.

Preparation:`data/doppel/uniform-qa-completion-prepare-live-v1.json`, SHA256
`bc85ac1307dc83c738ddf00246319354b07eac8ba746c51bbbce1275c1b3f499`.
Answer preflight:`data/doppel/uniform-qa-completion-answers-preflight-v1.json`,
plan fingerprint
`a4644f165d1241e97b58f804a14b30c4aad74655564b9d28cf48057ae4a3a224`.
All20 exact Reader requests/full preparation are bound before first provider call.
