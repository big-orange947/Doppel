# Committed-memory Graphiti backfill: bounded smoke

Frozen before any live graph-provider request. This is index integration, not an
answer benchmark or AML score.

## Inputs and selection

Reuse the completed fifty-history Store (`public_memory_03134787d461`), unchanged
manifest and existing local BGE-small-zh-v1.5 / FastEmbed 0.8.0 / 512-dimensional
embedding profile. Store snapshot: `11aab45f1bdfaebeea23bee822e53e5cdd94aef24f68bb020d90e9eda35e9cc3`.

There are 9,744 confirmed eligible owner/agent personal memories. Select the first
three using ingestion-scope order, then `created_at`, then `memory_id`. No question,
answer, required-evidence label, query result or domain rule enters selection or
graph generation. Source histories, memories and vectors are not regenerated.

## Production path and limits

Invoke `GraphitiSemanticIndex.index_record` with real Graphiti 0.29 and the existing
Neo4j. Do not preseed graph facts or use the earlier ablation fixture writer.
Use DeepSeek v4 flash chat/completions, JSON-object schema injection, temperature
zero, thinking disabled, per-request output cap 8,192 (respect smaller requested
limits). Override Graphiti's default Responses/retry path with a structured-model
bridge and the existing durable SQLite attempt ledger/content-addressed cache.

Maximum 48 provider attempts across resumptions, 500,000 canonical bytes per request,
8,000,000 total canonical request bytes. No automatic retries or budget extensions;
unknown usage remains unknown. This bounds attempts and canonical input bytes, not
exact billing or tokens. Concurrent Graphiti extraction uses one coroutine, and an
OS file lock prevents simultaneous writers in the same run directory. Disable
Graphiti telemetry. Keys/credentials remain in process and never enter plans/caches.

Persist the complete frozen plan and per-record fingerprint/checkpoint. A successful
record must have matching Episode metadata/version and actual Episode-linked graph
edges. A restarted run rechecks completed projections and skips them without calls.
Repair only a previously started deterministic slot owned by this run; refuse to
overwrite unowned or changed completed projections. Retain completed graph data.

## Reporting and follow-up

Report new index writes, exact completed memory IDs, Episode/edge checks, rich versus
fallback participation, ledger attempts/usage/cache counts and unchanged Store hash.
A three-record smoke never certifies coverage of all 9,744 memories or any answer
accuracy. Preserve failures and caches; no selective reseeding to obtain success.

After smoke, verify no-call resumption and production relation retrieval against the
materialized graph. Then expand the same source-only prefix in separately budgeted,
frozen runs. Reuse existing complete projections rather than paying for them again.

Preflight artifact: `data/doppel/public-memory-graph-smoke-preflight-v1.json`.
Run directory: `data/doppel/public-memory-graph-smoke-v1`.
Offline verification before live: 69 focused tests pass; Pyright with the actual
venv reports zero errors for the new transport and backfill modules.
