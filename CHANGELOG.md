# Changelog

## 0.4.3

Finite history-read budgets, version-bound checkpoints, and dependency-free
conformance probes for third-party batch extensions.

### Added

- `BatchReadLimits` and `GuardedHistoryReader`, with default per-run limits of 100
  pages, 50,000 messages, and a 2,000-message requested page size.
- `BatchReadLimitError` and `HistoryReaderContractError` surfaced as structured
  `history_read` failures before proposal persistence.
- `history_pages_read`, `history_messages_read`, and `checkpoint_schema_version`
  diagnostics on `BatchRunResult`.
- Task/version/schema identity fields on `BatchCheckpoint`; tasks can declare an
  optional `checkpoint_schema_version` attribute, defaulting to 1.
- Dependency-free `audit_history_reader()` and `audit_batch_task()` probes with
  structured reports and `raise_for_errors()` for third-party CI suites.

### Safety semantics

- Readers must honor the requested limit, return a cursor for every non-empty page,
  and advance the cursor for every non-empty page, including the final page.
- Reader conformance audits also require oldest-first ordering and reject duplicate
  non-empty message identities across pages.
- Exhausting a read budget or violating the reader contract prevents checkpoint
  release and proposal persistence.
- Input checkpoints already bound to another task, task version, or schema are
  rejected before task execution. Invalid output checkpoints are rejected before any
  proposal is written.
- Legacy unbound schema-1 checkpoints remain readable and become identity-bound when
  the next clean checkpoint is returned.
- Task audits execute only the proposal phase and never write the Doppel Store; they
  cannot prove that arbitrary plugin code has no unrelated external side effects.

## 0.4.2

Host-side recipes and durable incremental watermarks for periodic memory tasks.

### Added

- A runnable `examples/periodic_memory.py` recipe that aggregates transient interaction
  events without persisting each raw event as long-term memory.
- Reference external SQLite event log, exact-scope read-only history reader, and
  `(task_key, scope_key)` checkpoint store in `examples/batch_runtime.py`.
- Cross-backend tests for final-page cursor persistence, exhausted reads, forward-only
  watermark behavior, external reader scope isolation, multi-page recovery, and empty
  incremental reruns.

### Changed

- Stable Store scans now return `next_cursor` for every non-empty page, including the
  final page. An exhausted read preserves its input cursor. `has_more` exclusively
  indicates whether the current run should fetch another page.

### Semantics

- Cursors are forward-only watermarks, not snapshots. Events inserted later with an
  ordering key before the committed cursor require a host-defined delay, overlap
  window, or source watermark strategy.
- A checkpoint must not be reused after changing the task's history filters.
- The example policies and SQLite host adapters remain recipes rather than core
  defaults or installed package API.

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
- Existing custom Stores remain compatible without implementing `scan()`; they should
  override it and declare `pagination=True` only when the stable cursor contract is
  supported.

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
