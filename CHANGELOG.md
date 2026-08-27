# Changelog

## 0.5.3

Deterministic, opt-in consumption of structured style profiles plus an independent
observable-output quality evaluator and correctness-gated benchmark fixture.

### Added

- `StyleProfessorConfig`, `StyleDirective`, `StyleGuidance`, replaceable
  `StyleGuideCompiler`, and the `StyleProfessor` reference implementation for auditable
  profile-to-guidance compilation with source/config fingerprints.
- Hard prompt budgets, directive priorities, whole-directive omission reporting,
  sample-based confidence, and safe empty guidance below a configurable sample floor.
- Structured `MaterialBundle.style_profile` loading when the backing Store exposes the
  saved profile, plus opt-in guidance through `materials(style_professor=...)`; the
  default renderer keeps v0.5.1 summary behavior when no professor is supplied.
- `StyleQualityConfig`, `StyleQualityReport`, and `StyleQualityEvaluator` for comparing
  held-out black-box replies with a reference profile without generator self-judgment.
- A repository-only observable style benchmark, fixed positive/negative fixture,
  versioned result schema, tests, CI correctness gate, and end-to-end example.

### Semantics

- Professor directives cover observable message length, punctuation, question,
  exclamation, emoji, and multiline distributions. Each directive retains numeric
  evidence, confidence, and priority.
- Common phrases are excluded from guidance by default and never contribute to quality
  scores. Explicit phrase opt-in remains bounded and labeled as non-factual data.
- Empty candidate messages are ignored and reported. A quality report cannot pass below
  its configured candidate sample floor, regardless of its aggregate feature score.

### Boundaries

- StyleProfessor is a pure compiler: it does not read or write a Store, call an LLM,
  infer personality, or decide how a model adapter applies its prompt block.
- Observable quality scores do not claim factual, semantic, identity, helpfulness, or
  safety quality. Production evaluation still needs held-out data and human blind review.
- The benchmark is independent of Store performance tooling and remains repository-only.

### Roadmap

- The v0.5 differentiation pair—structured IM content and owner-style
  mining/consumption—is now complete. The next phase returns to reusable Store
  conformance, PostgreSQL/pgvector, and Graphiti stabilization.

## 0.5.2

Structured IM content representation and opt-in media resolution while keeping
representation, resolution, and long-term memory persistence as separate decisions.

### Added

- `MediaRef` for lightweight media identity, URI, MIME, filename, size, SHA-256,
  dimensions, duration, and backend-specific metadata without embedding binary data.
- Open `ContentPart` values carrying text, a media reference, or custom metadata.
- Optional `ChatMessage.parts`, appended to the existing wire model while preserving
  `text`, legacy `attachments`, and `raw` compatibility.
- Async `ContentResolver`, structured `ContentResolution`/`ContentResolutionError`, and
  `resolve_content()` for ordered, isolated resolver composition with bound provenance.
- Structured-content round trips through IM import envelopes, InMemory, SQLite,
  Graphiti owner samples, and Store-backed batch history.
- A runnable image/custom-event recipe in `examples/structured_events.py` and focused
  validation, resolution, failure-isolation, compatibility, and Store contract tests.

### Semantics

- When explicit message text is empty, non-empty text parts supply a deduplicated legacy
  text projection. Explicit text remains authoritative.
- Resolver outputs are additional derived parts. A later resolver can observe earlier
  successful output, but every resolver receives a deep message copy and cannot mutate
  the caller's original message.
- Resolver failures are structured and do not hide successful output from other
  resolvers. Reserved `metadata.doppel_resolution` records the actual resolver name and
  version.

### Boundaries

- Doppel never fetches a MediaRef URI, stores media bytes, manages platform credentials,
  or assumes that a signed URL is durable or safe to persist.
- `resolve_content()` returns data only: it does not call a Store, run processors, change
  `message_type`, or opt a media type into StyleMiner.
- Legacy attachment dictionaries remain untouched and are not guessed into MediaRef
  values. Adapters can migrate deliberately without losing private platform fields.
- Explicit `ingest()` remains a developer decision to persist an event; constructing or
  resolving structured content creates no long-term memory.

### Roadmap

- StyleProfessor and its independent imitation-quality evaluation are the next v0.5.3
  differentiation item. Backend/conformance expansion remains subsequent work.

## 0.5.1

Owner-style mining as a first-party periodic task, closing the existing history,
proposal, Store, and persona-material loop without binding Doppel to an LLM provider.

### Added

- `StyleMinerConfig`, a frozen and fingerprinted sampling/feature configuration with
  explicit accepted message types and conversation/user target scope.
- `StyleProfile` schema 1 with transparent message-length, punctuation, emoji,
  multiline, and frequent-fragment aggregates plus a deterministic summary.
- Replaceable async `StyleAnalyzer` and a language-light
  `DeterministicStyleAnalyzer` reference implementation.
- `StyleMiner`, a `MemoryBatchTask` that reads owner history, produces an idempotent
  `style` proposal, retains bounded source provenance, and emits diagnostic checkpoint
  metadata even when the minimum sample threshold is not met.
- A runnable external-event-log recipe in `examples/style_mining.py` and focused tests
  for filtering, pagination, retry, scope authorization, structured profile storage,
  and persona material rendering.

### Behavior

- Empty text, contact/agent messages, and message types outside the configured allowlist
  do not participate in the default analysis. Images, stickers, animations, and nudges
  therefore remain transient unless an application explicitly resolves and accepts
  their text.
- Style profiles default to the source conversation scope. Writing to user scope still
  requires explicit `allowed_scopes` authorization.
- `PersonaMaterialsBuilder` retrieves the latest style memory independently of the
  current query, fills `MaterialBundle.style_summary`, keeps style out of ordinary
  events, and retains its provenance.

### Boundaries

- The deterministic analyzer describes observed text aggregates; it does not infer
  personality, identity, emotion, or intent.
- Frequent fragments can still carry repeated names or topics. Privacy-sensitive hosts
  can set `max_common_phrases=0` or provide a redacting analyzer; full source messages
  are not copied into the default profile.
- StyleMiner processes one closed window. Hosts must not expect an advancing checkpoint
  to accumulate below-threshold samples across separate runs of the same window.
- Model-backed analyzers remain application integrations responsible for provider,
  prompt, privacy, evaluation, and proposal-confirmation policy.

### Roadmap

- Structured events (`ContentPart`, `MediaRef`, and `ContentResolver`) remain the next
  v0.5.x core item; StyleProfessor and its separate quality evaluation follow the
  StyleMiner foundation rather than being replaced by infrastructure work.

## 0.5.0

A reproducible Store benchmark foundation that keeps performance observations separate
from protocol correctness and higher-level model quality.

### Added

- A deterministic `doppel.synthetic.v1` dataset generator with versioned configuration,
  fixed seeds, stable IDs/timestamps, and an included dataset fingerprint.
- A backend-neutral benchmark runner for initial writes, idempotent duplicates,
  exact-scope searches, filtered searches, and stable paginated scans.
- Nearest-rank P50/P95/P99 latency, throughput, environment, backend capability, and
  dataset metadata in a versioned JSON result envelope.
- Correctness gates for missing expected memories, forbidden memory hits, exact-scope
  leakage, duplicate-write failures, scan duplication, and incomplete scans.
- A JSON Schema for benchmark results, reproducibility guidance, InMemory/SQLite smoke
  tests, and a correctness-only CI benchmark job.

### Boundaries

- Benchmark utilities are repository-only and are not installed or exported from the
  `doppel-memory` package.
- CI does not enforce performance thresholds because shared-runner timing is noisy.
  Correctness failures still return a non-zero process status.
- The Store benchmark does not score embeddings, LLM extraction, rerankers, prompts,
  or application retention policy as if they were core Doppel behavior.

### Compatibility

- The v0.4.4 stable public API remains unchanged. The public API manifest now records
  the v0.5.0 release without adding runtime exports.

## 0.4.4

Public API freeze for the v0.4 line, with an explicit compatibility contract for
applications, custom stores, processors, readers, and batch tasks.

### Added

- A versioned `docs/public-api.json` manifest separating stable root exports from the
  still-provisional batch and conformance surface.
- Compatibility snapshots for root exports, Pydantic wire-model fields, extension
  protocol signatures, critical defaults, enum values, and the `MemoryStore` abstract
  method set.
- `docs/api-stability.md`, documenting import boundaries, compatibility rules,
  deprecation windows, and the review process for future API changes.

### Changed

- `PromptRenderer` and `ScopePolicy` are now exported from `doppel_memory`, matching
  their use in public `MaterialBundle.render()` and `DoppelClient.materials()` APIs.
- The batch-task, read-only reader, proposal-writer, and conformance APIs are explicitly
  provisional. They remain patch-compatible but may evolve in a future minor release
  with migration notes.

### Compatibility

- This release does not change runtime memory, retrieval, persistence, or checkpoint
  semantics.
- Stable root imports are protected for the remainder of the v0.4 line. Experimental
  Graphiti and example host adapters remain outside that contract.

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
