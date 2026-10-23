# Opt-in rank-fusion service: real local acceptance

Runtime implementation: **6c81109ad1d22c70455737b2de55a074296892c3** on master.
This is operational acceptance of the selected ordering component, not another
QA experiment, independent quality verification, AML score, public deployment,
academic-model compliance or full structured-memory/Graphiti configuration.

## Delivered composition

`integrations.aml.service --profile local-hybrid --rerank-policy rank-fusion`
now selects the existing production `RankFusionReranker`. PostgreSQL authority,
pgvector and BM25 first produce at most80 scoped candidates using equal RRF60.
The local cross-encoder returns the complete authorized ordering; a second
equal RRF60 fuses retrieval and neural positions, with retrieval-position ties.
No tuned weights, question-specific rules or new model calls are introduced.

The default remains BGE-only, with its previous persisted identity unchanged.
The explicit fusion identity binds algorithm version, k60, equal weights,
candidate cap80 and underlying model artifacts/package/device to the journal.
Changing either direction in the same directory fails; the original policy can
reopen it. Passing a rerank policy with the BM25-only CLI is rejected.

The context retriever caps a delegate's requested output count to its fixed
candidate window; `top_k=1000` cannot exceed80 or cause the bounded fusion
delegate to reject an otherwise valid HTTP request. The delegate still receives
all authorized candidates even for `top_k=1`. Invalid or forged delegate output
fails explicitly rather than becoming an undocumented fallback.

The HTTP interface does **not** add the QA experiment's24,000-byte packing,
Reader/Judge or chunking. `top_k=20` selects an output-count bound, not byte-budget
equivalence. This adapter's content-fingerprinted model/index identity also
differs from benchmark-specific identities. The previous opened50 **40/50** and
locked reserved10 **9/10** remain separate, provisional small-sample results;
neither is remeasured by six synthetic records.

## Real execution and data protection

The already running PostgreSQL container was healthy. No Docker startup/restart,
extension installation, schema reset, graph operation or volume deletion occurred.
The runner required an absent schema and new state directory/output. Existing
evaluation schemas, default-profile smoke fixtures, histories and QA caches were
not reused or changed. Dedicated schema: `aml_rank_fusion_smoke_20261023`.
State directory: `data/aml-rank-fusion-live-smoke-20261023`.

Used existing `D:/project/.doppel-eval-cu128/Scripts/python.exe`, local512d
BGE-small-zh-v1.5 ONNX embedding on CPU, local BGE-reranker-v2-m3 with explicit
`cuda`, max8192 tokens/batch1. As in the original smoke, no independent device or
peak-memory instrumentation was added. Model downloads were disabled in child
processes. API-key environment variables were removed before the run and from
children. **Paid calls0**; no Reader, Judge, provider or Graphiti was invoked.

The existing local container's credentials were used only in the runner/service
environment, never command arguments, reports or tracked files. An ephemeral
service bearer token was generated in memory. A post-run scan found no database
password, DSN or Authorization field in the report or saved profile.

## Passed over actual TCP, twice

The runner launched the real CLI/uvicorn service on a random loopback port,
terminated that process, then started another against the same retained state.

- Three writes, three sessions, two owners, six source records/vector rows.
- Same-owner cross-session semantic query `optical instrument` returned all4
  original owner/assistant sources without a literal query match in their text.
- Every returned source's text, transport role, owner/historical-assistant label,
  actor, authority, session/turn identity and exact source timestamp matched input.
- OwnerA never received ownerB's two sources; ownerB received only its own two.
  Trimming whitespace from the opaque ownerA ID did not confer access.
- Identical add retries succeeded without duplicate records. Changed payload
  under an existing request ID returned409. Invalid bearer token returned401.
- Authenticated health/readiness passed. Profile ID stayed identical after
  restart, and matched the hash of the actual saved journal profile.
- Saved reranker identity identified `retrieval-neural-rrf-v1`, k60, cap80 and
  the local BGE delegate, not merely a requested CLI flag.
- `top_k=1000` returned the same four results as `top_k=10`, without errors.
- Original and restarted responses matched IDs, content, attribution, order and
  similarity scores. All6 index entries matched exact Store scope, source
  version and fingerprint. No unfinished journal writes remained.

The synthetic telescope history includes an older/newer location, but this smoke
does not choose the current location or test temporal QA. Timestamp preservation
is transport acceptance, not temporal-reasoning accuracy.

## Observations and receipts

| Process | Startup including warmup/readiness | Search and subsequent checks |
|---|---:|---:|
|initial|25.875s|0.797s|
|restart|23.765s|0.484s|

The check durations cover multiple requests, not isolated query latency. A full
regression ran concurrently; no idle-GPU p50/p95, throughput or SLA is claimed.

- Local report: `data/doppel/aml-rank-fusion-live-smoke-20261023.json`.
- Report SHA-256: `dbdb9e800e8c558f62558f5b31a60631e181c11ac71b34f9b8e8c3af0537d307`.
- Runner: `scripts/smoke_aml_local_hybrid.py`.
- Runner file SHA-256: `c42ccab16a72d9ec4a67d731936fec3d5933282a51d5483e3687c248b7dce085`.
- Response canonical SHA-256: `6be8aa63f91eb0de99e74cd3a0fc0aa23fa67dbe3763dc80346d364e2b350ccc`.
- Opaque service profile ID: `ff74e7432a97c50f6114339c9eabe05abda7f0f99db9df6b1b7b44c3c2e40f61`.
- Vector identity: `pgvector:dplv_69f382ac9fc73401`.

Six synthetic source/vector rows and their journal are intentionally retained.
Both temporary servers are stopped; no service is publicly listening. Existing
uv.lock remains a preexisting unstaged modification, not part of this delivery.

## Offline checks and next boundary

The focused final91 tests pass, including fixed fusion versus neural-only order
at top_k1/20/80/1000, complete delegate ordering, immutable source handling,
bidirectional profile drift rejection/reopen, invalid-policy early rejection,
CLI default/explicit forwarding and rejection of ignored configuration. Existing
durability, index-repair and isolation tests remain in that run. These tests use
fake model/index boundaries; the real database/model run above is separate.

Full regression: **2353 passed,33 skipped,3 subtests**,263.31s, one existing
optional Graphiti/Pydantic deprecation warning. That invocation collected tests
before four final CLI-forwarding/bidirectional-drift cases were added; all four
are included in the later passing91-test focused run. Do not call this a final
2357-test full run or count skipped tests as live-backend coverage.

Repository Ruff passes; changed runtime/smoke Pyright reports0 errors/warnings;
changed Python files pass formatting. Next work is a separately frozen deployment
configuration and external reachability/official contract/model-profile checks,
not another ranking sweep or rebuilding the opened/reserved corpus.
