# Fifty-history expansion: block07 result and block08 freeze

## Block07 result

- Parent checkpoint:754 completed chunks; block07 revalidated all754 before any new LLM call.
- New work:200/200 chunks completed; report status `partial` because the frozen per-block cap was reached.
- Cumulative source progress:954/2,420 chunks across 20 histories (19 complete, one partial,30 untouched).
- Calls/tokens:200 successful calls,1,032,276 reported tokens; usage was complete for all calls.
- Store audit:9,898 raw records,3,945 derived records (including inactive),53 governance records;14,923 provenance checks, zero failures.
- No retrieval, Reader, Judge, QA, or quality metrics ran. This is ingestion-only progress, not a LongMemEval score.
- The report explicitly records `semantic_truth_verified=false`, `publication_ready=false`, and `aml_academic_model_compliant=false`.
- Result: `data/doppel/longmemeval-expansion-50-ingestion-block07-v1.json` (SHA-256 `5ab81830211474679d3f636152c1d3572b4ed077d7a23c1a671b0916af7e051b`).

## Block08 frozen plan

- Parent report SHA-256: `5ab81830211474679d3f636152c1d3572b4ed077d7a23c1a671b0916af7e051b`.
- Parent checkpoint:954 chunks; 353 inherited,601 successful child-local attempts.
- Parent Store audit:14,923 provenance checks, zero failures.
- Remaining source chunks:1,466.
- Maximum new work:200 chunks / 200 calls; zero QA, retrieval, Reader, or Judge calls.
- Plan fingerprint: `de9b8546aaa18f823901c4087da6add1b39fd4541118a52dfc3f29dc5617ec80`.
- Frozen plan file: `data/doppel/public-memory-expansion-50-block04-recovery-v1/continuation-plan-de9b8546aaa1.json`.
- Intended output: `data/doppel/longmemeval-expansion-50-ingestion-block08-v1.json`.

The no-call plan was generated against the completed block07 report and existing
checkpoint. Execution must use the unchanged dataset, manifest, child run
directory, and frozen200-call cap. Any transport failure stops the block and
must be handled with a separately frozen recovery plan; no automatic retry or
budget increase is allowed.

## Reproduction

```powershell
D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_ingestion_continuation `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --parent-report data/doppel/longmemeval-expansion-50-ingestion-block07-v1.json `
  --run-dir data/doppel/public-memory-expansion-50-block04-recovery-v1 `
  --output data/doppel/longmemeval-expansion-50-ingestion-block08-v1.json `
  --max-new-chunks 200
```

Append `--live` only to execute. The API key remains in the existing process
environment; Docker must already be running. Do not alter the unrelated dirty
`uv.lock`.
