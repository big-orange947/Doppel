# Changelog

## 0.4.1

Periodic history aggregation for statistical memories while keeping online processors
stateless and store-independent.

### Added

- `MemoryBatchTask`, `BatchTaskContext`, `BatchProposalPlan`, and `BatchTaskRunner` for
  host-scheduled, one-shot aggregation runs.
- Exact-scoped read-only `ScopedHistoryReader` and `ScopedMemoryReader` protocols, with
  Store-backed reference implementations.
- `HistoryWindow` and host-owned `BatchCheckpoint`; a next checkpoint becomes
  committable only when proposal processing finishes without errors.
- `MemoryStore.scan()` and opaque `(created_at, memory_id)` cursor pagination for the
  stable InMemory and SQLite backends.
- Shared `ProposalWriter` used by both online and batch pipelines for validation,
  policy, scope authorization, deduplication, hooks, and persistence.
- `DoppelClient.run_batch_task()` convenience entry point.

### Changed

- `DoppelClient.process()` with no `processors` is now a no-op. Use `ingest()` to retain
  an event, or pass `[EventProcessor()]` explicitly.
- `ProcessorHooks.after_proposal()` receives `ChatMessage | None`; batch proposals have
  no single source message.
- Graphiti explicitly reports no pagination support and raises `NotImplementedError`
  for `scan()`.

### Design boundary

- Doppel runs one batch invocation; scheduling, leases, retries, and checkpoint storage
  remain responsibilities of the Agent runtime.
- Ephemeral IM interactions do not need to become long-term memory. Applications can
  supply a history reader backed by their event log and persist only aggregate proposals.

## 0.4.0

Retrieval composition, SQLite full-text search, and portable IM history ingestion.

### Added

- `RetrievalStrategy` and `Reranker` protocols with `StoreRetrievalStrategy` and
  `IdentityReranker` reference implementations.
- Candidate over-fetching, stable deduplication, and exact-scope guards both before and
  after custom reranking.
- SQLite FTS5 indexing for content and metadata, BM25 ordering, migration-time rebuild,
  synchronization triggers, runtime capability reporting, and substring fallback.
- Portable `IMImportBatch`/`IMImportItem` JSON envelopes and structured `ImportResult`.
- `DoppelClient.import_batch()` for multi-scope, scope-level-idempotent history imports.
- Stable fallback event identities from import source/item IDs, with batch provenance
  retained under `raw.doppel_import`.
- `sender_id`, `thread_id`, and `thread_root_id` message primitives; reply, quote, thread,
  attachments, and raw source provenance now survive stable Store round trips.

### Changed

- SQLite schema version is now 3. Existing valid databases are migrated and their FTS
  index is rebuilt automatically when FTS5 is available.
- `DoppelClient` accepts `retrieval_strategy`, `reranker`, and `candidate_multiplier`.
- Retrieval extension points cannot return unscoped results or inject results outside
  the caller's exact scope whitelist.

### Compatibility

- `MemoryStore.search()` remains the backend contract and default candidate source.
- SQLite can be constructed with `enable_fts=False`; lack of FTS5 support also degrades
  to the existing escaped `LIKE` behavior.
- Message `thread_id` is provenance only. Doppel never turns it into a scope dimension
  implicitly; use `scope.with_dimension("thread_id", value)` when thread isolation is
  desired.

## 0.3.0

Pluggable proposal-processing release. Doppel still does not choose an LLM or decide
which domain facts an application should retain.

### Added

- Backend-neutral `MemoryProposal` with confidence, proposed state, processor identity,
  source IDs, derived chain, metadata, and exact target scope.
- `MemoryProcessor` and `ProposalPolicy` protocols plus a pass-through default policy.
- `MemoryPipeline` coordination with per-run idempotency-key deduplication and explicit
  target-scope authorization.
- Deterministic `EventProcessor` and `DoppelClient.process()` convenience entry point.
- Five finite lifecycle hooks: `before_process`, `after_proposal`, `before_write`,
  `after_write`, and `on_error`.
- Structured `ProcessingResult` and `ProcessingError` reporting; processor failures do
  not hide successful results from other processors.

### Semantics

- Processors never receive or write a `MemoryStore`; they only return proposals.
- The default policy preserves a processor's proposed state. A policy can replace or
  reject a proposal, but Doppel does not impose a confidence threshold.
- A pipeline run can write only to its invocation scope unless additional exact scopes
  are explicitly supplied through `allowed_scopes`.
- A failing `after_write` hook is reported as an extension error and does not relabel an
  already successful store write as failed.

## 0.2.1

Protocol-hardening release for the pre-1.0 API.

### Added

- Canonical collision-resistant `MemoryScope.scope_key`, including extra dimensions.
- Generic `MemoryStore.put/get/transition` contract and optimistic state transitions.
- Structured `WriteResult`/`WriteStatus` outcomes.
- Scope-level idempotency, default inactive-state filtering and scope-guarded deletion.
- SQLite schema versioning, v0.2 migration, WAL/busy timeout and concurrent-operation safety.
- Shared InMemory/SQLite conformance tests, SQLite race/persistence/migration tests and an
  optional Graphiti 0.29 adapter smoke test.
- `py.typed` marker for typed-library consumers.

### Changed

- Store matching is exact; hierarchy expansion belongs to `ScopePolicy`.
- All public timestamps are timezone-aware `datetime` values normalized to UTC.
- `ChatMessage.actor` preserves custom actor strings.
- `DoppelClient.ingest`, `write_background` and `write_relation` return `WriteResult`.
- `forget` now requires `(scope, memory_id)`.
- Graphiti is explicitly experimental and unsupported lifecycle operations raise
  `NotImplementedError`.

### Migration notes

- Replace checks for an empty returned memory ID with `result.status` or `result.accepted`.
- Pass scope when calling `get`, `transition` or `forget`.
- Treat `group_id` as an opaque compatibility alias; use `describe()` for logs.
- Existing v0.2 SQLite databases with non-empty `user_id` and `agent_id` are migrated
  automatically when opened; invalid legacy scopes must be corrected before migration.
