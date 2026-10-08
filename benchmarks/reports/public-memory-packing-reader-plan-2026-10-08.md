# Same-Reader fit-context comparison: at most five new calls

Freeze this code and plan before execution. Do not change Reader instructions,
schema, provider configuration or the thirty logical question/channel rows.
Baseline remains the completed ten-history continuation, and candidate contexts
are the completed zero-provider paired packing result. Gold/profile/old answers
are not included in Reader requests. No extraction, retrieval, Judge, source
expansion, Store/index write or reserved-history execution.

Bound parent report SHA-256:
`6d2bb1f48ed03830c21706afbb8b80d580dfb8ec913e7d00ad903f321e975932`.
Packing report SHA-256:
`fc6e367bb0b5df0aaec95949393372a7d9d0dc6e98ba3ca46e139140fa1fed3b`.
Plan fingerprint:
`907fbfc93547396b0b4502387629f283d2e83cf3ea1239b9406819ba6203fa2b`.
Preflight SHA-256:
`8a6ccd146b065bd00fe885c403d0931f7c885cd74b78d0279dbdaeac63d6e12c`.

Rows 9,11,12,26,27 have changed request payloads; the other twenty-five use exact
original requests. Before any live call, read-only original cache reuse must
validate every unchanged request and match its preserved original Reader output.
Any missing/invalid/different reused output stops the experiment before paid work.
The cache inventory and input files are hash-bound and checked after execution.
No unchanged request may be billed as a cache miss.

New lifetime cap: **five Reader attempts, zero Judge attempts**. The unchanged
DeepSeek v4 flash configuration stays JSON object, temperature0, thinking disabled,
max_tokens2048. Independent fresh journal/cache namespace; original cache is
read-only. Failed attempts are retained and consume budget; no retry or prompt
repair. An attempted namespace may only replay cache-only, not rebill. Run a
separate key-free cache-only replay after completion, comparing all outputs,
checks and cumulative accounting. Keys remain in environment variables.

Publish all thirty logical rows, not only changed or successful cases. Report
behavior changes and citation/derivation structure, with no automatic accuracy
score. A bounded source-based reading may describe concrete reference delivery
versus refusal, but is not an independent exhaustive QA audit. Do not reuse the
known flawed Judge labels or convert a justified answerable refusal into success.
More packed items, legal IDs and changed answers do not prove improvement.

```powershell
& D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_packing_reader `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-10-manifest-v1.json `
  --parent-report data/doppel/longmemeval-continuation-10-live-v1.json `
  --packing-report data/doppel/longmemeval-packing-live-v1.json `
  --parent-cache data/doppel/public-memory-continuation-10-v1/answers/reader-cache `
  --run-dir data/doppel/public-memory-packing-reader-v1 `
  --output data/doppel/longmemeval-packing-reader-live-v1.json `
  --frozen-plan data/doppel/longmemeval-packing-reader-preflight-v1.json --live
```

This closes the already opened ten-history experiment; do not continue tweaking
it based on the next answers. Larger new-history coverage is the next stage.
This is not full LongMemEval, independent blind evaluation or AML performance.
