# Fifty-history expansion: blocks13–14 result and final block15 freeze

## Block13 result

- Parent checkpoint:1,954 chunks; all1,954 revalidated before new calls.
- New work:200/200 chunks completed; report status `partial` because the cap was reached.
- Cumulative progress:2,154/2,420 chunks.
- Calls/tokens:200 successful calls,1,010,710 reported tokens.
- Result: `data/doppel/longmemeval-expansion-50-ingestion-block13-v1.json` (SHA-256 `6e9db8d6a2ded739baa1e483e8efab3fc049cf5d7be25a02b6fe8a0c15a47559`).
- Provenance failures:0. No retrieval or QA metrics ran.

## Block14 result

- Parent checkpoint:2,154 chunks; all2,154 revalidated before new calls.
- New work:200/200 chunks completed; report status `partial` because the cap was reached.
- Cumulative progress:2,354/2,420 chunks across 49 histories (48 complete, one partial, one untouched).
- Calls/tokens:200 successful calls,1,033,623 reported tokens.
- Store audit:24,233 raw records,9,480 derived records (including inactive),120 governance records;36,443 provenance checks, zero failures.
- No retrieval, Reader, Judge, QA, or quality metrics ran. This is ingestion-only progress.
- The report explicitly records `semantic_truth_verified=false`, `publication_ready=false`, and `aml_academic_model_compliant=false`.
- Result: `data/doppel/longmemeval-expansion-50-ingestion-block14-v1.json` (SHA-256 `feb51ab22604722f46b62ee96aad8055a913f98993dc90efdbad81b5b30de5da`).

## Final block15 frozen plan

- Parent report SHA-256: `feb51ab22604722f46b62ee96aad8055a913f98993dc90efdbad81b5b30de5da`.
- Parent checkpoint:2,354 chunks; 353 inherited,2,001 successful child-local attempts.
- Remaining source chunks:66; final block bound is exactly66 chunks / 66 calls.
- Zero retrieval, Reader, Judge, or QA calls.
- Plan fingerprint: `47b3a3ac54c1b307019ce251fa9cf07254553b7b7a926d50041e015f98447d36`.
- Frozen plan file: `data/doppel/public-memory-expansion-50-block04-recovery-v1/continuation-plan-47b3a3ac54c1.json`.
- Intended output: `data/doppel/longmemeval-expansion-50-ingestion-block15-v1.json`.

Any transport failure stops this final block and must be handled with a
separately frozen recovery plan. Do not increase the budget or automatically
retry.

## Reproduction

```powershell
D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_ingestion_continuation `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --parent-report data/doppel/longmemeval-expansion-50-ingestion-block14-v1.json `
  --run-dir data/doppel/public-memory-expansion-50-block04-recovery-v1 `
  --output data/doppel/longmemeval-expansion-50-ingestion-block15-v1.json `
  --max-new-chunks 66
```

Append `--live` only to execute. The API key remains in the existing process
environment; Docker must already be running. Do not alter the unrelated dirty
`uv.lock`.
