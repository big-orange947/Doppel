# New fifty-history expansion: frozen selection and first bounded ingestion block

This freezes selection and the extraction/storage stage before new provider calls.
It is not a completed fifty-question evaluation or an implemented scoring plan.
Do not continue tuning the thirteen opened questions. Preserve old failures,
scores, cache inventories, databases and `uv.lock`.

## Fixed source and selection

Same public LongMemEval-S snapshot SHA-256:
`d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
Use existing public metadata type-round-robin/group sampler with seed20261009,
diagnostic50/reserved10/max_messages20. Exclude all nineteen exact history groups
from both former manifests, including their six reserved groups. Neither gold
values nor earlier scores choose cases. Keep the generated selection even if
performance is disappointing; no reseeding or case replacement.

Compact reproducible selection is committed in
`benchmarks/datasets/longmemeval-expansion-50-selection-v1.json`; it contains IDs,
partitions, type strata, history hashes and sizes, not question/answer or raw text.
Full ignored manifest `data/doppel/longmemeval-expansion-50-manifest-v1.json`:

- Fingerprint `e7e7214f0160a69b90d9535a3d9c9696a8a1fcbef9e2ad20204f836551830fa7`.
- File SHA-256 `28dc31edbcfc119d5f952d9f0ab3ceeaa123a5e9a5bfef70f82f9febbc120721`.
- Fifty histories: **24,891 raw/nonblank messages, 2,420 chunks**.
- Type counts: assistant9, knowledge-update9, multi-session8, preference8,
  temporal8, user8. Metadata is used for selection only, never runtime prompts.
- **One** no-answer-labeled question (`29f2956b_abs`). It permits a smoke
  observation, not reliable refusal-rate measurement. Do not claim adequate
  absence coverage or replace cases after discovering this distribution.
- Seventy-six session-content hashes are shared across the sixty selected groups.
  Grouping/exclusion prevents exact full-history reuse, not complete session
  independence; this is public development, not independently blind evaluation.
- Ten newly reserved histories stay unexecuted. Old reserved histories also remain
  unopened. No question-relative arrival cutoff; keep the full supplied haystack,
  original roles, order and dates, as in the previous declared protocol.

## Extraction/storage configuration and first block

Ingestion plan fingerprint:
`03134787d46171f0109d6e9770b68ed9f84f1d0a9d45d23aa4c9eaf32a0ba458`.
Zero-call preflight `data/doppel/longmemeval-expansion-50-ingestion-preflight-v1.json`,
SHA-256 `a9ee827e8de0fdd52981ba3732f6a187947bc47f9b9f9da288e63df616766ca2`.
New namespace `data/doppel/public-memory-expansion-50-v1/ingestion`; dedicated PG
schema `public_memory_03134787d461`. No old namespace migration, reset or repair.

Use unchanged extraction configuration: DeepSeek v4 flash, JSON object,
temperature0/thinking disabled/max_tokens8192, timeout120; same production
analyzer/Miner/consolidator/evidence qualification, quarantine policy, local
BGE-small-zh512 and raw-source/index persistence. No weakening of speaker,
subject or scope gates. Rejected/invalid drafts must be reported, not hidden.

Lifetime extraction attempt cap: **2,420**, equal to source chunks, no retry reserve.
**This invocation permits only94 new chunks/attempts**, the complete first two
histories (50+44 source chunks). It stops at that boundary or earlier on failure.
Do not silently spend the remaining2,326 calls. Each later bounded block needs
an explicit continuation/report; ledger limits survive restarts. Failed calls
consume the cap and remain recorded, even if an explicit separate recovery is
later authorized. Canonical-byte/attempt caps are not exact tokenizer/billing caps.
No Reader/Judge calls or scores on the completed prefix in this stage.

Normal chunk/index completion and final Store/provenance audit must pass. Output
is **partial**, not successful fifty-history completion, until all2,420 chunks
complete. A model/provider failure stops rather than replaces a history or raises
the response cap. Use fresh output paths and retain pending journals/caches.
Docker must already be running; otherwise ask the owner to open it manually.
Read local diagnostic credentials only in-process and keys only from environment.

The CLI parameters used for the first block, after loading the diagnostic DSN
in-process, are:

```powershell
--dataset data/public-benchmarks/longmemeval_s_cleaned.json `
--manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
--run-dir data/doppel/public-memory-expansion-50-v1/ingestion `
--output data/doppel/longmemeval-expansion-50-ingestion-block01-v1.json `
--max-new-chunks 94 --max-calls 2420 `
--model deepseek-v4-flash --base-url https://api.deepseek.com `
--schema-mode json_object --max-output-tokens 8192 `
--evidence-error-policy quarantine --api-key-env DEEPSEEK_API_KEY `
--embedding-cache-dir C:/Users/freeze/AppData/Local/Temp/fastembed_cache --live
```

## Subsequent quality stage, not yet executed

Finish the fixed full histories through bounded ingestion. Then freeze a scalable
fifty-question harness before query/answer execution: compare raw, memory and
combined with shared80-candidate/20-item/24KB budgets, unchanged local models and
the baseline prefix packer (the fit experiment showed no demonstrated gain).
Use the same Reader; assess answer correctness against question/reference/answer,
separately from context support and justified refusal. Do not copy the original
known noisy Judge labels or count an answerable refusal as correct. The actual
scoring request/schema, durable budgets and run identity require a separate
implementation/freeze before calls; they are not claimed complete here.

Report denominators, all stopped/unscored cases, six type groups and no-answer
observations. Do not report an overall full-benchmark score or a tiny no-answer
percentage as reliable. No Graphiti/production Planner or AML model compliance
is implied by this vector composition stage. Finish this coverage stage without
new case-specific rules, prompt chasing or an additional calibration taxonomy loop.
