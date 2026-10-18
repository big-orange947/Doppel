# Prospective raw selection comparison: fixed ordinals41-45

Date:2026-10-18. This freezes a five-question continuation before retrieval or
answer inspection. Public benchmark data may be model training data: no claim
of model-unseen independence, official LongMemEval/AML score or release readiness.

## Selection and exclusions

Select exactly diagnostic ordinals41-45 from the existing frozen50-case manifest
`data/doppel/longmemeval-fresh-high-config-50-manifest-v1.json`. Validate its hash,
unchanged LongMemEval-S source bytes, history payload/counts, and disjointness from
first40, reserved and excluded history groups. Do not replace cases based on
question content, expected answers, evidence labels, costs or results. Leave
ordinals46-50 and all reserved histories unopened.

| Ordinal | Case | Raw messages | Ingestion chunks | Public sampling stratum |
| --- | --- | ---: | ---: | --- |
|41|d6233ab6|437|44|single-session-preference|
|42|a96c20ee_abs|535|53|public-no-answer-id|
|43|f4f1d8a4|585|55|single-session-user|
|44|gpt4_7abb270c|467|48|temporal-reasoning|
|45|6a27ffc2|493|51|knowledge-update|

Total2,517 source messages/251 chunks. Sampling is not balanced across all
LongMemEval categories; these five cases do not support reliable category rates.

## Unchanged two-profile comparison

Both profiles start with the **identical frozen production BM25+local-vector
top80 pool**, source revalidation,20 selected sources, lossless1200-character/
160-overlap splitter, round-robin bounded80 fragment candidates,20 output cap,
and skip-to-fit24,000-byte packing. Original actor/authority/time/hash/offsets
survive. Candidate text may include historical assistant suggestions: do not
promote them into owner facts or impose a speaker quota.

- `bge_content_only`: existing local `bge-reranker-v2-m3`, unchanged8192-token cap,
  CUDA/batch1, content-only source and passage ranking.
- `llm_metadata_up_to20`: unchanged `BoundedTopKSelector`, source and passage
  selection0..20 unique authorized IDs, original source plus attribution/time.
  Unselected candidates are unranked, not scored false. No padding/repair/retry.

This is a comparison of deployable **profiles**, not an isolated model-only
ablation: metadata visibility and allowed selection cardinality also differ.
No metadata/BGE/MMR extra arms, prompt tuning, new Planner, graph authoring or
full-history LLM extraction. Reader v2, provisional task judge and their model
configurations remain unchanged. Query reference time still goes to the Reader;
source observation time is not an effective date or causal-arrival cutoff.

## Two separately frozen phases

Entry point:`python -m benchmarks.public_memory_prospective_selection`.

1. `--phase prepare`: zero LLM calls. Create only a previously absent dedicated
   schema `raw_select_952e5f3593e0`; namespace
   `longmemeval-prospective-selection-41-45-v1`. Preserve all old schemas, graph,
   caches/journals and the user's `uv.lock`. Ingest original messages with roles
   and source timestamps, index with existing local bge-small-zh512, freeze each
   actual pool and source inventory, actual bounded-selector source request,
   and unchanged local BGE baseline contexts. Save a per-history checkpoint.
   Refuse an existing schema or second attempt; no implicit reset/retry.
2. `--phase evaluate`: server-enforced read-only Store; exact prepared report,
   implementation hashes, original source/pool hashes and source request hashes
   must match. New LLM profile and both QA arms only; no rerunning BGE/import.
   Actual preparation is bound into a new preflight committed before paid calls.

Preparation preflight:
`data/doppel/prospective-selection-41-45-prepare-preflight-v1.json`, fingerprint
`ffe15441c54a2743f49e75747c42bf6666e391858252bb1e9c103958f9869e48`.
Runtime source files, exact local model artifacts/identity, all phase settings and
the later paid-stage caps are already bound before preparation outcomes exist.
Run directory:`data/doppel/prospective-selection-41-45-v1`.

## Calls, cost controls and failures

At most **30 new paid calls**:10 selector,10 Reader,10 provisional task judge.
No old QA result exists for these questions; both arms are actually generated.
DeepSeek flash JSON-object/temperature0/thinking disabled; completion caps
selector1024/Reader2048/judge1024. Selector input:80 candidates/300,000 content
characters,500,000 canonical request bytes per call/5,000,000 cumulative bytes.
Reader/judge100,000 bytes per call/1,000,000 cumulative each. These byte/output
caps do not guarantee a monetary ceiling; report observed or missing usage.

Use existing local model files; no model downloads. Durable SQLite stage ledgers,
content-addressed output caches, pre-await request receipts and per-row context/
answer checkpoints. No automatic retries or provider-output repair. Stop on first
runtime/validation failure, retain partially prepared data, paid attempts and
caches; do not replace failed cases or silently increase a bound. The API key
stays environment-only and is not needed/read by the zero-LLM preparation path.

## Metrics and decision

- Report candidate/top20 **whole-turn annotation coverage** separately, excluding
  predeclared unanswerable rows from positive answer-support denominators.
- For packed fragments, source-turn presence is **not** semantic answer support.
  Report source presence and conservative *full original turn text retained*
  separately; leave fragment answer-support recall undefined without span labels.
- Primary paired QA uses unchanged provisional task grades. Report actual answers,
  legal citations (not equivalent to support), missing/extra evidence, semantic
  abstention inconsistencies and Reader/ground-truth ambiguities without rescoring.
- Report all5 cases including errors/negative cases, source-to-fragment/packing
  losses, source/Store integrity, local truncation counts, calls/tokens. No stable
  latency or security benchmark claims from this normal-run small sample.

No after-result rule/prompt/judge changes, default promotion, forced temporal
inferences or entity merging to fit gold. A promising result warrants a larger
separately frozen sample, not a500-question/publication claim. A negative result
remains negative; distinguish evidence selection from Reader behavior without
another opened-example tuning loop.
