# Fifty-history expansion: block11 result and block12 freeze

## Block11 result

- Parent checkpoint:1,554 completed chunks; block11 revalidated all1,554 before any new LLM call.
- New work:200/200 chunks completed; report status `partial` because the frozen per-block cap was reached.
- Cumulative source progress:1,754/2,420 chunks across 37 histories (36 complete, one partial,13 untouched).
- Calls/tokens:200 successful calls,992,600 reported tokens; usage was complete for all calls.
- Store audit:18,077 raw records,7,176 derived records (including inactive),95 governance records;27,230 provenance checks, zero failures.
- No retrieval, Reader, Judge, QA, or quality metrics ran. This is ingestion-only progress, not a LongMemEval score.
- The report explicitly records `semantic_truth_verified=false`, `publication_ready=false`, and `aml_academic_model_compliant=false`.
- Result: `data/doppel/longmemeval-expansion-50-ingestion-block11-v1.json` (SHA-256 `4cb6e7a48e46a894492a5bf8193abbee2727c84ccad09aa5f417f7ae87927fde`).

## Block12 frozen plan

- Parent report SHA-256: `4cb6e7a48e46a894492a5bf8193abbee2727c84ccad09aa5f417f7ae87927fde`.
- Parent checkpoint:1,754 chunks; 353 inherited,1,401 successful child-local attempts.
- Parent Store audit:27,230 provenance checks, zero failures.
- Remaining source chunks:666.
- Maximum new work:200 chunks / 200 calls; zero QA, retrieval, Reader, or Judge calls.
- Plan fingerprint: `2d3002b26988da9d3c60ee6ee0696a0f676d1a1c8f9b98b9a07aabcebb73b41d`.
- Frozen plan file: `data/doppel/public-memory-expansion-50-block04-recovery-v1/continuation-plan-2d3002b26988.json`.
- Intended output: `data/doppel/longmemeval-expansion-50-ingestion-block12-v1.json`.

The no-call plan was generated against the completed block11 report and existing
checkpoint. Execution must use the unchanged dataset, manifest, child run
directory, and frozen200-call cap. Any transport failure stops the block and
must be handled with a separately frozen recovery plan; no automatic retry or
budget increase is allowed.

## Reproduction

```powershell
D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_ingestion_continuation `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --parent-report data/doppel/longmemeval-expansion-50-ingestion-block11-v1.json `
  --run-dir data/doppel/public-memory-expansion-50-block04-recovery-v1 `
  --output data/doppel/longmemeval-expansion-50-ingestion-block12-v1.json `
  --max-new-chunks 200
```

Append `--live` only to execute. The API key remains in the existing process
environment; Docker must already be running. Do not alter the unrelated dirty
`uv.lock`.
