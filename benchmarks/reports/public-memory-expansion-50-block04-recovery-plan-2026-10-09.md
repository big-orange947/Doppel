# One unchanged-request recovery for block04's transport failure

Block04 stopped at its23rd attempt:22 succeeded and the pending extraction
request has a redacted `transport_error` diagnostic without HTTP status, finish
reason or usage. The attempt is retained in the durable budget. This plan records
one separate observation for that exact unchanged request and stops if it fails.

## Frozen binding

- Parent report SHA-256: `795a9cc3e3121ba9c0dfe6bf5aaeacf49476382e75d4af0844dae8bc1c4a1de1`.
- Parent completed prefix:353 chunks; pending chunk follows it in exact source order.
- Parent block04 attempts:23 (22 successes,1 failed transport call).
- Parent Store audit:5,460 provenance checks, zero failures.
- Recovery plan fingerprint: `430076adcf62fbd4f033f285a922f755813db77e6c192ac8d71c8a8bb2fc667a`.
- Recovery plan file SHA-256: `d291456e356418d5b55fd93b17ec03d0d1971cdbbede626c1fdc4829b6b0340c`.
- Recovery budget: **one new call / one chunk**, same DeepSeek model, request and
  extraction configuration.
- Parent checkpoint: `data/doppel/public-memory-expansion-50-block02-recovery-v1/ingestion`.
- Fresh child checkpoint: `data/doppel/public-memory-expansion-50-block04-recovery-v1`.
- Zero-call preflight report: `data/doppel/longmemeval-public-memory-expansion-50-block04-recovery-v1.json`.
- Live result path: `data/doppel/longmemeval-expansion-50-block04-recovery-live-v1.json`.

The recovery runner clones the durable journal to the fresh child, reads the
parent provider cache without modifying it and uses its own one-call ledger. The
failed request's output is not fabricated or taken from another cache. No query,
Reader, Judge or quality scoring occurs. If the new attempt fails, preserve both
attempts and stop; do not make a third attempt without diagnosis.

At preflight the diagnostic PostgreSQL container is healthy. Local DSN access is
in-process; API key access remains environment-only. The source dataset, block04
report, parent journal/cache and `uv.lock` remain untouched.

Live reproduction command (using a distinct output from the zero-call preflight):

```powershell
D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_recovery `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --parent-report data/doppel/longmemeval-expansion-50-ingestion-block04-v1.json `
  --parent-report-sha256 795a9cc3e3121ba9c0dfe6bf5aaeacf49476382e75d4af0844dae8bc1c4a1de1 `
  --parent-dir data/doppel/public-memory-expansion-50-block02-recovery-v1/ingestion `
  --run-dir data/doppel/public-memory-expansion-50-block04-recovery-v1 `
  --output data/doppel/longmemeval-expansion-50-block04-recovery-live-v1.json `
  --embedding-cache-dir C:/Users/freeze/AppData/Local/Temp/fastembed_cache --live
```

This remains public-data ingestion diagnostics. It produces no LongMemEval QA,
full-benchmark, production Planner/Graphiti or AML result.
