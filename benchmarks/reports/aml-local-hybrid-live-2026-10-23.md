# Real local-hybrid service smoke: initial and restart pass

Runtime implementation commit **cf1a90d** on master. This is a tiny integration
acceptance, not a new QA score, independent benchmark, full structured high-config,
scalability/latency result, AML submission or compliant academic-model profile.
No core algorithm was changed in this round.

## Real execution

The user manually opened Docker. Non-mutating checks found healthy existing
`doppel-ablation-pgvector` and Neo4j; PG connection and vector0.8.6 passed. Neo4j
and the unrelated running Qdrant were not used or modified. The dedicated target
schema did not exist before the run; no evaluation schema was reused/reset.

Used the existing `D:/project/.doppel-eval-cu128/Scripts/python.exe` environment:
fastembed0.8.0, sentence-transformers6.0.1, torch2.7.1+cu128, asyncpg0.31.0,
uvicorn0.50.0. Embedding: existing local BGE-small-zh-v1.5 optimized ONNX,512d,
CPU. Reranker: existing local BGE-reranker-v2-m3 directory, explicit device `cuda`,
8192-token cap, batch1. No CPU fallback is configured; actual GPU device/peak memory
was not independently instrumented in the child. No weights were downloaded.

The smoke runner starts the actual repository CLI/uvicorn service twice on a
random loopback port. It terminates the first process, then starts a new process
against the same files/schema. Each child has API-key environment variables
removed and offline model flags set. DB credentials stay in process environment,
not command arguments, report, source or journal profile; service bearer token
is generated in memory and not persisted. **Paid calls0**; no LLM provider is used.

## Strict checks passed

- Three add requests, six raw messages, two distinct owners, three sessions.
- Same-owner cross-session query returns all4 original owner/assistant sources.
- Query `optical instrument` has no literal match in the synthetic sources;
  real semantic search contributes candidates through production BM25/vector RRF60.
  Neural ordering runs on original authorized text, without injected answer keys.
- Every source text, transport role, owner/historical-assistant label, actor,
  authority and exact Unix-millisecond-derived source timestamp matches input.
- OwnerA receives none of ownerB's sources; ownerB receives only its2 messages.
  Whitespace-trimmed ownerA ID is a different opaque principal and sees no data.
- Identical add retries succeed; changed same-ID payload returns409;
  wrong service bearer token returns401.
- After process termination/restart: IDs, source content, attribution, order and
  returned scores are identical; retry does not duplicate records.
- After both processes exit: PostgreSQL has exactly6 source records and6 vector
  rows; every one of6 catalog entries matches authoritative scope, version and
  full record fingerprint; local journal has no unfinished write.

Both old and new telescope messages remain attributed historical evidence. This
does **not** test temporal selection, infer who currently holds it, or generate an
answer; timestamps surviving transport is not proof of temporal QA correctness.

## Observed timings, not a benchmark

| Process | Startup including readiness | Search plus subsequent smoke checks |
|---|---:|---:|
|initial|83.265s|1.047s|
|restart|21.734s|0.235s|

First cold startup is long. Model/library initialization and first inference are
included, and another regression process ran concurrently. The check durations
cover multiple HTTP assertions, not isolated single-query latency. No p50/p95,
throughput, idle-GPU stability or production SLA follows from these observations.

## Artifacts and retention

- Runner: `scripts/smoke_aml_local_hybrid.py`.
- Runner file SHA-256:156dc77cd909eb6272b133087c4830876ca02469c45bcbcefdfd5291957f59a0.
- Local report: `data/doppel/aml-local-hybrid-live-smoke-20261023.json`.
- Report file SHA-256:4efd5e16eda5de97fe689914e48e683a207b8222f9d8f6261e9ab62c7ac7600c.
- Search-results canonical hash:896cb27bf7e24578e929b80048b8348db795ff66558574de0d72c2bb74f2bccc.
- Dedicated schema: `aml_local_hybrid_smoke_20261023`.
- State directory: `data/aml-local-hybrid-live-smoke-20261023`.
- Vector identity: `pgvector:dplv_69f382ac9fc73401`.

Six synthetic source/vector fixtures and the journal are intentionally retained
for inspection. Existing volumes, schema histories, graph, source caches and
frozen QA receipts were not changed. Both temporary TCP servers are stopped;
no service is publicly deployed. Existing uv.lock was not modified/staged.

Post-run inspection found no remaining service child process. Docker containers
remain healthy. A byte scan of the retained report/journal found no database
password; report has no DSN field. No live credentials are in committed files.

Eight offline validator tests verify acceptance of complete/reordered sources and
rejection of missing/duplicate, other-owner text, actor/authority reversal, wrong
timestamp and rewritten source. Repository Ruff clean; smoke/service modules
Pyright0 errors/warnings. Full regression: **2195 passed,33 skipped,3 subtests**,
219.03s, one existing optional Graphiti/Pydantic deprecation warning. The33 skips
are not live-PG coverage; the real six-record smoke above is a separate run.

The opened50 QA baseline remains **37/50**, unchanged. Next delivery work is
deployment/profile freeze and remaining submission/model-access acceptance,
not another eager full-history graph build or a claim this smoke improved QA.
