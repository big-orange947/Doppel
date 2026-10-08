# Fifty-history expansion: third bounded ingestion block

The prior block's transport failure was resolved by a separate, successful,
single-call recovery observation. Its child checkpoint preserves the cloned130
completed chunks, validates the unchanged request as chunk131, and has a separate
one-call ledger. This block continues from that child. It does not alter or reuse
the failed block's paid budget.

## Frozen binding

- Dataset SHA-256: `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
- Manifest SHA-256: `28dc31edbcfc119d5f952d9f0ab3ceeaa123a5e9a5bfef70f82f9febbc120721`.
- Recovery report SHA-256: `4326244c9f8e5935073d632369f9c395caf25ddccf7c652ab0bf9ab95921f306`.
- Recovery prefix: 131 completed chunks;130 are inherited and one recovery call is
  recorded in the cloned namespace.
- Recovery Store audit: 2,003 source/provenance checks; zero failures.
- Plan fingerprint: `035d36f05bd2a03c5268ac858ceeac61450bf38b70a52bea569452d4bbc550d3`.
- Frozen plan: `data/doppel/public-memory-expansion-50-block02-recovery-v1/continuation-plan-035d36f05bd2.json`.
- Block cap: **200 new chunks / 200 calls**. There are 2,289 planned chunks left
  before this block. Retrieval and answer calls are zero.

The plan binds all SQLite/WAL/budget/plan files, the exact parent report, manifest,
dataset, source cache and code. Before the first paid call, the runner revalidates
the 131-chunk ordered prefix against the authoritative Store and vector index,
reconciling once per completed scope. It then proceeds through chunk330 at most.
Any provider failure consumes an attempt and stops; it is never silently retried.

Model, transport, output cap, Miner, source/evidence qualification and local
embedding remain those fixed for the selection: DeepSeek v4 flash, JSON object,
temperature0, thinking disabled, max completion8192 and local BGE-small-zh512.
No labels enter ingestion. A successful block remains partial and supplies the
next checkpoint for another explicit bounded plan.

Reproduce the no-provider preflight:

```powershell
D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_ingestion_continuation `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --parent-report data/doppel/longmemeval-expansion-50-block02-recovery-live-v1.json `
  --run-dir data/doppel/public-memory-expansion-50-block02-recovery-v1 `
  --output data/doppel/longmemeval-expansion-50-ingestion-block03-v1.json `
  --max-new-chunks 200
```

To execute this exact plan, add `--live`. Keep the API key in the existing
environment variable and the local DSN in-process. Docker must already be
running; if not, the owner opens it manually. This is ingestion only: it does not
produce an accuracy, recall, production Planner/Graphiti or AML result.
