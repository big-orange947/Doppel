# Fifty-history expansion: block05 result and block06 freeze

## Block05 result

- Parent checkpoint:354 completed chunks; block05 revalidated all354 before any new LLM call.
- New work:200/200 chunks completed; report status `partial` because the frozen per-block cap was reached, not because of an execution failure.
- Cumulative source progress:554/2,420 chunks across 12 histories (11 complete, one partial,38 untouched).
- Calls/tokens:200 successful calls,1,038,589 reported tokens; usage was complete for all calls.
- Store audit:5,746 raw records,2,271 derived records (including inactive),31 governance records;8,634 provenance checks, zero failures.
- No retrieval, Reader, Judge, QA, or quality metrics ran. This is ingestion-only progress, not a LongMemEval score.
- The report explicitly records `semantic_truth_verified=false`, `publication_ready=false`, and `aml_academic_model_compliant=false`.
- Result: `data/doppel/longmemeval-expansion-50-ingestion-block05-v1.json`.

## Block06 frozen plan

- Parent report SHA-256: `3d1ee88bcd262ce159e8fe6ca5fda6567c172be5b6387975155ceabe0071ff7c`.
- Parent checkpoint:554 chunks; 353 inherited,201 successful child-local attempts.
- Parent Store audit:8,634 provenance checks, zero failures.
- Remaining source chunks:1,866.
- Maximum new work:200 chunks / 200 calls; zero QA, retrieval, Reader, or Judge calls.
- Plan fingerprint: `622ae417e98be0db39dc99a0c20008ea733314ede4c17dbd24b9296c0cb08d3e`.
- Frozen plan file: `data/doppel/public-memory-expansion-50-block04-recovery-v1/continuation-plan-622ae417e98b.json`.
- Intended output: `data/doppel/longmemeval-expansion-50-ingestion-block06-v1.json`.

The no-call plan was generated against the completed block05 report and existing
checkpoint. Execution must use the unchanged dataset, manifest, child run
directory, and frozen200-call cap. Any transport failure stops the block and
must be handled with a separately frozen recovery plan; no automatic retry or
budget increase is allowed.

## Reproduction

```powershell
D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_ingestion_continuation `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --parent-report data/doppel/longmemeval-expansion-50-ingestion-block05-v1.json `
  --run-dir data/doppel/public-memory-expansion-50-block04-recovery-v1 `
  --output data/doppel/longmemeval-expansion-50-ingestion-block06-v1.json `
  --max-new-chunks 200
```

Append `--live` only to execute. The API key remains in the existing process
environment; Docker must already be running. Do not alter the unrelated dirty
`uv.lock`.
