# One unchanged-request recovery observation after transport failure

Block02 stopped after36 successful new calls and one failed attempt. The failed
attempt is retained in its own durable ledger and consumes budget. Its redacted
diagnostic is `transport_error`, without HTTP status, finish reason or usage.
Block02's report and checkpoints remain preserved. This plan authorizes one
separate recovery observation for the exact same pending chunk; it is not an
automatic retry loop or a fresh history selection.

## Frozen recovery binding

- Parent report SHA-256: `dab74cb127f73f8585f07b7928d630ac8d46c19f7484d0be10d7e71456b979da`.
- Parent completed chunks: 130; one pending extraction chunk follows that prefix.
- Parent calls in this continuation ledger:37 (36 successful,1 failed).
- Failed transport request identity is the frozen pending chunk in the parent report.
- Recovery plan fingerprint: `39c5e63976c8d48f5a19c70ad12d6fb078ec9c196b4893c81d8e15d50547580d`.
- Recovery plan file SHA-256: `194d5b58b92c00fa0f799da7380965141db2c7e36d659d995b1eba8120668791`.
- New recovery budget: **one call / one chunk**, unchanged model, prompt and settings.
- Parent journal and provider-cache inventory are hash-bound and read-only.
- Fresh recovery checkpoint: `data/doppel/public-memory-expansion-50-block02-recovery-v1`.
- Zero-call preflight report: `data/doppel/longmemeval-expansion-50-block02-recovery-v1.json`.
- Live recovery report: `data/doppel/longmemeval-expansion-50-block02-recovery-live-v1.json`.

Recovery code clones the journal into a new checkpoint, reads the parent cache
without writing to it, and independently records the one-call recovery budget.
The failed output is not inferred or reconstructed. The source message, labels
and QA question do not enter a different query; this is only extraction recovery.
No retrieval, Reader, Judge or quality score executes. If the unchanged attempt
fails, preserve both failures and stop for diagnosis; do not issue a third call.

Docker's diagnostic PostgreSQL service was healthy at preflight. The local DSN is
loaded in-process. API key access is environment-only; secrets are not logged or
written to artifacts. `uv.lock`, source dataset, parent report, parent journal,
parent cache and original block report remain untouched.

Reproduction command:

```powershell
D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_recovery `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --parent-report data/doppel/longmemeval-expansion-50-block02-v1.json `
  --parent-report-sha256 dab74cb127f73f8585f07b7928d630ac8d46c19f7484d0be10d7e71456b979da `
  --parent-dir data/doppel/public-memory-expansion-50-v1/ingestion `
  --run-dir data/doppel/public-memory-expansion-50-block02-recovery-v1 `
  --output data/doppel/longmemeval-expansion-50-block02-recovery-live-v1.json `
  --embedding-cache-dir C:/Users/freeze/AppData/Local/Temp/fastembed_cache --live
```

This is a public development diagnostic, not full LongMemEval, independent blind
evaluation, production Planner/Graphiti or AML performance.
