# Runnable local Textual service

Status: repository-only experimental HTTP service. **Not deployed, submitted,
highest-config retrieval, a leaderboard score or an approved academic profile.**
The shipped backend is explicitly `bm25-raw-smoke-v1`: file-backed SQLite raw
history + the existing scoped BM25/attribution retrieval path. No LLM, embeddings,
graph building, miner, automatic fact confirmation or source-review calls happen
on add/search. This is a deployable transport baseline, not a quality upgrade.

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

High-config vector/reranker/optional typed-graph composition is **not wired into
this CLI**. Existing local50-case quality results are not measurements of this
new HTTP smoke profile. Do not point an official evaluation at it while claiming
the highest configuration. Model-profile compliance, hosting/TLS/reverse-proxy
limits, external access, benchmark credentials and actual official smoke remain
separate, unfinished acceptance steps. No public listener or paid hosting was
started by the local tests. Do not open this service publicly without deployment
review; the bearer token authenticates the adapter caller, not independent users.

Run interface/restart tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_aml_service.py tests/test_aml_contract.py tests/test_aml_ingestion.py tests/test_aml_evidence.py tests/test_aml_evidence_representation.py -q
```

The service tests use real temporary SQLite databases and HTTP serialization.
With the server extra installed, one test also starts a loopback TCP child,
terminates it and restarts on the same files; without it that test is skipped,
not claimed as passed network coverage. All fixtures are synthetic, with no LLM
requests, personal production database or Docker restart involved.
