# AML-facing transport: local contract and pinned-restart acceptance

Runtime commit: **7044b79251efcfa162c70c26448de5b29e976dad**. This is a local
operational check, not an official AML Smoke, public deployment, model-compliance
approval, new QA score or full structured-memory/Graphiti evaluation.

## Contract review and explicit switches

The [official API guide](https://agentmemoryleaderboard.ai/api-guide), rechecked
2026-10-23, specifies unauthenticated GET health, formal Search top_k100 as an
upper bound and optional relevance scores. The previous default authenticated
health and post-rerank original scores needed an explicit AML-facing variant.

- `--public-health`: only exact GET `/healthz` bypasses bearer authentication,
  returning constant liveness. Ready/add/search stay protected. Wrong credentials
  also receive only this constant health response, never private readiness/data.
- `--omit-search-scores`: omit optional wire item scores, not internal scores or
  source content. Preserve IDs, attribution, timestamps and existing order. This
  avoids exporting pre-rerank similarity as final-order relevance. No reranking,
  inference or new evidence is introduced by the projection.
- `--expected-profile-id`: malformed pins fail before opening state; valid but
  mismatched pins close the backend and fail before server construction/listen.
  Model/schema initialization may already have run. No reset/migration occurs.

All options are explicit. Existing auth/score defaults and retrieval identities
remain unchanged. The opaque profile pin does not cover transport switches,
listener, bounds, token, TLS proxy or every runtime package; record those
separately. The smoke report now records its switches/bounds and package versions.

## Real loopback/PG/model execution

Used an absent dedicated schema `aml_contract_smoke_20261023`, new state directory
`data/aml-service-contract-live-20261023`, and the existing healthy PostgreSQL
container. No Docker restart, schema/volume reset, old-history mutation or graph
operation. Six synthetic sources/vectors are retained for inspection.

The actual CLI/uvicorn ran twice on a random loopback port: first startup, then
termination and a new process with the observed expected-profile pin. Both used
local-hybrid, rank-fusion, public health and omitted scores. Passed:

- No-credential health200; no-credential readiness401 and wrong-token Search401.
- Three durable adds; exact opaque ID echoes; duplicate retries with no duplicate
  rows; conflicting payload409. Formal top_k100 and larger1000 return the same
  four authorized ownerA sources as top_k10, without padding or cap errors.
- Two owners and three sessions; ownerA sees none of ownerB's sources, ownerB
  sees only its two; whitespace-trimmed ownerA ID does not grant access.
- All original source text, actor/authority, role, session/turn and source time
  match input. No item score is serialized. Restart preserves IDs/content/order.
- Readiness profile ID stays identical and matches the actual saved journal
  profile. All6 vector entries match authoritative scope/version/fingerprint;
  exactly6 raw rows,6 vector rows and no unfinished writes.

Python3.12.7/win32; fastembed0.8.0, sentence-transformers6.0.1,
torch2.7.1+cu128, asyncpg0.31.0, uvicorn0.50.0. Reused local512d BGE-small-zh
ONNX CPU embedding and BGE-reranker-v2-m3 with explicit cuda, cap8192/batch1.
No independent device/peak-memory instrumentation. API-key variables removed
from runner/children; model downloads disabled; **paid provider calls0**.

Startup including readiness:17.719s initial/17.984s restart. Search and following
checks:0.812s/0.515s. These cover multiple requests while regression ran concurrently,
not isolated latency or idle-GPU p50/p95. Both temporary servers are stopped.
Credentials and the ephemeral bearer token were not persisted in receipts/config;
report/saved-profile scans found no database password, DSN or Authorization field.

## Receipts, verification and remaining boundary

- Report: `data/doppel/aml-service-contract-live-20261023.json`.
- Report SHA-256: `56c4568d9ebf8974d107e268a363c04c50e4962725a03a9483f6c8b6719eb2d6`.
- Runner file SHA-256: `f47877f7f93a756c88f2b3fa576e4821aecdd687938d8ad0860d35c502bbcd06`.
- Response canonical SHA-256: `38cd59ba045b625c7b82a84a9013171e75baee06c423097f21d394ea83f7dabe`.
- Profile ID: `da4d55f499682b95e9f837fc5aca294551a43931d76b094cb96d5dd30ac14597`.

Focused108 tests passed; final full regression **2370 passed,33 skipped,3 subtests**,
231.84s, one existing optional Graphiti/Pydantic deprecation warning. Both default
and opted-in real SQLite TCP restart tests pass. Offline tests also cover pin
mismatch before listening with backend closure, invalid pin before state creation,
strict switches and lossless score-only omission. Ruff clean, changed runtime/
runner Pyright0 errors/warnings, formatting clean. Existing uv.lock remains unstaged.

No new QA measurement: opened50 fusion40/50 and reserved10 9/10 remain separate
small-sample provisional results. Local BGE is not the academic embedding model.
The user selected **Alibaba Cloud** for the next text-embedding-v4 integration;
implement/validate that separately with a distinct vector identity, not an in-place
overwrite of BGE indexes. Hosting/TLS/external reachability, official credentials/
Smoke and any formal submission still require separate acceptance and authority.
