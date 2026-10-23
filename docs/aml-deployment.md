# Local service operations and deployment boundary

This is a repository-only, single-host experimental adapter. Local HTTP, durable
restart and tiny PG/local-model tests pass; no public deployment, official smoke,
academic-model compliance, multi-worker support or production SLA is established.
Start with [the service guide](aml-service.md). This runbook does not authorize a
cloud purchase or opening a public port.

## Freeze before serving

Record the Git commit, selected Python environment/package versions, namespace,
state directory, PostgreSQL database/schema, local model artifact fingerprints,
device and request bounds. Choose the profile explicitly:

- `--profile bm25`: SQLite/BM25 transport smoke, no semantic retrieval.
- `--profile local-hybrid`: PG/pgvector + BM25/RRF60 + offline neural reranker.
  This is raw history, not the full temporal/typed-graph engine or text-embedding-v4.
  Optional `--rerank-policy rank-fusion` combines retrieval/neural orders with
  locked equal RRF60; omit it for the unchanged BGE-only default. Record this
  choice: switching policies refuses the same journal directory. Neither option
  installs downstream24KB context packing or generates answers.

Use the same directory and namespace after restart. Do not switch profiles or
model files in place. Keep journal and authoritative DB backups consistent; a DB
alone does not contain this adapter's complete write/source mapping. Never point
an operational service at a protected benchmark schema. Do not copy bearer tokens,
provider keys or DSNs into tracked config, command-line arguments, logs or reports.

PG connection URI must explicitly name host, username and database; only `sslmode`
is accepted as a query parameter. Host/user/database/password query overrides,
duplicate sslmode, multi-host and implicit targets are rejected before model/DB
initialization. DB-target fingerprints exclude password and TLS mode; credential
rotation does not change the authority, while schema/database/user changes do.
Percent-encoded usernames/database names are normalized, so an older directory
bound using an encoded URI may refuse the new canonical identity; it is **not**
automatically migrated. The existing ASCII-URI local smoke directory is compatible.

## Startup bounds

Defaults are unchanged: loopback127.0.0.1:8000,2MB body,1000 messages/add,
1000 requested results,8 active requests and30-second cooperative timeout.
`local-hybrid` still has a fixed80-candidate window and returns at most80 snippets.

Explicit CLI overrides:

```text
--request-timeout-seconds 30
--max-concurrency 8
--max-body-bytes 2000000
--max-messages 1000
--max-results 1000
```

Limits must be positive/finite; message/result caps may be lowered, not increased
beyond1000. Invalid bounds/port and invalid bearer-token bytes fail before opening
state files or loading models. Tokens must be visible ASCII without whitespace.
Non-loopback binds additionally require `--allow-remote-bind` and a token of at
least32 characters. This guard is **not TLS or a deployment approval**. Uvicorn
does not trust forwarded headers in this CLI. No access logs are enabled.

One process per state directory is the verified operating pattern. A long model
call serializes the raw backend;8 admitted requests is not8 parallel GPU queries.
Threaded ONNX/PyTorch work cannot be preempted by an async request timeout.
Do not raise limits as a substitute for a measured deployment workload.

## Liveness and readiness

All routes, including probes, require the same bearer token:

```powershell
$headers = @{Authorization = "Bearer $env:DOPPEL_AML_BEARER_TOKEN"}
Invoke-RestMethod http://127.0.0.1:8000/healthz -Headers $headers
Invoke-RestMethod http://127.0.0.1:8000/readyz -Headers $headers
```

- `GET /healthz`:200 `{"status":"alive"}` if the event loop can respond. It does
  not contact dependencies and remains available when request capacity is full.
- `GET /readyz`:200 `{"status":"ready","profile_id":"..."}` only after the
  configured backend probe passes,503 otherwise; probe deadline is at most5s.
  Pin the opaque profile_id with the deployment so a different runtime profile
  is detectable. It covers the journal namespace/roles/retrieval/storage/model
  binding, not token rotation, transport limits, SSL mode or every runtime package.
  Record those settings separately. This is not a content hash of user histories.
- Wrong/missing credentials:401. Wrong method/path:404. Failed readiness returns
  only a generic error, not source data, DB identifiers, DSNs or exception text.

CLI startup performs the backend probe **before listening**. The probe checks
journal access, an exact-scope Store point read, and (for local-hybrid) existing
vector-table access/columns, exact vector-profile metadata and loaded model
objects. It performs **no history scan, vector counts, embedding, reranking or
answer generation**. Model startup warmup remains separate and runs once.
An injected custom backend without an explicit readiness probe is not called ready.

Readiness means dependency/profile accessibility, **not** complete indexing of all
users, QA correctness, safe public exposure or ability to allocate a future large
GPU request. A scope with an unfinished write still fails its own add/search503;
it does not mark every other user's history unavailable. Capacity/lock contention
can temporarily fail readiness. Liveness is not proof that the DB is healthy.

## Failure and recovery

For409, fix the caller's reused request ID/payload rather than retrying modified
content under that ID. For a partially completed add, preserve the exact request
and retry it; do not delete journal rows, reset schema or re-import all history.
Check readiness/connectivity when receiving503. An unprobed custom configuration
also returns503. Unexpected add/search errors remain redacted500; no automatic
lexical fallback or paid retry is installed. Restart with the same immutable
profile and files, then check readiness and a synthetic authenticated search.

For backup, stop traffic and the process, then back up both PG and the local
journal (plus raw.sqlite3 for BM25). Do not copy live WAL files piecemeal. Restore
as a matched pair under the same profile; a general live-backup/DR procedure has
not been certified. Do not delete old data to make a profile mismatch disappear.

## Before any public deployment

Still needed: an agreed host, persistent storage/model paths, private DB access,
TLS reverse proxy, caller-secret provisioning/rotation, request/body/time limits
at the edge, startup grace for model loading, backup/restore rehearsal and the
actual evaluation client's reachability/contract test. Keep the service bound to
loopback behind the proxy where possible. A bearer token authenticates the
adapter caller, **not** independent end users who can choose arbitrary user_ids.
Never expose it as a public multi-user API without a separate authorization layer.

Only the local Windows environment has been exercised for this adapter; this
work does not certify a Linux image, GPU driver stack, public endpoint or latency.
Do not claim an official submission, highest configuration or a new QA score from
these operational checks.
