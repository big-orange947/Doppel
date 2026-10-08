# Fifty-history expansion: block08 result and block09 freeze

## Block08 result

- Parent checkpoint:954 completed chunks; block08 revalidated all954 before any new LLM call.
- New work:200/200 chunks completed; report status `partial` because the frozen per-block cap was reached.
- Cumulative source progress:1,154/2,420 chunks across 24 histories (23 complete, one partial,26 untouched).
- Calls/tokens:200 successful calls,1,006,976 reported tokens; usage was complete for all calls.
- Store audit:11,936 raw records,4,720 derived records (including inactive),70 governance records;17,990 provenance checks, zero failures.
- No retrieval, Reader, Judge, QA, or quality metrics ran. This is ingestion-only progress, not a LongMemEval score.
- The report explicitly records `semantic_truth_verified=false`, `publication_ready=false`, and `aml_academic_model_compliant=false`.
- Result: `data/doppel/longmemeval-expansion-50-ingestion-block08-v1.json` (SHA-256 `2d7ffa64a61cbd2eb8106f7be96299dc08cbf80c5db7a87547538af846f44bad`).

## Block09 frozen plan

- Parent report SHA-256: `2d7ffa64a61cbd2eb8106f7be96299dc08cbf80c5db7a87547538af846f44bad`.
- Parent checkpoint:1,154 chunks; 353 inherited,801 successful child-local attempts.
- Parent Store audit:17,990 provenance checks, zero failures.
- Remaining source chunks:1,266.
- Maximum new work:200 chunks / 200 calls; zero QA, retrieval, Reader, or Judge calls.
- Plan fingerprint: `909c70423b9b565cf2b0ea3768a8c8b7a082613e941cb5d6a034a9037b367d30`.
- Frozen plan file: `data/doppel/public-memory-expansion-50-block04-recovery-v1/continuation-plan-909c70423b9b.json`.
- Intended output: `data/doppel/longmemeval-expansion-50-ingestion-block09-v1.json`.

The no-call plan was generated against the completed block08 report and existing
checkpoint. Execution must use the unchanged dataset, manifest, child run
directory, and frozen200-call cap. Any transport failure stops the block and
must be handled with a separately frozen recovery plan; no automatic retry or
budget increase is allowed.

## Reproduction

```powershell
D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_ingestion_continuation `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --parent-report data/doppel/longmemeval-expansion-50-ingestion-block08-v1.json `
  --run-dir data/doppel/public-memory-expansion-50-block04-recovery-v1 `
  --output data/doppel/longmemeval-expansion-50-ingestion-block09-v1.json `
  --max-new-chunks 200
```

Append `--live` only to execute. The API key remains in the existing process
environment; Docker must already be running. Do not alter the unrelated dirty
`uv.lock`.
