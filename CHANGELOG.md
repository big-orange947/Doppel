# Changelog

## Unreleased

### Direction

- Freeze Doppel's ownership boundary as the authoritative long-term memory core for
  information about a person. Chat remains the first mature adapter rather than the
  domain definition; Agent workflow state, procedural execution memory, complete
  document stores, and live source-system state stay outside the core.
- Reframe v0.9 around held-out high-quality personal retrieval. PostgreSQL remains
  authoritative while pgvector and Graphiti provide derived candidates that must pass
  exact-scope Store revalidation; ease of minimal configuration is not the v0.9 target.
- Add a repository-only personal hybrid retrieval ablation benchmark
  (`benchmarks/personal_retrieval_ablation.py`) that compares lexical /
  lexical+pgvector / lexical+Graphiti / full hybrid over the same pre-extracted
  fixture set through the real `PersonalMemoryQueryEngine`. It runs with zero
  external LLM calls, preseeded Graphiti relations, local bge-small-zh embeddings,
  structured unavailable handling, hard gates (scope/provenance/temporal/reload),
  per-source contribution counts, graph fallback-vs-rich edge classification,
  metamorphic safety checks, and a threshold sweep. The candidate dataset
  (`personal-retrieval-ablation-zh-v1.json`, 37 queries / 5 users / three
  partitions) remains a draft and is not publication-ready.
- Ablation semantics v2: planner modes (`oracle` fixture-grounded plan vs the
  real deterministic planner) split planner failures from retrieval failures;
  `lexical_vector_graph` executes only when both indexes are live and single-source
  composites are reported as degradation diagnostics; temporal violations are
  attributed to retrieval only under an oracle plan; fixtures carry semantic
  validation (event_key on episodes only, plans without event_key, owner subject
  consistency, as-of reachability, explicit cross-subject authorization,
  deferred_cross_subject partition); Graphiti edge counts are renamed to
  `returned_edge_counts` and true final-hit attribution is computed from engine
  accepted hits crossed with edge->episode->memory mappings; reports embed
  reproducibility fields (command, commit, dataset fingerprint, canonical payload
  hash, and a sidecar hash of the final report file).

### Changed

- Retrieval evaluation checks accepted interval plans against the interval rather
  than an arbitrary representative as-of label. Out-of-interval hits still fail;
  unrelated/forbidden evidence is not excused by temporal overlap.
- Retrieval report replay preserves explicit failed Planner attempts while executing
  valid drafts, without paid retries. Failed evidence-bearing queries remain in
  recall/MRR denominators and source failures are attributed to Planner hard gates,
  not retrieval. Missing/duplicate/unclassified attempts remain invalid inputs.
- Provisional query behavior: planner `relation_types` now bind as candidate types;
  exact filters require the host `required_relation_types` argument. Existing stored
  execution plans retain explicit-filter semantics. Reference Planner v10 describes
  suggestions, and typed-oracle benchmarks explicitly bind host gold constraints.
- Graphiti reserves a neutral candidate bank plus a bounded suggested-type bank,
  deduplicates edges before reranking, and never promotes an inferred type by label
  alone. Exact scope/time/provenance and Store gates remain in force. Reports mark
  the new execution semantics so ambiguous suggestions are not labeled hard filters.
- Reference Planner v9 distinguishes requested-predicate ambiguity from unknown
  answers or other relationships of the same entity, uses host endpoint roles and
  explicit exclusions, retains common-noun anchors, and requests brief/omitted
  explanations. No ontology/query-specific rules, retrieval/ranking changes,
  automatic repair, token-cap increases, or quality gains are assumed.
- Give existing query-time validation constraints distinct content-free error
  codes and preserve them in redacted benchmark diagnostics/replay. Record output
  truncations and explanation lengths without new quality gates; retain old
  unspecified errors and provider truncation/status details rather than guessing.
- Add a dry-run-by-default, one-command fresh relation catalog comparison with
  hidden process-only credential input, two fixed no-cache/no-retry arms capped at
  130 total calls, input drift checks, unique output directories, and paired
  metric/status reports. Preserve first-pass failures and stop on authentication
  failures; no live quality gain is claimed until the comparison is executed.
- Add opt-in host-owned `RelationTypeDefinition` catalogs to query requests and
  engine plan/query calls. Definitions carry meaning, directed endpoint roles,
  and boundaries; duplicate/unknown labels fail before planning, while labels-only
  provider inputs remain compatible. Reference Planner v8 reads definitions without
  changing its output schema, hard filters, authority/time guards, or ranking.
- Add a relation-planner `--relation-catalog` ablation arm with one global,
  answer-free example vocabulary, catalog hashes, definition-sensitive caches,
  and catalog-bound replay. Keep legacy report fingerprints and scores unchanged;
  this is instrumentation and schema context, not a demonstrated quality gain.
- Harden relation-planner evaluation: fail fast on authentication errors, preflight
  missing credentials, distinguish unexecuted cases from invalid responses, report
  zero-denominator metrics as null, and keep only redacted field/code validation
  diagnostics. Cache-only audits use zero provider calls; replay preserves source
  failures and checks dataset/request identity. Reports record implementation hashes
  and a SHA-256 sidecar.
- Add an opt-in, explicitly post-hoc semantic review overlay for the 65-query
  relation fixture. It separates observable predicates, conservative abstention,
  and ambiguous hard filters without modifying storage gold, legacy scores, runtime
  prompts, or gates. Temporal review checks explicit point/open-interval shapes and
  flags retrieval gold that still needs review rather than silently accepting it.
- Split graph relations from generic semantic retrieval. The additive
  `RelationIndex` protocol carries explicit entity anchors and optional relation
  hints; `GraphitiRelationIndex` queries only non-fallback Entity relationships,
  maps Edge -> Episode -> authoritative memory, and never invokes Graphiti's
  embedding/BM25/RRF search. `PersonalMemoryQueryEngine` accepts this relation
  source independently from pgvector, applies the same exact-scope/authority/
  lifecycle/time Store gates, and exposes a separate `relation_score`.
- Relation hints now measure generic edge-name/fact relevance: an entity-adjacent edge
  that does not answer the requested relation remains observable at score 0.2 but is
  below the default relation gate. Explicit structured relation hints now make that
  gate an evidence-eligibility constraint by default: lexical/vector candidates may
  rank qualified graph facts but cannot answer a different relation. Semantic and
  relation candidate reads still run concurrently, and a graph outage retains the
  configured non-relation fallback. A separate 65-query Chinese relation ablation
  draft covers temporal boundaries, exact-scope name collisions, unknown entities,
  and wrong-relation adversaries without paid LLM calls. Profile latency uses one
  discarded warm-up, both dedicated PostgreSQL fixtures and exact Neo4j scopes are
  cleaned in `finally`, and quality gates can target candidate profiles independently
  without hiding control-profile failures from the report.
- Add a provisional, text-only `RelationReranker` protocol for Graphiti rich edges.
  It receives opaque edge IDs plus relation type/fact in one batch, requires an
  explicitly configured score threshold, and can only promote textual relation
  relevance; it cannot select scopes, subjects, memory IDs, time, lifecycle, or factual
  authority. Missing scores remain non-promoting. Duplicate/unknown IDs, invalid
  output, and provider exceptions fail closed to the existing lexical relation
  decision, after which Edge→Episode provenance and authoritative Store revalidation
  still apply. No default cross-encoder or benchmark-derived threshold is claimed yet.
- Add explicit `lexical_relation_reranked` and
  `lexical_vector_relation_reranked` ablation profiles backed by a benchmark-only
  local FastEmbed cross-encoder. Raw logits are sigmoid-normalized to the public 0..1
  protocol, model/version/threshold are reproducibility metadata, and final-hit
  accounting distinguishes reranker promotions from ordinary relation matches. A
  missing model, missing threshold, or load failure is structured `unavailable` and
  never silently reported under a reranked profile.
- Add the optional `QueryEmbeddingProvider` extension for instruction-aware and
  asymmetric embedding models. Stored documents still use `embed()` while search
  text can use `embed_queries()`; the asymmetric mode participates in pgvector
  profile identity, and providers must include their query template, truncation, and
  normalization in `version`. Existing symmetric providers remain compatible.
- Add benchmark-only SentenceTransformers adapters for configurable embedding and
  relation reranker models without adding PyTorch/Transformers to Doppel's runtime
  dependencies. Model/backend/revision/dimension/query-prefix hash/normalization are
  reported, missing optional packages are structured unavailable, and raw edge
  scores produce a dev/heldout/adversarial threshold sweep before the relation gate.
- Record requested device, batch size, PyTorch/CUDA versions, CUDA availability, and
  detected GPU identity for SentenceTransformers benchmark profiles so CPU and GPU
  measurements cannot be silently compared as the same runtime.
- Force raw-logit output for SentenceTransformers rerankers when Doppel owns sigmoid
  normalization. This prevents the library's single-label default activation from
  applying a first sigmoid and collapsing a second normalization around `0.5`.
- Add host-bound canonical `relation_types` to personal-memory query planning and
  Graphiti relation lookup. Types are selected only from an explicit host ontology,
  enforced again by the execution layer, and remain optional so natural-language
  hints/rerankers can handle open-vocabulary relations without domain special cases.
- Make retrieval reports disclose tracked dirty paths and a hash over the benchmark
  plus all `doppel_memory` Python sources. Relation score sweeps also emit a dev-only
  threshold recommendation using a fixed zero-forbidden/zero-false-abstention rule.
- Content-address local SentenceTransformers reranker directories in benchmark
  reports, including a full file-manifest hash and the model weights SHA-256.
- Add an independent `oracle_typed` relation-ablation mode backed by a closed
  dataset ontology. It uses the public host allowlist and exact relation-type plan
  constraints, while the existing oracle keeps surface hints, so structured Planner
  ceiling gains are not misattributed to Graphiti or the relation reranker.
- Extend the relation-planner quality runner with the same host ontology request,
  independent relation-type accuracy/recall/precision and whitelist-violation
  metrics, plus an opt-in exact-type failure gate. Existing surface-structure scores
  retain their original meaning for longitudinal comparison.
- Add a separate relation-planner quality runner over the existing 65-query
  dev/heldout/adversarial relation fixture. It measures intent, as-of recognition,
  entity/relation recall, unexpected anchors, provider errors, latency, usage, and
  partition/category accuracy before retrieval executes. Reference-model runs use a
  preflight call budget and content-addressed successful-draft cache; API keys are
  environment-only and are never part of cache keys, reports, or error details.
- Tighten the relation-planner boundary without fixture vocabulary. Explicit
  relationship/property questions must preserve a surface-form relation hint even
  when the requested endpoint is unknown; the trusted personal subject is bound as a
  scope-salted Graphiti anchor and does not need to be repeated as an entity mention.
  Ordinary state/fact/relation questions leave hard `memory_types`/`topic_keys`
  filters empty. Planner evaluation accepts explicitly labeled, semantically
  equivalent intent/time plans, reports unexpected hard filters, and can replay a
  prior paid report with a source hash and zero provider calls.
- Time-range query filtering now uses overlap with a record's authoritative
  `valid_from`/`valid_to` interval instead of requiring its effective/start instant to
  fall inside the query window. Common temporal-status aliases normalize at the
  query-draft boundary. The live 65-query relation ablation covers subject-only
  questions and continues to require zero scope, provenance, and temporal failures;
  wrong-relation forbidden hits remain an explicit quality failure instead of being
  folded into those security gates.
- The personal retrieval ablation can consume a successful planner-quality report
  as a third `report` planner mode. It requires an exact dataset fingerprint, hashes
  the source report, performs zero provider calls during replay, and reuses each
  natural-language draft across every local retrieval profile. Planner structure
  failures are attributed before retrieval failures, preventing a missing relation
  hint or harmful hard filter from being mislabeled as a pgvector/Graphiti defect.
- Reference planner v6 treats `default_subject/default_subject_id` as host authority:
  model output cannot reinterpret a mentioned person, pet, object, or place as the
  memory subject. Relation hints must preserve the shortest source-language predicate
  without the named anchor or interrogative endpoint, while named non-subject anchors
  remain independently present in `entity_mentions`. Planner quality now reports
  trusted-subject binding and uses exact normalized surface-predicate agreement rather
  than giving an overlong hint credit merely because it contains the gold term.
- Extend the additive `RelationQuery` with mutually exclusive `valid_at` and
  `time_from/time_to` coordinates. Graphiti rich-edge selection and authoritative
  Store revalidation both apply interval overlap. Explicitly time-scoped history uses
  validity coordinates rather than a present-day `historical` label, so a state that
  was already valid then and remains current now is not incorrectly excluded.
- Graphiti relation matching now expands model-generated phrases into a bounded set
  of contiguous 2-4 character Han fragments before testing edge name/fact text.
  Single-character hints never qualify an edge, expansion is capped, and no synonym,
  entity, benchmark, or domain vocabulary is embedded in runtime code. Exact scope,
  temporal overlap, provenance, and authoritative Store gates still run afterwards.
  On the draft 30-query live v6 replay this raised relation evidence recall from
  13/22 to 16/22 while forbidden, scope, temporal, provenance, and security failures
  remained zero; six synonym/abstraction misses remain and are not hidden.
- Expand the relation ablation from 14 memories / 30 queries / 3 owner scopes to
  28 memories / 65 queries / 5 owner scopes. New heldout and adversarial cases cover
  one entity carrying several valid relation types, colloquial paraphrases, expired
  possession, compositional false edges, and repeated object names across owners.
  Dataset validation now rejects duplicate gold IDs, inverted validity intervals,
  contradictory required/forbidden labels, abstention cases with required answers,
  and unmet declared minimum counts. The expanded zero-LLM live baseline records
  0.72 relation Recall@1 with one forbidden hit, versus 0.90 vector Recall@1 with
  19 forbidden hits; scope, temporal, provenance, and security failures remain zero.
- Personal-memory queries now derive one evidence-eligibility filter from the trusted
  plan for full scans, lexical candidates, semantic candidates, and final Store
  revalidation. Agent-authored output cannot become an owner/contact fact; human and
  derived active candidates remain available. Current/history/planned intents supply
  their domain-neutral temporal filter when a planner omits it. History/as-of queries
  may recover superseded or expired records only with explicit validity evidence,
  while current queries and all queries over rejected records remain closed. The
  deterministic planner also accepts whitespace around explicit Chinese
  year/month/day separators without guessing incomplete dates.

- Add provisional `CompositeSemanticIndex` for parallel pgvector/Graphiti candidate
  retrieval. It performs exact-scope weighted RRF, forwards current/as-of instants only
  to temporal-capable sources, degrades per known unavailable source, and exposes the
  contributing source names in personal-query hit reasons after authoritative Store
  reload.
- Candidate deduplication now keys memory IDs by exact scope as well as ID, so two
  explicitly authorized scopes cannot hide each other when a custom Store reuses an
  ID namespace.

- Graphiti temporal projection v3 now carries authoritative evidence observation time,
  temporal status, and valid-from/valid-to coordinates into each episode. Current and
  as-of personal queries use the additive `TemporalSemanticIndex.search_at()` path;
  source records are reloaded and revalidated after Graphiti BM25/cosine/RRF recall.
- Graphiti candidates now return the authoritative source memory ID rather than an
  edge UUID. All `MemoryFilter` fields are proven against the recovered Store record,
  so Graphiti can participate in personal-memory hybrid retrieval without weakening
  exact-scope, lifecycle, provenance, or temporal gates.
- Graphiti 0.29 stable-UUID indexing now pre-creates the deterministic Episode slot
  required by upstream's ``add_episode(uuid=...)`` update path. Failed extraction
  removes that incomplete slot so reconciliation can retry instead of mistaking a
  header-only Episode for a completed graph projection.
- Graphiti projection v4 now carries authoritative ``DOPPEL_SUBJECT`` metadata into
  extraction using a scope-salted stable pseudonym rather than a raw platform subject
  ID. First-person facts are connected to that subject entity instead of collapsing
  into object self-loops, while v2/v3 projections are marked for additive upgrades.
- Graphiti projection v5 requires the authoritative pseudonymous subject in every
  Episode's entity set. If a provider still accepts an Episode without producing a
  usable relationship, Doppel adds one explicitly named deterministic fallback edge
  with the Store's fact, validity interval, Episode provenance, and deletion links.
  Rich extracted relations remain preferred; v2-v4 projections reconcile additively.

- OpenAI-compatible structured output can optionally send a provider thinking-mode
  toggle. This supports low-cost non-thinking extraction on compatible providers while
  leaving the existing request shape unchanged by default.
- The provider accepts an optional content-free usage observer and normalizes common
  OpenAI/DeepSeek prompt, completion, cache-hit/cache-miss, total, and reasoning token
  counters before structured-content validation. Hosts can enforce budgets even when a
  paid response is later rejected as truncated or invalid.
- The reference personal-memory analyzer now validates model drafts independently:
  invalid items are rejected with content-free diagnostics while valid siblings remain
  usable. Its prompt also makes the `episode`/`event_key`/`kind=event` relationship
  explicit for JSON-object providers that cannot enforce cross-field JSON Schema rules.
- Reference extraction now asks compatible models to use Doppel's canonical temporal
  and memory-type vocabulary and to merge compatible evidence about one entity inside
  a batch. Common provider aliases (`future`, `past`, `history`, `present`) normalize to
  `planned`, `historical`, and `current` at the validation boundary.
- Extracted memory content is instructed to preserve the evidence's primary language
  and identifying terms so lexical retrieval and evidence audits do not fail because a
  compatible model unnecessarily translated names or locations.
- Reference-model `subject_id` values are now discarded before draft validation;
  owner/agent identity is derived from trusted scope and contact identity from bound
  evidence. Custom analyzers still receive the strict mismatch checks.
- The reference extraction contract explicitly excludes cancelled, hypothetical,
  denied, and intended-but-not-completed occurrences from episode/event-key counting;
  cancellations remain auditable plan revisions instead of invented completed trips.

## 0.8.3

Doppel now includes an official OpenAI-compatible implementation of its existing
provider-neutral `StructuredOutputModel` boundary. Reference extraction, query
planning, and semantic consolidation can run without every host rebuilding HTTP,
schema, refusal, and failure handling.

### Added

- `OpenAICompatibleStructuredOutputModel` over async `/v1/chat/completions`, with
  configurable model/base URL and JSON Schema or JSON Object response formats. It can
  target OpenAI or compatible local/gateway endpoints without a vendor SDK.
- `OpenAICompatibleStructuredOutputConfig` with bounded request/response sizes,
  timeout, optional completion-token/temperature controls, normalized secret-free base
  URLs, deterministic config fingerprints, and a generation identity that excludes
  purely operational limits.
- `StructuredOutputProviderError` classifies authentication, rate limiting, retryable
  HTTP/transport/timeout failures, refusal, content filtering, truncation, unexpected
  finish reasons, invalid envelopes, invalid JSON, and size violations. Errors expose
  safe machine-readable status/retry context without response, prompt, or key text.
- Async context-manager/`aclose()` support and optional host-owned `httpx.AsyncClient`
  injection for connection policy and deterministic tests.
- A real-provider-bound Reference analyzer test and an executable environment-driven
  example. The full transport suite covers JSON Schema/Object requests, Unicode,
  authentication/header rules, refusal/truncation, retry metadata, size limits, and
  downstream Pydantic validation.

### Compatibility and operations

- The provider/config/error APIs are additive provisional root exports. `httpx` moves
  from the dev extra to the small core dependency set so the official provider works
  after a normal install; Store protocols and persisted database schemas are unchanged.
- API keys are constructor-only private state: they are absent from Pydantic config,
  fingerprints, plans, memory provenance, exception messages, and repr output. Hosts
  still own environment/secret management, retries, budgets, fallback, and shutdown.
- `strict_schema` defaults to false because Doppel reference schemas intentionally
  contain defaulted fields and open metadata that are outside the OpenAI strict JSON
  Schema subset. Endpoint output still must be a JSON object and is always revalidated
  by the component-specific Pydantic model. Compatible custom strict schemas may opt in.
- Reference analyzer, query planner, and consolidator versions now bind the injected
  structured model identity. Changing model, endpoint, schema mode, or generation
  parameters therefore changes proposal idempotency/planner/checkpoint identity instead
  of silently replaying an earlier model configuration.

## 0.8.2

Doppel no longer treats a newer incompatible claim as sufficient proof that an older
personal memory is wrong. Conflicting current or planned claims now remain visible and
queryable until evidence explicitly marks a correction or retraction.

### Added

- `PersonalMemoryDraft.revision_kind` and `PersonalMemoryRevisionKind` distinguish an
  ordinary assertion from evidence-bound correction or retraction. The reference
  analyzer is instructed to use revision markers only when the cited message says so.
- `ConsolidationOperation.CONFLICT` and replay-safe conflict actions. A conflict writes
  one derived `memory_conflict` marker while keeping every source memory active; it
  does not select canonical content or transition sources.
- Runner-side correction safety gates apply to deterministic and model consolidators:
  `CORRECT` requires one shared non-empty topic, one current/planned temporal class, a
  strictly latest canonical source, and explicit correction/retraction metadata.
- Personal-memory query results expose `conflicts` with marker provenance, all source
  IDs, and matched source IDs. Conflict markers are read separately and never appear
  in ordinary personal-memory hits; a relevant open conflict forces `ambiguous=True`.
- Consolidation quality fixture v2 adds unmarked divergence, explicit retraction, and
  equal-time conflict cases. Its schema v2 also makes source lifecycle and isolated
  conflict-marker creation correctness gates.

### Compatibility and operations

- The new draft/result fields, root exports, and conflict operation are additive
  provisional APIs. Stores need no schema migration because markers use ordinary
  `MemoryRecord`/`MemoryProposal` primitives and a dedicated tag.
- This release intentionally tightens the provisional consolidation policy: records
  produced before v0.8.2 default to `revision_kind=assertion`, so they cannot silently
  replace an incompatible claim. Re-extract explicit correction evidence or annotate
  trusted imported records before requesting `CORRECT`.
- Conflict markers become query-inert once fewer than two referenced source memories
  remain active, for example after a later explicit correction. v0.8.2 does not mutate
  the old marker to a closed state; marker compaction is left to later governance.

## 0.8.1

Doppel can now evolve personal memories without turning age or recall frequency into
an implicit deletion policy. The new governance layer is conservative by default,
fully provenance-bound, and additive to the frozen Store lifecycle.

### Added

- `MemoryGovernancePolicy`, schema-constrained decisions, full exact-scope inputs,
  integrity-bound plans, checkpoints, action results, and `MemoryGovernanceRunner`.
  Policies can propose reinforcement, decay, or archive for supplied active IDs but
  cannot select scope, mutate evidence, write directly, or delete records.
- `DeterministicMemoryGovernancePolicy`: distinct trusted owner/peer evidence can raise
  importance; only state/plan/commitment memories with an explicit ended `valid_to`
  archive automatically. Stable facts, preferences, relationships, and historical
  episodes never disappear merely because they are old or have not been recalled.
- Decay is disabled by default and remains limited to records explicitly marked by the
  host with `retention_class=ephemeral`. When enabled, it is interval-limited, bounded
  by a floor, and produces a new audited snapshot rather than mutating in place.
- Archive uses an inactive `expired` replacement snapshot with source fingerprint,
  version, policy/config identity, reason, evaluation time, importance values, and
  derived chain. The active source is then optimistically transitioned to
  `superseded`; no evidence is deleted.
- Explicit restoration from a Doppel archive to a new candidate or confirmed snapshot.
  Restore preserves the original validity interval and keeps the archive inactive, so
  recovery does not silently rewrite temporal meaning.
- `DoppelClient.govern_personal_memory()` and
  `DoppelClient.restore_personal_memory()` convenience entries.
- Current-intent personal-memory queries now apply `valid_from`/`valid_to` against the
  plan's trusted `now`, so an ended temporary state is excluded even before the next
  scheduled governance cycle runs.
- A versioned Chinese governance fixture, report schema, CLI runner, tests, and CI gate
  for false/missing actions, operation choice, importance, lifecycle, provenance, and
  scope isolation.

### Compatibility and operations

- Governance APIs are additive provisional APIs; stable `MemoryStore`, `MemoryState`,
  `MemoryProposal`, query, and retrieval shapes are unchanged. Existing Stores with
  stable pagination work without a schema migration.
- Hosts own scheduling, durable plan/checkpoint storage, and one in-flight governance
  or consolidation writer per exact scope. Replay handles partial failure of the same
  plan; it is not a substitute for a distributed lease between competing plans.
- v0.8.1 does not infer that a planned event occurred, decay from last-access time,
  synthesize new facts, or permanently delete archived evidence. Those choices require
  explicit evidence or host policy.

## 0.8.0

Doppel now retrieves personal memories by question intent and time semantics instead
of treating every query as an unstructured similarity search. The new layer returns an
auditable evidence set and conservative aggregation; final answer generation remains an
Agent-runtime responsibility.

### Added

- Scope-free PersonalMemoryQueryPlanner drafts for lookup, current, history, planned,
  list, count, and explicit as_of questions, with a transparent Chinese deterministic
  baseline and a schema-constrained reference planner over StructuredOutputModel.
- PersonalMemoryQueryEngine binds planner output to explicit exact scopes and a trusted
  subject, performs bounded complete active-memory scans, applies subject/type/topic/
  temporal/validity gates, and returns integrity-bound plans plus complete evidence.
- Current, planned, historical, and point-in-time retrieval semantics. Planned records
  do not become actual facts merely because an as_of date falls in their proposed
  interval, and unresolved current/as-of conflicts are returned as ambiguous evidence.
- Conservative episode counts based on distinct non-empty event_key values. Counts are
  indeterminate if any matching episode lacks a stable identity.
- Optional semantic scoring over the existing SemanticIndex protocol. Only known
  memory IDs already loaded from authorized exact scopes can receive semantic scores;
  unknown and cross-scope candidates are discarded.
- DoppelClient.query_personal_memory() as the convenience entry point. Analyzer drafts
  gain optional episode-only event_key metadata for downstream deduplication.
- A versioned Chinese query-quality dataset, result schema, CLI runner, tests, and CI
  gate covering temporal residence, travel enumeration and count safety, Chinese
  lexical paraphrases, ambiguity, and cross-user isolation.

### Compatibility and scope

- Query APIs and PersonalMemoryDraft.event_key are additive provisional APIs. The
  stable generic Store/Retriever/RecallResult contracts are unchanged.
- The deterministic planner intentionally covers a small, transparent Chinese intent
  set. Applications may inject the reference model planner or their own planner;
  semantic quality still depends on the host's index and embedding provider.
- An exact count is exact over the complete authorized snapshot's asserted stable event
  keys. It does not independently prove that an analyzer assigned real-world event
  identity correctly. Generated answers, temporary-state expiry, and plan fulfillment
  remain outside v0.8.0.

## 0.7.3

Doppel can now turn evidence-bound personal-memory candidates into an auditable active
set without giving a model direct Store authority. This release adds conservative
duplicate consolidation and explicit-slot correction while treating false merges as a
harder failure than missed merges.

### Added

- `MemoryConsolidator`, schema-constrained `ConsolidationDecision` values, and
  `ReferenceMemoryConsolidator`. A model may select existing source IDs and one existing
  canonical source, but cannot generate replacement content, scope, authority, state,
  IDs, or deletion/expiry actions.
- `DeterministicMemoryConsolidator`, which merges normalized duplicate non-episode
  memories and applies newest-wins correction only inside one identical non-empty
  `topic_key`, subject, personal-memory type, and temporal class. `current` and
  `planned` claims coexist; historical/unknown claims are never treated as replacements.
- `ConsolidationRunner` and `DoppelClient.consolidate()` with full exact-scope reads,
  bounded planning, immutable source snapshots, Store fingerprints, optimistic
  lifecycle transitions, and a serializable integrity-bound plan. The canonical record
  is written idempotently before source records become `superseded`; a partial failure
  can replay the same plan without creating another canonical record.
- Consolidated records preserve the selected canonical content and union source
  evidence/provenance. A checkpoint is released only after every canonical write and
  source transition completes cleanly.
- A versioned Chinese consolidation-quality fixture, result schema, CLI runner, and CI
  correctness gate measuring false/missing actions, canonical selection, scope leakage,
  and latency. Adversarial cases cover unrelated claims, repeated trips, topic-key
  collisions, historical mentions, and current-versus-planned state.
- Optional `PersonalMemoryDraft.topic_key`, allowing analyzers to identify stable slots
  such as `residence.primary` while leaving the field empty when uncertain.

### Compatibility and scope

- Consolidation APIs and `topic_key` are additive provisional APIs. Existing stable
  Store, processor, proposal, retrieval, and lifecycle contracts are unchanged.
- v0.7.3 deliberately does not infer that a plan happened, expire temporary facts,
  count semantically distinct trips, invent a synthesized fact, or solve ambiguous
  conflicts. Those require temporal policy, event identity/aggregation, or a reviewed
  application/model decision in later stages.
- Hosts own scheduling, a single-writer lease per exact scope, and durable
  checkpoint/plan storage. A Store needs stable pagination for a full-scope
  consolidation audit.

## 0.7.2

Doppel now has its first official personal-memory extraction path. The release narrows
the product direction from a generic conversational memory framework to a
provenance-aware personal memory and context core for long-running personal agents,
while preserving backend-neutral protocols and the existing Agent-runtime boundary.

### Added

- `PersonalMemoryDraft`, `PersonalMemoryAnalysisRequest`, and
  `PersonalMemoryAnalysis` as schema-constrained, evidence-bound analyzer values.
  Drafts distinguish open personal-memory types, subjects, temporal interpretation,
  optional validity bounds, confidence, and one or more source evidence IDs.
- `StructuredOutputModel` and `ReferencePersonalMemoryAnalyzer`, providing a small
  provider-neutral model boundary, reviewed output schema, and a high-precision
  reference instruction set. The core package adds no network dependency and works
  with host-owned local or hosted providers.
- `PersonalMemoryExtractor` for self-contained online facts and
  `PersonalMemoryMiner` for bounded, exact-scope, checkpointed history windows. Both
  emit ordinary candidate `MemoryProposal` values and use the existing policy,
  authorization, hook, idempotency, and Store path.
- Trusted post-model gates for known evidence IDs, one source actor per claim,
  subject/source agreement, trusted owner/agent IDs, contact sender binding, maximum
  outputs, confidence threshold, deterministic idempotency, and duplicate removal.
  Owner memories may target user scope only through explicit `allowed_scopes`;
  contact memories stay in the source conversation, and agent/system evidence is
  excluded by default.
- A separate extraction-quality runner that injects a real analyzer into the periodic
  extraction path and reports gold evidence coverage, supported-candidate precision,
  subject and target-scope accuracy, ignored/agent evidence writes, latency, and hard
  cross-user leakage. It explicitly does not equate evidence overlap with semantic
  content correctness.

### Compatibility and scope

- All personal-memory intelligence exports are additive and provisional. Stable
  `MemoryStore`, `MemoryProcessor`, `MemoryProposal`, retrieval, and lifecycle shapes
  are unchanged.
- v0.7.2 does not consolidate conflicts, supersede old facts, infer that plans
  happened, expire temporary states, generate answers, or grade model semantics.
  Those remain separately auditable work for the consolidator, temporal retrieval,
  and live-model quality stages.
- PyPI publication, additional Stores, cloud hosting, broad provider integrations,
  and generic knowledge-base positioning remain deferred in favor of personal-memory
  correctness.

## 0.7.1

Doppel now has a reproducible quality baseline for the problem the framework exists to
solve: selecting safe, useful evidence from long-horizon Chinese IM conversations. This
release intentionally adds no extractor or model integration; it measures the current
gap before the reference intelligence is designed.

### Added

- A versioned `doppel.memory-quality.zh.v1` fixture with 10 scenarios, 34 messages,
  13 future gold memories, and 11 evidence-labeled queries. It covers stable facts,
  explicit corrections, speaker and authority attribution, cross-user scope attacks,
  explicit user-scope expansion, long-horizon distractors, repeated evidence, stale
  facts, and abstention.
- Four deterministic baselines: no memory, a recent authorized window, transparent
  Chinese character n-gram retrieval over all raw events, and Doppel v0.7 raw-event
  ingest with default Store retrieval.
- Layered retrieval metrics for evidence coverage, candidate precision, reciprocal
  rank, abstention, forbidden evidence, redundancy, context characters, latency, and
  scope leakage. Extraction, consolidation, answer correctness, and model cost are
  explicitly declared unmeasured instead of being inferred from retrieval scores.
- A strict result JSON Schema, committed release-reference report, dataset fingerprint,
  CLI runner, adversarial contract tests, and a dedicated CI smoke job. Out-of-scope
  candidates fail the run; weak but scope-safe quality remains observable for honest
  baseline comparison.

### Direction

- The next intelligence layer must improve this fixed baseline rather than introducing
  domain-specific processors or self-reported model scores. Gold memories and evidence
  groups are already present for the reference extractor and consolidator planned for
  subsequent releases.
- PyPI publication, additional Stores, cloud hosting, and new graph features remain
  intentionally deferred while memory quality is the primary development gate.

## 0.7.0

Derived semantic indexes now have an explicit lifecycle contract and a resumable way
to converge on the authoritative Store. Retrieval remains independent: implementing
`SemanticIndex.search()` does not silently make an index a persistence owner.

### Added

- Provisional `IndexWriter` with exact-scope `inspect`, idempotent `upsert`/`delete`,
  and paginated `scan_entries` operations, plus serializable entry, operation,
  checkpoint, failure, and report models.
- `IndexMaintainer`, which reconciles one bounded page at a time in two phases. The
  records phase adds or refreshes active records and removes inactive records; the
  entries phase removes hard-delete orphans and repairs changes racing the first
  phase.
- `memory_index_fingerprint()` as the canonical SHA-256 digest binding an index entry
  to the complete authoritative `MemoryRecord`, including lifecycle version and
  provenance.
- Failure-safe, index/scope/schema-bound maintenance checkpoints. A failed page never
  releases a new checkpoint, while successful index mutations remain safe to replay.

### Backends

- `PostgreSQLVectorIndex` now implements `IndexWriter`. Its profile table records exact
  scope, complete record fingerprint, and source version; existing profile tables are
  migrated in place. Metadata-only lifecycle changes do not call the embedding
  provider, and hard deletes remain protected by the core-record foreign key cascade.
- `GraphitiSemanticIndex` now implements the same maintenance contract. Versioned
  Doppel episode names carry the source fingerprint, repeated submissions skip
  unchanged episodes, stale episodes are replaced, and exact-scope catalog scans allow
  orphan pruning through Graphiti's episode removal API. Legacy v1 episode names are
  recognized as stale and repaired during reconciliation.

### Compatibility

- The stable `MemoryStore` and `SemanticIndex.search()` contracts are unchanged. The
  new lifecycle surface is provisional and additive at the package root.
- `GraphitiSemanticIndex` remains module-only experimental even though it implements
  the provisional root `IndexWriter` protocol. `GraphitiMemoryStore` remains deprecated.
- Hosts own scheduling and checkpoint persistence. Doppel executes one bounded page;
  a completed cycle returns a reset records-phase checkpoint with an incremented cycle
  counter for the next audit.

## 0.6.2

Graphiti is now explicitly modeled as a graph-derived semantic candidate index, not a
partial implementation of Doppel's authoritative Store contract.

### Added

- Experimental module-only `GraphitiSemanticIndex`, which accepts already-committed
  `MemoryRecord` values, submits deterministic exact-scope episodes, and implements the
  `SemanticIndex` search contract for composition with `HybridRetrievalStrategy`.
- `SemanticIndexUnavailableError` as the shared, provisional signal for semantic
  sources that cannot honor a request. Hybrid retrieval may explicitly fall back to
  lexical Store candidates for this known boundary while continuing to propagate
  unexpected programming and core Store failures.
- Graphiti-specific indexing provenance, exact-scope output guards, lifecycle mapping
  for invalidated edges, authoritative Store revalidation, temporal/state
  post-filtering, and injectable-client contract tests that do not require Neo4j or an
  LLM service.

### Changed

- `GraphitiMemoryStore` is deprecated but retained as a module-only compatibility
  adapter. It still raises for unsupported lifecycle operations; new integrations
  should combine InMemory, SQLite, or PostgreSQL with `GraphitiSemanticIndex`.
- Graphiti rejects kind, actor, authority, tag, and importance filters it cannot prove
  from Graphiti edges. It never fabricates those fields merely to appear compatible
  with the semantic-index protocol.
- Graph-derived facts use their edge UUID as candidate identity and retain episode,
  extraction, validity, scope, and derivation provenance. Unknown returned scope groups
  are dropped even when the upstream service was already given exact group IDs. A fact
  is also dropped when none of its source episodes still maps to an active record in
  the authoritative Store.

### Compatibility

- The preferred Graphiti API remains module-only experimental because installing it is
  optional and its upstream 0.29 contract is pinned. The stable core Store protocol is
  unchanged.
- `DoppelClient(backend="graphiti")` remains temporarily available and emits the same
  deprecation warning through `GraphitiMemoryStore`; removal requires a future minor
  release with migration notes.

## 0.6.1

An explicit pgvector semantic index and hybrid retrieval layer that preserves the
transactional boundary of the PostgreSQL core Store.

### Added

- `EmbeddingProvider` and `SemanticIndex` protocols with stable provider name, version,
  dimensions, and exact-scope search contracts.
- `PostgreSQLVectorIndex` with profile-isolated pgvector tables, content-hash
  idempotency, batched indexing, one-page cursor backfill, structured failure reports,
  cosine search, optional HNSW indexes, health metadata, and hard-delete cascade.
- `HybridRetrievalStrategy` using weighted reciprocal-rank fusion of ordinary Store
  candidates and semantic candidates, followed by the existing Retriever scope guard.
- `VectorIndexConfig`, `VectorIndexFailure`, `VectorIndexReport`, and
  `VectorBackfillResult` as provisional, serializable operational APIs.
- A `pgvector` installation extra, pinned pgvector 0.8.6 PostgreSQL 16 CI image, real
  extension/index/search tests, and an adversarial vector-quality benchmark fixture.

### Semantics

- Core writes never call an embedding service. Callers explicitly index a successful
  `MemoryRecord`, or backfill one bounded Store page at a time. A provider outage
  therefore cannot turn a committed memory write into an ambiguous failed operation.
- A vector profile hashes provider name, provider version, dimensions, and cosine
  metric. Each profile gets its own table, so incompatible models or dimensions are
  never silently compared and can coexist during a reindex rollout.
- Indexing reloads every requested record through its exact scope and embeds the stored
  content, not an untrusted caller copy. Identical content hashes skip provider calls.
- The pgvector extension and HNSW creation are both opt-in. Exact nearest-neighbor
  search remains available without HNSW; dimensions above pgvector's 2,000-dimension
  HNSW limit are accepted only for exact search.
- Known provider/unavailable errors may explicitly degrade hybrid search to lexical
  candidates. Unexpected database and programming failures are not swallowed.

### Evaluation and safety

- The repository vector fixture supplies fixed precomputed embeddings. It measures
  expected top-1 retrieval, hybrid top-1 retrieval, exact-scope leakage, forbidden
  cross-scope IDs, complete indexing, and idempotent replay; it does not grade or
  endorse a real embedding model.
- The benchmark requires an explicit DSN and `--allow-mutating-benchmark`, and CI runs
  it only against an ephemeral pgvector database.
- `PostgreSQLStore.search()` and its `semantic_search` capability remain unchanged:
  semantic retrieval belongs to the explicit index/strategy layer, not the core Store.

## 0.6.0

A PostgreSQL core Store that is admitted by the same installed conformance contract as
the InMemory and SQLite reference backends.

### Added

- `PostgreSQLStore` as a provisional root API and `DoppelClient(backend="postgres")`
  facade option, backed by a lazy async connection pool.
- The `postgres` optional dependency (`doppel-memory[postgres]`), keeping the default
  package dependency surface limited to Pydantic.
- PostgreSQL schema v1 with exact scope keys, JSONB scope dimensions and metadata,
  native tag arrays, timezone-aware timestamps, stable pagination indexes, and a
  scope-local partial unique idempotency index.
- Capability-complete substring search, filters/provenance, structured owner samples,
  optimistic lifecycle transitions, soft/hard deletion, and durable
  `(created_at, memory_id)` cursors.
- A guarded PostgreSQL mode for `doppel-conformance`; it requires both an explicit DSN
  and `--allow-mutating-audit` so a remote database cannot be selected accidentally.
- A real PostgreSQL CI service running the 11 public Store checks, concurrency and
  reopen tests, facade integration, and the installed conformance CLI.

### Semantics and safety

- Pool creation and schema migration are lazy and concurrency-safe. Concurrent replay
  is arbitrated by PostgreSQL, returning exactly one `created` result and the original
  memory ID for every `duplicate` result.
- The Store creates its two tables and indexes inside an existing schema. Creating the
  schema itself is opt-in through `create_schema=True`, which supports restricted
  production roles and explicit tenant provisioning.
- Schema names accept only plain PostgreSQL identifiers and are safely quoted. Health
  output includes the backend, schema, schema version, and server version but never the
  DSN or credentials.
- PostgreSQL currently advertises substring, temporal, transaction, pagination, and
  hard-delete capabilities. Full-text and semantic/vector search remain false until
  their retrieval semantics and evaluation gates are implemented.

### Compatibility

- Existing Store protocol methods and wire models are unchanged; the release is
  additive for InMemory, SQLite, Graphiti, batch, structured content, and style APIs.
- Importing the root package does not import `asyncpg`. The missing optional dependency
  produces an actionable error only when a PostgreSQL operation first opens the pool.

### Roadmap

- Add pgvector as a separate optional retrieval capability with an embedding-provider
  protocol, deterministic fallback behavior, and hybrid-retrieval evaluation.
- Reassess Graphiti against the same core conformance gate instead of treating semantic
  search alone as Store compatibility.

## 0.5.4

A reusable, dependency-free Store conformance kit that makes the installed contract—
not repository-only pytest helpers—the backend acceptance source of truth.

### Added

- `StoreConformanceConfig`, `StoreConformanceCheck`, `StoreConformanceReport`, and
  `audit_store()` as provisional root APIs for third-party backend CI.
- Eleven isolated checks covering health, exact-scope isolation, hierarchy and extra
  dimensions, idempotency, arbitrary record round trips, filters/provenance, structured
  owner samples, lifecycle, convenience writers, pagination, temporal filters, and hard
  deletion.
- Capability-aware skip/fail semantics and `required_capabilities` for turning product
  claims into enforceable gates.
- The installed `doppel-conformance` command with InMemory and safe disposable-SQLite
  recipes, JSON output, non-zero failure status, and refusal to reuse an existing
  SQLite database.
- Focused tests for optional capabilities, required capability failures, continuation
  after a failed check, invalid configuration, and both stable reference Stores.

### Semantics

- Every check receives a run/check-specific scope, event, and memory namespace. One
  failure is captured as a structured issue and does not hide later check outcomes.
- Optional pagination, temporal-filter, and hard-delete checks skip only when the Store
  does not advertise the corresponding capability. Stable core get/lifecycle/scope and
  provenance behavior is not optional.
- The auditor reports the Store class, capability snapshot, per-check status, aggregate
  counts, `ok`, flattened issues, and `raise_for_errors()`.

### Safety and compatibility

- `audit_store()` mutates a caller-owned backend but never closes it. It transitions or
  deletes only records it created, and explicitly requires a disposable database, test
  tenant, or isolated namespace because universal cleanup is impossible without hard
  delete.
- The SQLite CLI refuses existing database files and uses a temporary database by
  default. It never guesses that an application database is safe to audit.
- Existing InMemory/SQLite pytest adapters now invoke the installed auditor instead of
  carrying a second contract implementation. Existing MemoryStore abstract methods and
  StoreCapabilities fields are unchanged.

### Roadmap

- The conformance kit becomes the admission gate for PostgreSQL/pgvector and for any
  future Graphiti stabilization. Backend benchmarks run only after conformance passes.

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
