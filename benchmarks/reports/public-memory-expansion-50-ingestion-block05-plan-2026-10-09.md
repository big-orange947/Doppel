# Fifty-history expansion: fifth bounded ingestion block

This block continues from the successful block04 recovery child. The runner
binds and validates the recovery report, dataset, manifest, child Store/journal,
cache and durable ledgers, then revalidates the354-chunk source prefix before
spending any new calls.

## Frozen binding and cap

- Dataset SHA-256: `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
- Manifest SHA-256: `28dc31edbcfc119d5f952d9f0ab3ceeaa123a5e9a5bfef70f82f9febbc120721`.
- Parent recovery report SHA-256: `c05c27293782003a925f202a1fa06067d9be174b2e16b6cef6948c9dbfc39a86`.
- Parent prefix:354 completed chunks, with353 inherited and one successful local
  recovery attempt in the fresh child.
- Store provenance:5,467 checks, zero failures.
- Plan fingerprint: `7a2c1bbda85fed97ad550582d95079b5c2a1e2f728fea88348707d349c2b61e5`.
- Frozen plan: `data/doppel/public-memory-expansion-50-block04-recovery-v1/continuation-plan-7a2c1bbda85f.json`.
- New budget: **200 extraction chunks / 200 calls maximum**;2,066 chunks remain
  before this block. Reader, Judge, retrieval and QA calls are zero.

DeepSeek v4 flash, JSON-object response mode, temperature0, thinking disabled,
max completion8192, production Analyzer/Miner/consolidator and evidence gates,
and local BGE-small-zh512 remain bound to the selection. A failure consumes an
attempt and stops the block. No automatic retry, replacement or budget increase.

The no-call preflight is:

```powershell
D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_ingestion_continuation `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --parent-report data/doppel/longmemeval-expansion-50-block04-recovery-live-v1.json `
  --run-dir data/doppel/public-memory-expansion-50-block04-recovery-v1 `
  --output data/doppel/longmemeval-expansion-50-ingestion-block05-v1.json `
  --max-new-chunks 200
```

Append `--live` to execute the frozen plan. The API key remains in the existing
environment variable, the diagnostic DSN is loaded in-process, and Docker must
already be running. This block produces no query or answer-quality measure.
