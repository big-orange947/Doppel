# Fifty-history expansion: second bounded ingestion block

The first94 chunks from two complete histories are preserved in the frozen
[block01 result](public-memory-expansion-50-ingestion-block01-result-2026-10-08.md).
This continuation validates the exact completed prefix, source, durable ledger,
PostgreSQL provenance audit, model settings and provider-cache inventory before
it reserves any new call. The normal per-scope recovery path revalidates source
events and reconciles the index once for each completed scope.

## Frozen inputs and bound

- Dataset SHA-256: `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
- Selection manifest SHA-256: `28dc31edbcfc119d5f952d9f0ab3ceeaa123a5e9a5bfef70f82f9febbc120721`.
- Parent report SHA-256: `736b7f7f2fdf0ae30e0511443368768370ffe89f3a8c2289538397a238dc1cbf`.
- Parent ingestion plan fingerprint: `03134787d46171f0109d6e9770b68ed9f84f1d0a9d45d23aa4c9eaf32a0ba458`.
- Parent prefix: 94/2,420 exact ordered chunks, 94 successful durable attempts.
- Parent PostgreSQL Store audit: 1,404 provenance checks, zero failures.
- Continuation plan fingerprint: `5b60c74a4922667f42a72af7f5086fedd4ed6cf64e75068997d33e822fadbd8c`.
- Frozen plan: `data/doppel/public-memory-expansion-50-v1/continuation-plan-5b60c74a4922.json`.
- This block: at most **200 new chunks and 200 new calls**, with a separate ledger
  identity. No QA or retrieval calls are permitted in this stage.

The200-attempt boundary is set before the live run. Source, model and miner
configuration match the original frozen ingestion plan: DeepSeek v4 flash,
JSON-object responses, temperature0, thinking disabled, max completion8192,
local BGE-small-zh512, production Analyzer/Miner/consolidator and evidence
qualification. The call cap bounds attempts, not exact token billing. Failure
consumes its attempt and stops the block; there is no automatic retry, case
replacement or cap increase.

The continuation uses the existing diagnostic PostgreSQL schema and journal.
Every completed prefix key must be the exact ordered prefix, and its raw source
and vector index are revalidated before new extraction. Each continuation budget
has a distinct durable file/identity so later explicitly frozen blocks can append
without replacing previous accounting. Earlier journal, cache and output remain
available; the source dataset and `uv.lock` are not edited.

At freeze time, Docker's diagnostic PostgreSQL container is healthy. The runner
reads the local DSN in-process and reads the DeepSeek key only from the existing
environment variable; neither value is emitted or persisted. If Docker becomes
unavailable, stop and ask the owner to open it manually.

## Reproduction

First, reproduce the plan without a provider call:

```powershell
D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_ingestion_continuation `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --parent-report data/doppel/longmemeval-expansion-50-ingestion-block01-v1.json `
  --run-dir data/doppel/public-memory-expansion-50-v1 `
  --output data/doppel/longmemeval-expansion-50-ingestion-block02-v1.json `
  --max-new-chunks 200
```

Then execute the same frozen block by adding `--live`. The output report path is
new and exclusive. The block ends after200 new chunks or earlier on a recorded
failure. Its status remains partial until all2,420 source chunks are complete;
this stage produces no retrieval, Reader, Judge, quality or AML score.

## Next stage

After this block, check the report and freeze the next bounded continuation against
its exact new checkpoint. Do not automatically spend the remaining extraction
budget. Once all fifty histories are ingested, freeze and run the three-channel
retrieval and answer harness as specified in the first expansion plan.
