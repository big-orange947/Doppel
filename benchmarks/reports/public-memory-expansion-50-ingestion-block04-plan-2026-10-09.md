# Fifty-history expansion: fourth bounded ingestion block

Continue from the preserved block03 report and the recovered child journal. The
runner verifies the exact dataset/manifest/report, all SQLite/WAL/budget/plan
checkpoint files, provider-cache inventory and ordered completed-source prefix.
It revalidates all331 completed chunks and reconciles the source/index state once
per scope before any new extraction call.

## Frozen binding

- Dataset SHA-256: `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
- Manifest SHA-256: `28dc31edbcfc119d5f952d9f0ab3ceeaa123a5e9a5bfef70f82f9febbc120721`.
- Parent report SHA-256: `6e969585d41465798a66dfbedb057708370cdeda00d276addffe1ea75e1e4f06`.
- Prefix:331 completed chunks, of which130 are inherited from the recovery clone;
  201 successful durable local attempts are in the continuation database.
- Parent Store audit:5,084 provenance checks, zero failures.
- Plan fingerprint: `cdefcd7842432228de7fb8d356eae7469dcf2bab3bd2678c6fcc5b2b0ab781d6`.
- Frozen plan: `data/doppel/public-memory-expansion-50-block02-recovery-v1/continuation-plan-cdefcd784243.json`.
- New call/chunk cap: **200**. The selection has2,089 chunks remaining before
  this block; this run will stop at531 total chunks unless a failure stops earlier.
- QA, retrieval and Reader/Judge call cap: **zero**.

The model and extraction configuration remain unchanged: DeepSeek v4 flash,
JSON object, temperature0, thinking disabled, completion cap8192, production
Analyzer/Miner/consolidator and evidence gates, local BGE-small-zh512. A failed
attempt consumes budget and halts; no automatic retry or case replacement.

Run preflight without a provider call:

```powershell
D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_ingestion_continuation `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --parent-report data/doppel/longmemeval-expansion-50-ingestion-block03-v1.json `
  --run-dir data/doppel/public-memory-expansion-50-block02-recovery-v1 `
  --output data/doppel/longmemeval-expansion-50-ingestion-block04-v1.json `
  --max-new-chunks 200
```

Add `--live` to execute this plan. The owner opens Docker manually if needed;
keys remain in the environment and the DSN is read in-process. No benchmark QA
score is produced by this ingestion stage.
