# Runnable local Textual service

Status: repository-only experimental HTTP service. **Not deployed, submitted,
highest-config retrieval, a leaderboard score or an approved academic profile.**
The default backend is explicitly `bm25-raw-smoke-v1`: file-backed SQLite raw
history + the existing scoped BM25/attribution retrieval path. No LLM, embeddings,
graph building, miner, automatic fact confirmation or source-review calls happen
on add/search. This is a deployable transport baseline, not a quality upgrade.

By default authenticated `GET /healthz` and `GET /readyz` distinguish liveness from
backend/profile accessibility. Startup probes before listening; a failed readiness
probe returns503 without private exceptions. Explicit CLI request bounds and a
non-loopback opt-in guard are available. See the [operations runbook](aml-deployment.md)
for profile freeze, recovery/backup boundaries and remaining public-deployment work.
For AML-facing transport, `--public-health` optionally exposes only constant
liveness, while readiness/data routes stay authenticated; `--omit-search-scores`
avoids exporting pre-rerank scores as final relevance. Defaults remain unchanged.
After first startup, `--expected-profile-id` pins the observed journal/retrieval
identity and refuses mismatches before listening. See the runbook for boundaries.

## Local startup

From the repository root, install the optional server dependency into the chosen
environment. This command does not require changing an existing lockfile:

```powershell
uv pip install --python .venv/Scripts/python.exe -e ".[server]"
$env:DOPPEL_AML_BEARER_TOKEN = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
.\.venv\Scripts\python.exe -m integrations.aml.service --directory data/aml-local-smoke --namespace local-smoke-v1 --bind-owner-roles
```

Default listener:127.0.0.1:8000. No provider API keys are needed. Keep the generated
service token securely in the caller environment; do not commit it or confuse it
with a model API key. `--bind-owner-roles` explicitly declares that each incoming
user role is this scoped owner's utterance and assistant is historical assistant.
This binding is appropriate only when the host can actually vouch for it, not for
arbitrary IM group speakers. User IDs stay opaque, including whitespace; source
session IDs do not restrict the owner's cross-session recall.

Example request:

```powershell
$headers = @{Authorization = "Bearer $env:DOPPEL_AML_BEARER_TOKEN"}
$add = @{
    request_id = 'example-write-1'; user_id = 'example-owner'; session_id = 'example-chat'
    messages = @(@{role='user'; content='My telescope is with Morgan.'; timestamp=1704067200000})
} | ConvertTo-Json -Depth 6
Invoke-RestMethod http://127.0.0.1:8000/add -Method Post -Headers $headers -ContentType 'application/json' -Body $add
$search = @{user_id='example-owner'; query='telescope'; top_k=10} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/search -Method Post -Headers $headers -ContentType 'application/json' -Body $search
```

Optional timestamps are Unix milliseconds. Missing timestamps use the persisted
arrival clock for that write, stable on retries; that is observation time, not
an inferred occurrence date. Original content/role/session/order and source time
are embedded in attributed `content`, not only ignored response metadata.

## Persistence and errors

- State directory has separate `raw.sqlite3` and `service-journal.sqlite3` files.
  Namespace/role/strategy profile is bound to it; drift fails rather than resetting
  user data. Use a separate directory for another profile.
- Pending write marker is durable before source writes. Partial add returns no
  success; search and new adds for that scope fail503 until the same request is
  repaired. Retry reuses deterministic event identities, including after process
  death. Other users' completed histories remain independently scoped.
- A completed retry revalidates original sources; deleted/expired sources are not
  silently resurrected or claimed searchable. Same request ID with a changed
  payload returns409. Identical retry returns the original opaque ID echoes.
- 401 authentication;404 unknown route/method;413 size/message limit;422 malformed
  request/time/top_k;409 write conflict;503 pending/busy/timeout;500 redacted backend
  failure. Bodies do not echo private source text or provider exceptions.
- Default limits:2MB request body,1000 messages/add,1000 results requested,
  8 active requests/process,30-second cooperative async timeout. SQLite blocking
  I/O is not preemptible by this timeout; no hard latency SLA is claimed.

The journal serializes cooperating local writers, not a distributed fleet or
unrelated direct Store edits. SQLite/BM25 reads remain bounded by existing
retrieval read limits. Whole-message retrieval and lexical relevance are not
semantic retrieval or complete answer coverage. Search options are accepted by
the boundary but this raw smoke backend does not apply option-aware reasoning.

## High-config composition and remaining deployment work

`TextualASGI(TextualBoundary(your_backend, namespace=...), bearer_token=...)`
can wrap another `AMLBackend`. The transport never silently installs a lexical
fallback for it. That backend must independently prove durable/idempotent add,
index readiness, authoritative scope/source reload and immediate searchability.
The raw backend's receipt promises only its fresh Store-backed lexical path.

An explicit **local-hybrid** CLI profile now wires PostgreSQL authority, pgvector,
BM25/vector RRF60 and an offline cross-encoder through the same attributed path.
It is a raw-history retrieval profile, **not** the full structured-memory/time/
typed-graph configuration. A tiny live PostgreSQL/model acceptance now passes:
two real loopback TCP processes (initial+restart), existing local ONNX embedding,
CUDA-requested cross-encoder, two synthetic owners and6 source/vector records.
Offline tests separately use fake index/model boundaries. See the
[live acceptance report](../benchmarks/reports/aml-local-hybrid-live-2026-10-23.md).
Existing local50-case quality results are not measurements of this new service.
Do not claim the highest configuration. Model-profile compliance, hosting/TLS/reverse-proxy
limits, external access, benchmark credentials and actual official smoke remain
separate, unfinished acceptance steps. No public listener or paid hosting was
started by the local tests. Do not open this service publicly without deployment
review; the bearer token authenticates the adapter caller, not independent users.

### Explicit local-hybrid profile

Use an environment with `asyncpg`, `fastembed`, `sentence-transformers` and the
server extra installed. Reuse an existing compatible GPU environment if desired;
installing a new CUDA stack is not part of service startup. This profile never
downloads weights or invokes a paid LLM. Embedding is CPU-only small Chinese BGE;
the reranker device is explicit (`cpu` default, `cuda` opt-in). It is **not** the
text-embedding-v4 academic profile. Both model directories are content-fingerprinted.

```powershell
# Set the DSN in this shell using your existing PostgreSQL credentials.
# Do not commit it or paste it into reports.
$env:DOPPEL_AML_PG_DSN = 'postgresql://USER:PASSWORD@127.0.0.1:PORT/DATABASE'
.\.venv\Scripts\python.exe -m integrations.aml.service `
  --directory data/aml-local-hybrid --namespace local-hybrid-v1 --bind-owner-roles `
  --profile local-hybrid --pg-schema aml_local_hybrid_v1 `
  --embedding-model-path PATH_TO_EXISTING_BGE_SMALL_ZH_ONNX_DIRECTORY `
  --reranker-model-path D:\project\.doppel-eval-models\bge-reranker-v2-m3 `
  --reranker-device cpu
```

For the locked, opt-in retrieval/neural rank-fusion ordering, add
`--rerank-policy rank-fusion` to the **local-hybrid** command above, with a new
state directory. Omitting the flag (or passing `--rerank-policy bge`) preserves
the existing neural-only order **and its saved profile identity**. The flag is
rejected with `--profile bm25`, rather than silently ignored.

Rank fusion is a second ordering stage: BM25/vector RRF60 first produces the
fixed80 authorized candidates; the local BGE reranker orders all of them; equal
RRF60 combines that complete neural order with the original retrieval order.
Ties retain retrieval position. No weights/k tuning, category rules, role quotas,
extra LLM calls or graph building are introduced. Final evidence still reloads
from Store. Delegate errors, incomplete orders, changed source payloads and
unknown scoped IDs fail explicitly; there is no silent ranking fallback.

This option binds its policy/version/k/weights/candidate cap and delegate model
identity to the journal. Switching BGE↔fusion in the same directory is refused;
the original profile can still reopen it. Use a separate directory, and a new
dedicated schema for acceptance experiments; never reset an evaluation schema.
Readiness probes continue checking the underlying loaded models/vector profile,
without reranking or calling a provider. A larger `top_k` cannot enlarge80
candidates; use `top_k=20` for the evaluated output-count bound.

This exposes the evaluated **ordering component**, not the entire QA experiment:
the HTTP contract returns whole attributed source items and does **not** apply
the experiment's24,000-byte downstream context packing or Reader/Judge. A caller
must pack its own context. Model/index identity, raw-message chunking and client
packing can differ from the benchmark; do not label arbitrary HTTP requests as
reproductions of the opened50 or reserved10 QA scores. No default is promoted.

The embedding directory must be the **actual ONNX model directory**, not the
outer FastEmbed cache. Provision pgvector in the database first. Startup may
create the named schema/tables, but does not enable extensions, delete/reset
schemas or rebuild a graph. Use a new dedicated schema and state directory, not
an evaluation database/schema. Keep model files immutable while serving.

The journal binds namespace, roles, DB target fingerprint (no password), model
artifacts/package versions, reranker device and retrieval policy. Changed profile
refuses the old directory; no automatic migration or fallback. PostgreSQL owns
raw records and vectors; the local directory owns the durable source/write journal
and must also be retained/backed up. This is a single-host composition, not a
distributed service. It does not import any benchmark implementation.

Each add batches local embedding/index writes, then checks **every source's exact
scope, version and authoritative fingerprint** in the index before success. Failed
or interrupted indexing leaves the scope pending; same-request retry repairs it.
Completed-source retry is separately marked pending during index revalidation;
failure cannot turn it into a fresh ingest or resurrect deleted sources. Sources
are never promoted to owner facts. Search uses a fixed80-candidate fused window,
then content-only cross-encoder ordering and final Store/provenance reload. At
most80 snippets are returned even if a larger top_k is requested. A vector/model
failure is an error, not a silently relabeled BM25 success. Model token cap8192
and cumulative truncated-pair count are explicit on the local reranker object;
neither byte packing nor answer generation is added by this HTTP profile.

Local inference runs in worker threads; cancellation cannot preempt already
running ONNX/PyTorch work. Default HTTP timeout is not a hard compute deadline.
No real service throughput/latency or quality gain is claimed by fake-provider tests.

The opt-in `scripts.smoke_aml_local_hybrid` runner reproduces the real tiny smoke
with an **absent dedicated schema**, new state directory/output and existing
model paths; it reads only the PG DSN from the environment, creates an ephemeral
service token, strips API-key variables from children and binds loopback only.
It checks both real process lifetimes, exact attribution/timestamps, opaque-ID
isolation, cross-session evidence, idempotence/conflict/auth, source/vector counts
and six authoritative index fingerprints. The script deliberately retains its
small synthetic schema/journal, never deletes old data, and refuses overwrite.
It does not generate answers, judge50 cases, build graphs or certify performance.
Pass `--rerank-policy rank-fusion` to the smoke runner to exercise the new option;
it additionally verifies authenticated readiness/profile-ID stability, the saved
ordering identity and `top_k=1000` behavior across both process lifetimes.
The [fusion live acceptance report](../benchmarks/reports/aml-rank-fusion-live-2026-10-23.md)
records the actual new schema, model/policy identity, restart checks and limits.
The optional smoke switches `--public-health --omit-search-scores --pin-restart-profile`
check the AML-facing transport variant, formal `top_k=100` compatibility and a
pinned restart. Reports record effective switches/bounds and runtime versions;
they never store bearer tokens or provider keys. These local checks do not
request an official AML Smoke or certify academic-model compliance.

Run interface/restart tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_aml_service.py tests/test_aml_retrieval_profile.py tests/test_aml_contract.py tests/test_aml_ingestion.py tests/test_aml_evidence.py tests/test_aml_evidence_representation.py -q
```

The service tests use real temporary SQLite databases and HTTP serialization.
With the server extra installed, one test also starts a loopback TCP child,
terminates it and restarts on the same files; without it that test is skipped,
not claimed as passed network coverage. All fixtures are synthetic, with no LLM
requests, personal production database or Docker restart involved.
