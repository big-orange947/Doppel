# Fifty-history expansion: block06 result and block07 freeze

## Block06 result

- Parent checkpoint:554 completed chunks; block06 revalidated all554 before any new LLM call.
- New work:200/200 chunks completed; report status `partial` because the frozen per-block cap was reached.
- Cumulative source progress:754/2,420 chunks across 16 histories (15 complete, one partial,34 untouched).
- Calls/tokens:200 successful calls,993,151 reported tokens; usage was complete for all calls.
- Store audit:7,827 raw records,3,086 derived records (including inactive),44 governance records;11,773 provenance checks, zero failures.
- No retrieval, Reader, Judge, QA, or quality metrics ran. This is ingestion-only progress, not a LongMemEval score.
- The report explicitly records `semantic_truth_verified=false`, `publication_ready=false`, and `aml_academic_model_compliant=false`.
- Result: `data/doppel/longmemeval-expansion-50-ingestion-block06-v1.json` (SHA-256 `85f32edc5ecd15b77a30828c227a132c29bf16cd5d6c65e4eea66b2e56aeae71`).

## Block07 frozen plan

- Parent report SHA-256: `85f32edc5ecd15b77a30828c227a132c29bf16cd5d6c65e4eea66b2e56aeae71`.
- Parent checkpoint:754 chunks; 353 inherited,401 successful child-local attempts.
- Parent Store audit:11,773 provenance checks, zero failures.
- Remaining source chunks:1,666.
- Maximum new work:200 chunks / 200 calls; zero QA, retrieval, Reader, or Judge calls.
- Plan fingerprint: `21faf0efc0b3d36a648c4a6f2c2ac5955bb1bcd7c6df41d112cec8befc7f90dc`.
- Frozen plan file: `data/doppel/public-memory-expansion-50-block04-recovery-v1/continuation-plan-21faf0efc0b3.json`.
- Intended output: `data/doppel/longmemeval-expansion-50-ingestion-block07-v1.json`.

The no-call plan was generated against the completed block06 report and existing
checkpoint. Execution must use the unchanged dataset, manifest, child run
directory, and frozen200-call cap. Any transport failure stops the block and
must be handled with a separately frozen recovery plan; no automatic retry or
budget increase is allowed.

## Reproduction

```powershell
D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_ingestion_continuation `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --parent-report data/doppel/longmemeval-expansion-50-ingestion-block06-v1.json `
  --run-dir data/doppel/public-memory-expansion-50-block04-recovery-v1 `
  --output data/doppel/longmemeval-expansion-50-ingestion-block07-v1.json `
  --max-new-chunks 200
```

Append `--live` only to execute. The API key remains in the existing process
environment; Docker must already be running. Do not alter the unrelated dirty
`uv.lock`.
