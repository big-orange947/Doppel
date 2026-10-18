# Opened-three listwise ranking comparison (frozen before paid calls)

Date: 2026-10-18. This is a bounded diagnostic, not an independent benchmark,
complete LongMemEval run, production-default promotion or AML score.

## Question and fixed design

Can a general listwise model select useful original evidence where a passage
cross-encoder plus metadata/MMR did not? Do not add topic/role quotas or rules for
individual questions. Do not alter the Reader, task judge or old scores.

The already-opened cases are `e9327a54`, `gpt4_ec93e27f`, `gpt4_2f8be40d`.
Frozen content-only source/passage baseline: 2/3 provisional task grades, reused
with exact context and Reader request hash checks, zero new baseline calls.
Previous BGE metadata/MMR candidate was 1/3 with a known hedging-sensitive grade;
do not reinterpret it or repeat judge calibration.

One new profile only, `metadata_listwise_no_mmr`:

1. Reproduce the existing production BM25/vector top-80 pool, exact same pool hash
   as the prior experiment; revalidate scoped source content in read-only Store.
2. One listwise source call, keep top 20. Speaker/authority/supplied time are
   explicit, with source text unchanged and opaque request-local IDs only.
3. Unchanged lossless splitter: 1,200 characters, 160 overlap, round-robin bounded
   80 fragments; one listwise passage call, keep top 20. No source MMR.
4. Unchanged skip-to-fit packer: 24,000 UTF-8 bytes, at most 20 items. Preserve
   original-source hash, offsets, attribution and fresh Store revocation checks.
5. Unchanged Reader v2, then unchanged provisional DeepSeek task judge.

The ranking prompt contains no answer, labels, profile names or case-specific
examples. It ranks complementary evidence but cannot write or repair memory.
Only a complete ID permutation is accepted; no output repair or retry.

## Frozen preflight and accounting

Entry point: `python -m benchmarks.public_memory_listwise_diagnostic`.
Preflight: `data/doppel/listwise-diagnostic-preflight-v1.json`, zero model calls.
Plan fingerprint:
`ff2a2489aba98c92550a985b88c5734265c72b9419e1894b597708ab01367d64`.
The plan binds six parent/dataset files, original Store inventories, candidate
pools, source request hashes, implementation hashes and model configurations.

| Case | Source candidates | Source content characters | Canonical request bytes |
| --- | ---: | ---: | ---: |
| e9327a54 | 80 | 68,023 | 75,404 |
| gpt4_ec93e27f | 80 | 96,976 | 104,303 |
| gpt4_2f8be40d | 80 | 114,351 | 121,869 |

New-call hard limits: ranking 6, Reader 3, judge 3; **12 total**. DeepSeek
`deepseek-v4-flash`, temperature 0, thinking disabled, JSON-object mode. Completion
limits: ranker/Reader 2,048 tokens, judge 1,024. No automatic retries. The durable
ledger caps canonical request bytes: ranker 500,000/call and 1,500,000 total;
Reader/judge each 100,000/call and 300,000 total. These are not hard billing/token
caps; actual provider usage must be reported separately, including missing usage.

Run directory: `data/doppel/listwise-diagnostic-20261018-v1`. Exact-output cache
and SQLite ledgers stay in the ignored data directory; the key is environment-only.
Each ranking request gets a pre-await receipt and each completed case a checkpoint.
Stop on the first provider/validation/QA failure, keeping billed attempts and caches.

No graph authoring, schema/data resets, full-history LLM extraction, reserved or
new 41–50 QA cases, model downloads, benchmark-answer heuristics, source writes or
unrelated `uv.lock` changes are authorized by this experiment.

## Decision rule

Report paired primary grades, actual answers, citation legality (not semantic
proof), provenance/Store checks, source-to-fragment/packing losses and costs.
Three opened cases cannot prove an accuracy gain. If the candidate offers no
useful evidence improvement, stop it without stacking rules. If promising, the
next step is a separately frozen untouched small continuation, not deployment or
a 500-question/generalization claim. No post-result winner selection among prompts.
