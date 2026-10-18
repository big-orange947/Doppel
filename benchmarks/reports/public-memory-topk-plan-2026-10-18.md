# Explicit Top-20 diagnostic: frozen before live calls

Date: 2026-10-18. This is an opened-three development diagnostic, not a blind
benchmark, complete LongMemEval score, AML score or default-configuration change.

## Fixed question and design

The prior full-permutation smoke failed after one valid JSON response omitted one
of80 IDs. Preserve that report, cache, 19,290 tokens and failed result. This new
experiment does not truncate that response, append IDs or reinterpret it as a
successful Top-20 selection. Use a new contract, requests, cache and budget.

Only the previously opened cases `e9327a54`, `gpt4_ec93e27f`, `gpt4_2f8be40d` are
used. Reuse the exact old content-only passage baseline (provisional2/3), bound by
context bytes and Reader request hashes. No new baseline calls.

One new profile: `metadata_top20_selected_unranked`.

1. Reproduce existing production BM25/vector top80; exact prior pool and scoped
   Store inventory hashes must match. Revalidate source provenance and authority.
2. Ask the model for exactly20 distinct authorized IDs, in useful order. Do not
   ask it to rank the unselected60. Record those60 as **unranked, without scores**.
3. Split selected sources with unchanged1,200-character/160-overlap lossless spans,
   round-robin bounded80 candidates. Ask for exactly min(20, pool size) passages.
4. Return only selected immutable originals; never fill from the unselected tail.
   Fresh Store/hash/offset checks remain; no speaker quotas or scenario heuristics.
5. Unchanged skip-to-fit24,000-byte/20-item packing, Reader v2 and provisional
   task judge. No prompt, scoring or answer-policy tuning after seeing results.

The model gets only question, opaque IDs, original text and source attribution/
supplied time; no reference answer, evidence labels, profile names or old judgments.
Schema hints specify count, uniqueness and ID enum, but runtime validation is
mandatory even when a JSON-object provider ignores schema constraints. Unknown,
duplicate, extra or omitted selected IDs fail without repair or retry. Inclusion
is not an assertion of answerability, completeness or factual authority.

## Frozen preflight

Entry point: `python -m benchmarks.public_memory_topk_diagnostic`.
Artifact: `data/doppel/topk-diagnostic-preflight-v1.json`, zero provider calls.
Plan fingerprint:
`f8013a2b5d726a3bf5368df891757038a95350e98e3715893d55cdfcf17f8d67`.

| Case | Authorized source candidates | Selected count | Source request bytes |
| --- | ---: | ---: | ---: |
| e9327a54 | 80 | 20 | 76,743 |
| gpt4_ec93e27f | 80 | 20 | 105,642 |
| gpt4_2f8be40d | 80 | 20 | 123,208 |

The plan binds dataset/parent hashes, old failed-report hash, unchanged source/
candidate inventories, actual source requests, implementation hashes and model
configurations. Source text is not truncated. New run directory:
`data/doppel/topk-diagnostic-20261018-v1`. No prior cache is imported.

## Limits and decision

At most **12 new calls**:6 selection,3 Reader,3 task judge. Prior1 call/19,290
tokens is additional historical spend, not erased or refunded into this budget.
DeepSeek `deepseek-v4-flash`, JSON-object mode, temperature0, thinking disabled.
Completion caps: selection1,024, Reader2,048, judge1,024 tokens. No automatic
retries. Per-request canonical bytes: selector500,000, Reader/judge100,000;
total bytes: selector1,500,000, Reader/judge300,000 each. Durable SQLite ledgers,
exact-output caches, pre-await request receipts and per-case context/QA checkpoints.
Stop on first runtime/validation failure and preserve actual/missing provider usage.
Byte/output caps are not exact billing guarantees. Key stays environment-only.

Run offline guards before paid execution, commit plan/code, then execute only the
matching preflight. Report actual paired answers, provisional grades, provenance/
Store checks, fragment and packing losses, calls and tokens. Three opened cases
cannot establish a general gain. A promising result warrants a separately frozen
untouched small continuation, not a default promotion. A failed result warrants
attribution rather than scenario rules or another judge-calibration loop.

Do not author graphs, analyze complete histories, modify Store/vector data or
schemas, reset databases, open reserved/41–50 cases, edit old scores/cache outputs,
or stage the user's unrelated `uv.lock`.
