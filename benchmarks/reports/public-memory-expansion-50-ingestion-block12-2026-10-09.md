# Fifty-history expansion: block12 result and block13 freeze

## Block12 result

- Parent checkpoint:1,754 completed chunks; block12 revalidated all1,754 before any new LLM call.
- New work:200/200 chunks completed; report status `partial` because the frozen per-block cap was reached.
- Cumulative source progress:1,954/2,420 chunks across 41 histories (40 complete, one partial,9 untouched).
- Calls/tokens:200 successful calls,982,292 reported tokens; usage was complete for all calls.
- Store audit:20,107 raw records,7,851 derived records (including inactive),103 governance records;30,157 provenance checks, zero failures.
- No retrieval, Reader, Judge, QA, or quality metrics ran. This is ingestion-only progress, not a LongMemEval score.
- The report explicitly records `semantic_truth_verified=false`, `publication_ready=false`, and `aml_academic_model_compliant=false`.
- Result: `data/doppel/longmemeval-expansion-50-ingestion-block12-v1.json` (SHA-256 `29cbd9603859e2ad7fd4beb62c5b853ebe1cce4fd49c759c69b7e6971887ff1c`).

## Block13 frozen plan

- Parent report SHA-256: `29cbd9603859e2ad7fd4beb62c5b853ebe1cce4fd49c759c69b7e6971887ff1c`.
- Parent checkpoint:1,954 chunks; 353 inherited,1,601 successful child-local attempts.
- Parent Store audit:30,157 provenance checks, zero failures.
- Remaining source chunks:466.
- Maximum new work:200 chunks / 200 calls; zero QA, retrieval, Reader, or Judge calls.
- Plan fingerprint: `771dc46df12eef74c395776a3e66b1dcfbac39a40763e90c29ce1d3523b930cc`.
- Frozen plan file: `data/doppel/public-memory-expansion-50-block04-recovery-v1/continuation-plan-771dc46df12e.json`.
- Intended output: `data/doppel/longmemeval-expansion-50-ingestion-block13-v1.json`.

The no-call plan was generated against the completed block12 report and existing
checkpoint. Execution must use the unchanged dataset, manifest, child run
directory, and frozen200-call cap. Any transport failure stops the block and
must be handled with a separately frozen recovery plan; no automatic retry or
budget increase is allowed.

## Reproduction

```powershell
D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_ingestion_continuation `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --parent-report data/doppel/longmemeval-expansion-50-ingestion-block12-v1.json `
  --run-dir data/doppel/public-memory-expansion-50-block04-recovery-v1 `
  --output data/doppel/longmemeval-expansion-50-ingestion-block13-v1.json `
  --max-new-chunks 200
```

Append `--live` only to execute. The API key remains in the existing process
environment; Docker must already be running. Do not alter the unrelated dirty
`uv.lock`.
