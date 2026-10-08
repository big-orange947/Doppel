# Fifty-history expansion: block10 result and block11 freeze

## Block10 result

- Parent checkpoint:1,354 completed chunks; block10 revalidated all1,354 before any new LLM call.
- New work:200/200 chunks completed; report status `partial` because the frozen per-block cap was reached.
- Cumulative source progress:1,554/2,420 chunks across 33 histories (32 complete, one partial,17 untouched).
- Calls/tokens:200 successful calls,1,008,332 reported tokens; usage was complete for all calls.
- Store audit:16,009 raw records,6,331 derived records (including inactive),86 governance records;24,059 provenance checks, zero failures.
- No retrieval, Reader, Judge, QA, or quality metrics ran. This is ingestion-only progress, not a LongMemEval score.
- The report explicitly records `semantic_truth_verified=false`, `publication_ready=false`, and `aml_academic_model_compliant=false`.
- Result: `data/doppel/longmemeval-expansion-50-ingestion-block10-v1.json` (SHA-256 `50def994d0ec50662a86424152f64527043dacf65aec39895240fa643cd45783`).

## Block11 frozen plan

- Parent report SHA-256: `50def994d0ec50662a86424152f64527043dacf65aec39895240fa643cd45783`.
- Parent checkpoint:1,554 chunks; 353 inherited,1,201 successful child-local attempts.
- Parent Store audit:24,059 provenance checks, zero failures.
- Remaining source chunks:866.
- Maximum new work:200 chunks / 200 calls; zero QA, retrieval, Reader, or Judge calls.
- Plan fingerprint: `97aa5f88c29889b6c115b870c9d25d9078d42d6ac6ed2ea0469dc0883c7ff93e`.
- Frozen plan file: `data/doppel/public-memory-expansion-50-block04-recovery-v1/continuation-plan-97aa5f88c298.json`.
- Intended output: `data/doppel/longmemeval-expansion-50-ingestion-block11-v1.json`.

The no-call plan was generated against the completed block10 report and existing
checkpoint. Execution must use the unchanged dataset, manifest, child run
directory, and frozen200-call cap. Any transport failure stops the block and
must be handled with a separately frozen recovery plan; no automatic retry or
budget increase is allowed.

## Reproduction

```powershell
D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_ingestion_continuation `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --parent-report data/doppel/longmemeval-expansion-50-ingestion-block10-v1.json `
  --run-dir data/doppel/public-memory-expansion-50-block04-recovery-v1 `
  --output data/doppel/longmemeval-expansion-50-ingestion-block11-v1.json `
  --max-new-chunks 200
```

Append `--live` only to execute. The API key remains in the existing process
environment; Docker must already be running. Do not alter the unrelated dirty
`uv.lock`.
