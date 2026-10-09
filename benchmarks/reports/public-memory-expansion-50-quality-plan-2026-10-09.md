# Fifty-question Reader/primary-Judge plan

This plan is committed before any new answer or judgment is requested. Reuse
Reader v2 and the primary Judge from the earlier ten-question expansion unchanged.
The new entrypoint only binds/scales that protocol to the completed fifty-question
retrieval artifact. No prompt tuning or synthetic calibration loop is part of it.

## Frozen inputs and requests

- Retrieval result SHA-256:
  `af98f44a9f73a71bb43acffb9a28e46e6ac319507c5283001b97cbdacc36eff7`.
- Manifest SHA-256:
  `28dc31edbcfc119d5f952d9f0ab3ceeaa123a5e9a5bfef70f82f9febbc120721`.
- Dataset SHA-256:
  `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
- Zero-call preflight:
  `data/doppel/longmemeval-expansion-50-quality-preflight-v1.json`, SHA-256
  `b472dd35ad6588229fc175f49a5abe74284a15cf8332f13b1657e2d258a809a3`.
- Frozen plan fingerprint:
  `6f5a84460813cafb12336a1423de44c7081f77343832b2fa9ea0abba9a82aed1`.
- All fifty manifest-ordered questions, partitioned in advance into five
  ten-question batches. Each question runs raw_vector_reranked,
  memory_vector_reranked and combined_vector_reranked: 150 logical rows.
  These profiles match the earlier ten-question QA protocol; selection is fixed.
  The remaining three vector-only profiles are retrieval observations only.
- Bind all 300 parent retrieval row identities and packed context bytes/counts
  before selecting the fixed QA rows. Source hashes bind the implementation,
  instructions, schemas, model settings, exact Reader requests and scoring
  references. There are 145 distinct Reader requests across the 150 rows.

## Generation, accounting and scoring

Use DeepSeek `deepseek-v4-flash`, `https://api.deepseek.com`, JSON object mode,
temperature 0, thinking disabled and 120-second timeout. Reader max_tokens 2048;
Judge max_tokens 3072. No setting changes after observing failures or answers.

Each batch reuses the established durable thirty-row executor with separate
30-Reader / 30-Judge attempt caps. Overall caps are 150 + 150 = **300 new attempts**.
Identical requests share cached outputs within a batch. No retry, case replacement
or new extraction. Failures and invalid structured outputs stay reported; judge
execution requires a valid Reader output. Attempt caps are not exact billing caps.

The Reader sees only question, reference time and its unchanged packed context;
the reference answer, annotations, profile names and old scores are withheld.
The Judge sees the candidate and reference answers plus the same supplied context
for citation support/absence assessment. This is same-model provisional scoring,
with source-quote anchoring and deterministic citation/derivation legality checks.
Quote presence does not validate entailment or the correctness label. Preserve
contradictory Judge fields and explicitly report rows excluded for missing anchors.

Report each profile's fifty-question denominator, scored/unscored rows, provisional
correctness, citation legality, support, contradictions, refusals, six question-type
groups and the single no-answer observation. Do not promote the sample to full
LongMemEval, independent blind, AML or a reliable refusal-rate result. The ten
reserved histories stay unexecuted. Keys come only from the named environment
variable. No Store, retrieval/index, graph, source expansion or context changes.

## Execution and replay

Live requires the exact preflight before reading a key:

```powershell
& D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_quality_50 `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --comparison data/doppel/longmemeval-expansion-50-memory-comparison-v2.json `
  --run-dir data/doppel/public-memory-expansion-50-quality-v1 `
  --output data/doppel/longmemeval-expansion-50-quality-v1.json `
  --frozen-preflight data/doppel/longmemeval-expansion-50-quality-preflight-v1.json `
  --api-key-env DEEPSEEK_API_KEY --live
```

Run a subsequent key-free `--live --cache-only` replay with a fresh output path,
comparing answer/judgment/check contents and profile summaries. Existing live
artifacts and all older journals, caches, database records and `uv.lock` are
preserved. A completed live run cannot spend again in the same answer ledgers.
