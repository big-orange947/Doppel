# Explicit one-attempt recovery observation

The stopped ten-history result is preserved in commit `f16148a`. The original arm
remains failed; this is a new recovery observation, not an uninterrupted run or
unopened sample. Commit this implementation/plan before paid execution.

## Fixed scope

- Same selected ten histories, complete source order, scope/event identities,
  reference Miner, evidence quarantine and deterministic consolidation.
- Same exact generation configuration as the failed parent: DeepSeek v4 flash,
  json_object, temperature 0, thinking disabled, output cap 8,192. No prompt change,
  increased output cap, case replacement, source truncation or relaxed evidence gate.
- One explicitly authorized attempt on the first pending extraction chunk. No
  automatic retry. Persist unknown/failed usage as unknown, never zero; include the
  original failed attempt in aggregate accounting.
- Copy the closed parent ingestion journal through SQLite backup to a fresh child
  directory. Do not copy/reset the usage ledger or edit the parent checkpoint/cache.
  Revalidate the completed prefix against the existing dedicated PG Store/index.
  Existing raw/derived records may receive normal idempotent validation/index
  maintenance; no database/volume reset, Graphiti write or unrelated data changes.
- A new one-call durable budget identity binds the recovery-plan fingerprint,
  separate from the original 482-call plan. Retain its successful output in the new
  cache. Reject a second execution of an attempted recovery directory, rather than
  silently re-bill it. Parent caches are read-only and must match bound inventory.
- Stop immediately after this observation. No retrieval, Reader/Judge, subset QA
  score or default algorithm change. Success means completion of the pending chunk,
  not proof of semantic quality or a proven cause of the earlier failure.

## Safe observability

The structured provider exposes a closed normalized finish-reason label on errors.
The runtime ledger records whitelisted error code, valid numeric HTTP status and
closed finish reason alongside request digest/usage. Arbitrary response content,
exception text, keys, transport headers and DSNs are never persisted. Unknown
errors keep `unknown_provider_failure`; legacy failed calls remain explicitly
without diagnostics. No finish reason is inferred retroactively from token count.

Additive diagnostic tables do not change provider requests or existing call rows.
The existing non-recovery ingestion API/budget is unchanged. The recovery budget
option requires a separately bound fingerprint and exactly one call/one new chunk.

## Bound inputs and outputs

Parent ingestion report SHA-256:
`48db227c90f8c908d26981fd630adbd5b2b0603260851def4ad99d6970a4ad2a`.
Parent journal SHA-256:
`e9004f24fcd9d3e3e83663b4f128ed910646191d4039732e57ffbbfd6af436b7`.
Parent cache inventory SHA-256:
`5ccba98c878f9ef45c0f6f2bf23dd49a8266917dacaf6d7123a055555b312e21`.
232 completed prefix chunks; pending write key:
`f36cf658b5f8f7feedfb230b9a8b9211841cf33a9acfd81f30a312f0c9b5badd`.

Recovery plan fingerprint:
`2613ff21946f7278fe8ab5be6335fcf91ed4307e891bb36a09543f04e3ab739a`.
Preflight output `data/doppel/longmemeval-recovery-observe-preflight-v1.json`, SHA-256
`2350376e4cccdd254e42dc855bfd8bd6632b9bd2f00e3e74ef5e5a3e9c853f47`.
Fresh run directory: `data/doppel/public-memory-recovery-observe-v1`.
All runtime artifacts are ignored and retain request/content bindings without
publishing personal source content. New preflight made no provider/database call.

```powershell
& D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_recovery `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-10-manifest-v1.json `
  --parent-report data/doppel/public-memory-expansion-10-v1/ingestion-live.json `
  --parent-report-sha256 48db227c90f8c908d26981fd630adbd5b2b0603260851def4ad99d6970a4ad2a `
  --parent-dir data/doppel/public-memory-expansion-10-v1/ingestion `
  --run-dir data/doppel/public-memory-recovery-observe-v1 `
  --output data/doppel/longmemeval-recovery-observe-live-v1.json `
  --embedding-cache-dir C:/Users/freeze/AppData/Local/Temp/fastembed_cache --live
```

The key comes only from the existing environment. If Docker is unavailable, stop
and ask the owner to open it manually; do not launch/reset Docker automatically.
After a successful observation, a separately bound continuation may resume the
remaining same-sample work while retaining this observation and all original costs.
After failure, inspect the new safe diagnostics before proposing any changed policy.
