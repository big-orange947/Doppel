# Fifty-history expansion: block09 result and block10 freeze

## Block09 result

- Parent checkpoint:1,154 completed chunks; block09 revalidated all1,154 before any new LLM call.
- New work:200/200 chunks completed; report status `partial` because the frozen per-block cap was reached.
- Cumulative source progress:1,354/2,420 chunks across 28 histories (27 complete, one partial,22 untouched).
- Calls/tokens:200 successful calls,999,463 reported tokens; usage was complete for all calls.
- Store audit:13,990 raw records,5,489 derived records (including inactive),79 governance records;20,989 provenance checks, zero failures.
- No retrieval, Reader, Judge, QA, or quality metrics ran. This is ingestion-only progress, not a LongMemEval score.
- The report explicitly records `semantic_truth_verified=false`, `publication_ready=false`, and `aml_academic_model_compliant=false`.
- Result: `data/doppel/longmemeval-expansion-50-ingestion-block09-v1.json` (SHA-256 `fcbff478143f2f96820f716eeeda8d091dde514d538f75bd565e167a058f12b7`).

## Block10 frozen plan

- Parent report SHA-256: `fcbff478143f2f96820f716eeeda8d091dde514d538f75bd565e167a058f12b7`.
- Parent checkpoint:1,354 chunks; 353 inherited,1,001 successful child-local attempts.
- Parent Store audit:20,989 provenance checks, zero failures.
- Remaining source chunks:1,066.
- Maximum new work:200 chunks / 200 calls; zero QA, retrieval, Reader, or Judge calls.
- Plan fingerprint: `39a536d833e547161d6a3ae0781bad680b83447f655f434f4882846fff1cef6f`.
- Frozen plan file: `data/doppel/public-memory-expansion-50-block04-recovery-v1/continuation-plan-39a536d833e5.json`.
- Intended output: `data/doppel/longmemeval-expansion-50-ingestion-block10-v1.json`.

The no-call plan was generated against the completed block09 report and existing
checkpoint. Execution must use the unchanged dataset, manifest, child run
directory, and frozen200-call cap. Any transport failure stops the block and
must be handled with a separately frozen recovery plan; no automatic retry or
budget increase is allowed.

## Reproduction

```powershell
D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_ingestion_continuation `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --parent-report data/doppel/longmemeval-expansion-50-ingestion-block09-v1.json `
  --run-dir data/doppel/public-memory-expansion-50-block04-recovery-v1 `
  --output data/doppel/longmemeval-expansion-50-ingestion-block10-v1.json `
  --max-new-chunks 200
```

Append `--live` only to execute. The API key remains in the existing process
environment; Docker must already be running. Do not alter the unrelated dirty
`uv.lock`.
