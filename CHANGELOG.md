# Changelog

## Unreleased

- Add a deterministic, frozen heterogeneous personal-memory generalization corpus with
  9,216 memories, 480 unique Chinese queries, 48 owner-disjoint scopes, and explicit
  dev/sealed/adversarial partitions. It broadens evaluation to temporal residence,
  corrections, deduplicated episode counts, document facts, cross-conversation recall,
  subject attribution, one- and two-hop relations, and related-but-insufficient
  evidence. Freeze its validation contract, result schema, guarded live runner, and
  first-run gates before opening any retrieval result. The runner keeps oracle-route
  graph execution separate from natural-language planning and compares real pgvector,
  Graphiti, Store-revalidated assembly, and reorder-only local reranking. The corpus is
  synthetic and author-known, so it remains non-publication evidence. Preserve the
  first dev-only V1 result, then supersede V1 before opening sealed/adversarial results:
  V2 changes only peer-conflict evidence from hard-forbidden to related context. Also
  distinguish a legitimate reranker `not_run` on an empty candidate set and report
  pre-rerank candidate-window coverage so recall and ranking failures cannot be mixed.
  Preserve the second dev-only result and add V3 oracle count-plan fields without
  changing corpus text or answer evidence, keeping natural Planner quality explicitly
  separate. Add an opt-in, one-record literal-entity reservation to hybrid assembly;
  it only reorders Store-revalidated candidates, remains answer-support agnostic, and
  is disabled by default.
- Add a separately gated full-corpus profile that reranks only the independent
  lexical/vector branch before atomic fusion with typed and explored Graphiti paths.
  It freezes non-regression requirements for one-hop, two-hop, temporal, overall, and
  MRR quality plus strict reorder-only, eligibility, isolation, provenance, candidate
  bound, and backend-cleanup checks before opening the 144-query GPU result. The first
  frozen run passed every gate and reached 1.000 evidence recall@5 plus complete
  evidence@10 overall and in all four categories; MRR rose from 0.616 to 0.796, while
  p50/p95 increased from 150.8/192.9 ms to 419.6/542.7 ms.
- Add a frozen semantic-only overfetch and whole-memory reranking ablation for the
  combined V2 corpus. It distinguishes index/score-gate misses from ranking errors,
  verifies the existing personal-memory reranker is strictly reorder-only, and keeps
  Store eligibility, exact scope, a 20-item context bound, and backend cleanup as hard
  gates before any local GPU result is opened. The first frozen run found 1.000
  candidate recall inside the 64-item window and improved Recall@1/5/10/20 plus MRR
  from 0.417/0.417/0.417/0.750/0.445 to 1.000 across all metrics, with zero safety or
  reorder-membership violations; p50 increased from 65.6 ms to 257.2 ms.
- Make hybrid candidate rejection auditable by separating expected filter and scope
  enforcement from stale Store references and post-read scope mismatches. The first
  frozen combined V2 live exploration run now passes its independent preregistered
  gate: 0.854 evidence recall@5, 0.806 complete evidence@10, perfect complete evidence
  on the 36 two-hop cases, and zero forbidden, scope, authority, provenance, or time
  violations. Add `--gate exploration` so this additive gate can control CLI status
  without changing the legacy typed-only default.
- Preserve the completed frozen V2 provider topology baseline (144/144 cases, 289
  calls including one rejected malformed draft). The reviewed generator reached
  91.7% one-hop recall, 58.3% explicit heldout two-hop recall, zero false candidates
  on semantic no-path queries, and zero provider errors, but failed the preregistered
  overall gate because hidden temporal paths are not inferable from query text alone
  and three outputs could not compile. The aggregate two-hop score was 29.2%.
- Let the second-pass candidate reviewer receive a bounded projection of malformed
  first-pass JSON, so it can repair self-loops and disconnected drafts without
  receiving scope, memory IDs, or arbitrary provider fields. Strict ontology and
  topology validation still applies to the reviewed result.
- Add an experimental ontology-governed Graphiti path-exploration contract for
  questions whose hidden first hop is absent from the text. Exploration is bounded
  to two hops and 512 scanned paths, exact-scope and temporal filtered, and every hop
  still requires Episode provenance plus authoritative Store revalidation. Hop-count
  and terminal-type preferences affect ranking only; results remain unassessed
  candidates and do not replace independent vector retrieval.
- Add source-aware ranking and fusion for explored paths. Identical typed and
  explored graph paths are deduplicated by scope, edge IDs, and directions; repeated
  results from one source cannot stack score, while cross-source attribution remains
  visible to hybrid assembly as `relation_path:exploration`.
- Extend the frozen combined live runner with additive explored-path and
  exploration-enhanced hybrid profiles while leaving the legacy typed-only profiles
  and gate unchanged. Pre-register a separate exploration gate requiring at least
  +0.15 two-hop complete-evidence gain, semantic/overall non-regression, a 20-item
  context bound, zero authority/scope/time/provenance violations, and backend cleanup.
- Add the frozen, deterministic `doppel-combined-retrieval-zh-v1` corpus: 144 queries,
  36 exact owner scopes, and 3,600 memories with one-hop/two-hop relations, independent
  semantic questions, temporal incomplete paths, repeated cross-owner entity names,
  and lifecycle/authority distractors. Pre-register provider-resume integrity plus
  topology, retrieval, isolation, time, provenance, and non-regression gates before
  any provider or live-backend result is opened.
- Supersede combined V1 before any provider call after offline validation found
  repeated full prompts across intentional cross-owner collisions. Add V2 with the
  same 36 scopes, 3,600 memories, topology, labels, and time boundaries but 144 unique
  provider inputs, plus a resumable acquisition harness bound to dataset/catalog,
  generator, provider configuration, and implementation commit.
- Add the corresponding live combined-retrieval runner. It refuses incomplete or
  fingerprint-mismatched topology reports, runs PostgreSQL/pgvector and live
  Neo4j/Graphiti against the same exact scopes, and independently gates topology
  quality, Recall@5, complete evidence@10, two-hop gain, semantic recall, hard
  forbidden evidence, lifecycle/authority, scope, provenance, context bounds, and
  backend cleanup while reporting tail latency and source attribution.

- Add an experimental Store-revalidated assembly for independent memory hits and
  typed relation paths. It reserves independent recall, retains paths atomically,
  caps duplicate path rank, preserves path provenance, and leaves answer support
  explicitly unassessed. Add a preregistered live lexical/pgvector versus Graphiti
  path versus assembled-union development ablation over the existing 36-query corpus.
- Preserve the first failed hybrid-path run and version its evaluation contract. V2
  distinguishes hard scope/time/authority/provenance violations from an active,
  authoritative first-hop candidate that is useful context but insufficient proof of
  a complete typed path; the projection uses record invariants rather than scenarios.
- Record the passing V2 live hybrid-path result: the assembled branch raises evidence
  recall from 0.900 to 1.000 and complete-evidence rate from 0.833 to 1.000 over
  lexical + pgvector, with zero hard-forbidden hits, scope leakage, Store revalidation
  failures, path-budget omissions, or backend residue. Candidate IDs are unchanged
  from V1, confirming that only the preregistered evaluation label contract changed.

- Record the V7 Planner-backed candidate comparison. Its exact-path abstention policy
  returned only 4/9 required routes versus V3's 7/9, while two-hop stayed 2/4. Do not
  unify exact and candidate decision contracts; stop natural-language path tuning on
  the opened corpus and evaluate candidate paths as one additive hybrid source.
- Add an experimental V7 Planner-backed candidate profile. It reuses the established
  two-pass relation-atom Planner and trusted host path compiler, then deterministically
  converts compiled directions into retrieval-only candidate atoms. This isolates
  shared path understanding from candidate-specific prompt behavior without adding
  graph, scope, answer, or execution authority.
- Record the opened V3 reviewed candidate-path result. Reusing 12 cached first passes,
  12 review calls improved required recall from 6/9 to 7/9, one-hop from 4/5 to 5/5,
  removed the only no-path false candidate, and halved extra routes, but two-hop stayed
  2/4. Stop prompt iteration on this corpus and compare the existing V7 Planner backbone.
- Add an optional two-pass candidate-path generator. A second non-authoritative model
  review can repair missing predicates, endpoint-role reversals, split chains, and
  unjustified alternatives before unchanged host ontology validation and compilation.
  The budgeted runner records the protocol and requires two calls per case for a fresh
  sealed run; existing first-pass cache entries can be reused without paid calls.
- Record the 12-case opened V2 heldout/adversarial regression. V2 improved required
  recall from 5/9 to 6/9, one-hop recall from 3/5 to 4/5, cut extra routes from 16 to
  four, and eliminated three invalid topologies, but two-hop recall stayed 2/4 and
  the complete gate failed. The next experiment uses a non-authoritative review pass.
- Record the opened V2 dev regression: required-route recall stayed 6/6 while
  generated routes fell from 12 to 6, extra routes from six to zero, and extra types
  from seven to zero. Mark partition-only runs as incomplete gates when one-hop,
  two-hop, or no-path coverage is absent.
- Record the first sealed 18-case candidate-path generator run. It passed one-hop
  recall (9/11), no-path rejection (4/4), type-expansion, and zero-error gates, but
  correctly failed overall/two-hop recall, extra-route, and invalid-topology gates.
  The corpus is now opened regression data; no Neo4j or answer-quality claim is made.
- Retain raw non-authoritative topology observations in local quality reports, allow
  keyless zero-call cache re-scoring, and tighten the reference generator's generic
  minimal/connected-path and endpoint-role instructions without query-specific rules.
- Add an experimental ontology-bound candidate-path generator and an independent
  frozen 18-query topology-quality probe. It separates candidate route coverage
  from extra graph routes/types and no-path false candidates; the model receives
  no scope, graph authority, or gold labels. Live provider calls remain opt-in and
  capped, and this probe does not claim end-to-end graph retrieval quality.
- Pre-register development gates for the first candidate-generator run and report
  overall plus dev/heldout/adversarial, one-hop, two-hop, no-path and excess-candidate
  metrics separately. A sealed run must cover every frozen case with a fresh cache.
- Record the first live Neo4j candidate-path ablation against the pre-registered v2
  dataset: 36 completed queries, 8/8 ontology-drift cases recovered, evidence recall
  0.600 to 1.000, zero forbidden hits and scope leakage, and five related-candidate
  noise occurrences. The run used no paid model calls and cleaned its fixture.
- Enforce trusted subject and subject-ID binding while Graphiti relation and path
  candidates are reloaded from the authoritative Store. Explicit contact/agent facts
  cannot enter an owner relation result inside the same scope. Legacy records without
  subject metadata remain eligible only for the exact scope owner.
- Pre-register the candidate relation-path v2 dataset fingerprints, primary
  hypotheses, hard gates, expected precision cost, zero-model contract, and first
  live output path before Docker produces any v2 result.
- Make the Windows benchmark preflight recognize Docker Desktop's inaccessible stale
  inference-socket crash signature and fail early with a safe diagnostic. It remains
  read-only with respect to WSL, containers, volumes, and Docker data.
- Add a deterministic 36-query candidate relation-path ablation over live Neo4j. It
  compares strict, candidate-only, and exact-plus-candidate routes; separates
  ontology-drift recovery from related candidate noise; and hard-gates scope,
  temporal/provenance, Store revalidation, topology compilation, route attribution,
  deduplication, and fixture cleanup. The experiment makes no LLM or external HTTP
  calls and keeps all alternative type groups in the dataset rather than runtime
  scenario rules.
- Execute the bounded exact/candidate relation-path routes concurrently before the
  unchanged deterministic RRF merge. The plan still caps route count at nine and any
  route error cancels its siblings, preserves the original error type, and fails the
  whole graph branch; independent Neo4j I/O no longer adds linearly to
  highest-configuration latency.
- Enforce the candidate-route resource bound before compiling any observation and
  weight route-level RRF contributions by the already bounded route confidence.
  Low-confidence widening can improve recall without receiving the same ranking
  influence as a high-confidence exact route.
- Deduplicate a path within each individual route before assigning RRF credit. A
  noisy or custom `RelationPathIndex` cannot inflate one graph path by returning it
  repeatedly; cross-route support is still retained and attributed.
- Canonicalize each step's relation-type set when deduplicating routes. Alternative
  lists that differ only in order no longer cause duplicate Neo4j calls or duplicate
  cross-route RRF support.
- Cap RRF support to the best contribution per route mode for each graph path. Exact
  and candidate support can still reinforce one another, while overlapping candidate
  supersets cannot manufacture confidence by matching the same stored edges.
- Compute route ranks after within-route deduplication and retain the highest-scoring
  underlying candidate object when multiple routes return the same edge path. Custom
  indexes cannot push unique paths down by injecting duplicates or hide a better
  backend score behind first-writer ordering.
- Record two incomplete V7 Flash thinking diagnostics. A 4K generation ceiling
  truncated after six cases and an 8K ceiling truncated after 21; both returned HTTP
  200 with an incomplete generation, not a network timeout. The completed 8K prefix
  was promising but still contained a wrong abstention and forbidden nearby type,
  while no no-path controls had run. Stop increasing online Planner output budgets.
- Add an experimental exact-plus-candidate relation-path retrieval layer. Host code
  compiles bounded candidate atom graphs, validates every alternative type against
  the ontology, derives directions, rejects disconnected or over-bound topologies,
  and searches every accepted route through `RelationPathIndex`. Route results are
  deduplicated with RRF attribution. Plans permanently require independent semantic
  fallback and forbid a global relation gate; this module is not connected to the
  stable query engine.
- Add valid-only diagnostic metrics beside the unchanged hard whole-corpus metrics
  for incomplete relation-path evaluations. Provider errors and unrun cases continue
  to fail gates, while reports can now show what completed cases actually measured.
- Record the V7 Pro non-thinking single-variable comparison. With the same opened V2
  corpus, two-pass protocol, host compiler, and gates, Pro regressed exact-path
  accuracy from 0.875 to 0.7083, decision accuracy from 0.9583 to 0.7708, two-hop
  exact accuracy from 0.75 to 0.4375, and no-path accuracy from 1.0 to 0.8125. It
  introduced three wrong executions and three forbidden-type hits. The complete,
  error-free run rejects the assumption that the larger non-thinking model is a
  better governed path Planner.
- Expose a bounded per-request timeout in the staged relation-path live runner so
  thinking-mode comparisons can allow slower inference without changing generation
  budgets, schemas, prompts, or quality gates.
- Record V7's opened V2 regression: the independent atom-review pass raised decision
  accuracy from 0.8542 to 0.9583, path recall from 0.78125 to 0.9375, direction
  accuracy from 0.7083 to 0.9167, and two-hop exact accuracy from 0.5625 to 0.75.
  Exact-path accuracy reached 0.875 and missed the 0.90 gate; two forbidden nearby
  types, two wrong abstentions, and four inexact executed paths prevent promotion.
  Stop prompt tuning on opened V2 and isolate the model-quality ceiling next.
- Add experimental Planner V7 for opened regression only. It performs one V6 atom
  extraction and one independent schema-constrained review, then sends only the
  reviewed observation through the unchanged host ontology validation and path
  compiler. The review may repair omitted predicates, endpoint bindings, shared
  references, or unjustified ambiguity, but still emits no direction, ordered path,
  or execution decision. The live runner records the two-provider-call-per-case
  contract and keeps the existing cache, hard budget, and host safety boundaries.
- Record V6's opened V2 regression: declarative atoms and host compilation improved
  exact path from 0.75 to 0.8333, two-hop exact from 0.3125 to 0.5625, removed the
  forbidden type, and repaired shared-endpoint/double-inbound ordering. Decision and
  path recall remained unchanged at 0.8542 and 0.78125 because seven answerable cases
  were still rejected or incompletely extracted before compilation. V6 remains
  experimental and receives no execution authority.
- Add experimental Planner V6 after the sealed V2 failure, without changing the
  default query engine. The model now emits unordered declarative relation atoms that
  bind definition source/target roles to fixed `anchor`/`answer` and shared
  intermediate references; it emits no traversal direction, ordered path, or
  execution decision. Host code validates the ontology and atom graph, finds the
  unique anchor-to-answer chain, orders edges, derives inbound/outbound, and retains
  the existing two-edge execution bound. The opened V2 corpus can evaluate this
  representation only as regression evidence.
- Record V5's immutable sealed V2 failure without weakening or reinterpreting its
  pre-registered gates. The complete 48-call run achieved perfect no-path and
  over-bound handling with zero wrong execution, but only 0.75 exact path, 0.8542
  decision, and 0.3125 two-hop exact accuracy. Inbound, shared-endpoint, implicit, and
  double-inbound compositions exposed over-abstention, omitted edges, reversed
  traversal, sentence-order sequencing, and one nearby-type error. V5 receives no
  default query-engine execution authority; V2 is now opened regression data.
- Record V5's first opened regression: 0.96875 exact-path accuracy and perfect
  execute/abstain, reason, over-bound, type, recall, and no-path metrics, with zero
  wrong execution, wrong abstention, forbidden types, or validation errors. One
  `HELD_BY` direction fluctuation remains real. The opened result authorizes a new
  sealed evaluation, not default-query-engine execution.
- Add a frozen 48-case provider-unseen V2 relation-path corpus with no V1 query
  overlap. It covers every governed type, all four two-hop direction combinations,
  implicit/shared-endpoint compositions, and balanced over-bound, ambiguous,
  unsupported, and non-relation controls. The pre-registered plan fixes gates before
  opening while explicitly keeping the small corpus non-publication-ready.
- Harden the V5 runner with `--sealed-first-run`: a frozen dataset, raw-output cache,
  empty dedicated cache directory, and new explicit report path are required before
  the provider is opened. Sealed path/type/direction/recall/category/error gates are
  enforced in addition to the generic decision gates, and the report permanently
  records that the first run opened the corpus.
- Record V4 v2's opened regression at 0.78125 exact-path/decision accuracy. It
  preserved zero wrong execution and perfect known over-bound handling, but still
  over-abstained five exact two-hop paths, called one exact inbound path ambiguous,
  and produced one contradictory hard/soft path shape. Prompt-only tuning on the
  opened corpus stops; V4 v2 receives no execution authority.
- Add an experimental two-stage relation-path Planner V5 without changing the default
  query engine. The model emits a non-authoritative complete observation of up to
  eight typed/directed edges and has no execute/abstain field. Host code validates the
  ontology, deterministically executes only exact one/two-edge observations, maps
  longer or truncated paths to `abstain/over_bound`, and maps non-exact semantics to
  safe abstention. A separate dry-run-first live runner retains cache, budget, token,
  provenance-of-run, and opened-corpus labels for regression testing.
- Record V4's first opened regression without promoting it to held-out evidence. The
  original three-hop case correctly became `abstain/over_bound` and wrong execution
  stayed zero, but eight valid two-hop chains were over-abstained, one valid inbound
  relation was called ambiguous, and one safe soft-candidate abstention failed strict
  validation. The 0.6875 decision/path result failed its gate and motivated V4 v2.
- Refine experimental Planner V4 after its first opened regression, advancing the
  Reference version to 2. Hop count now explicitly means relationship edges, so a
  start-to-intermediate-to-end chain is two hops and only a third edge is over-bound.
  Ambiguity concerns relation planning rather than downstream evidence sufficiency.
  Structured abstention may retain non-executing V2 soft relation candidates for
  ordinary recall, while steps stay empty and confidence stays zero; those candidates
  never acquire exact-filter or graph-execution authority.
- Add a module-only experimental Planner v4 decision protocol without changing V3 or
  the default query engine. V4 separates `execute` from structured `abstain`; exact
  one/two-hop paths require `path_reason=exact`, while ambiguous, unsupported,
  over-bound, and non-relation requests require empty steps, zero path confidence,
  and no soft relation candidates. Three-step output remains invalid and is never
  truncated. The Reference adapter retains host-bound subject authority, ontology
  validation, temporal grounding, and the V3 endpoint-direction rules.
- Add a separate V4 decision scorer over the now-opened 32-case V1 corpus. It preserves
  the existing path-shape metrics while independently measuring execute/abstain,
  abstention reason, wrong execution, wrong abstention, and explicit over-bound
  handling. Reports permanently label this corpus `opened_regression` and ineligible
  as unseen evidence.
- Add a dry-run-first, no-retry V4 live regression runner with content-addressed raw
  output caching, provider-call and token accounting, failure-origin separation, and
  independent gates for path shape, decision, reason, over-bound abstention, and wrong
  execution. Every report marks all V1 partitions as opened regression data and grants
  no graph execution authority.
- Record the first immutable sealed Planner v3 result. The pre-registered gate failed:
  exact path was 0.9524, all 15 answerable one/two-hop cases had exact types and
  directions, and false/forbidden paths stayed zero, but one adversarial three-hop
  request returned three correct steps instead of an explicit no-path decision. The
  host's two-hop schema rejected it, proving the safety boundary while still counting
  as a Planner validation/reliability failure. V3 therefore receives no default query-
  engine execution authority, and the opened partition will not be reused as unseen
  evidence.
- Pre-register sealed relation-path Planner gates before opening the heldout and
  adversarial partitions: exact path and path recall, per-hop type and direction,
  no-path behavior, false paths, forbidden types, and execution completeness are
  independent thresholds. Entity-string exactness remains diagnostic because the
  draft gold does not yet distinguish equivalent referring expressions.
- Strengthen V3 traversal direction without adding domain labels or query-specific
  rules: grammatical voice and a requested human actor no longer override the host
  definition's source/target roles. Traversing from an acted-on source entity to its
  actor target is outbound; starting at that actor and finding affected entities is
  inbound. The Reference Planner version advances to 3 before sealed evaluation.
- Clarify the experimental V3 path contract after its first live dev run: an exact
  directed one-hop question belongs in one `path_steps` item rather than the older
  unordered `relation_types` candidates; path direction is derived from the explicit
  starting anchor and definition endpoint roles rather than sentence order; and
  qualitative recency cannot create a boundless interval. The generic rules and JSON
  Schema descriptions contain no dataset entities or per-case relation mappings, and
  the Reference Planner version advances to 2 so old outputs remain identifiable.
- Add a dry-run-first, budgeted live provider runner for the 32-case relation-path
  Planner v3 draft. It defaults to the 11-case dev partition, supports a separately
  opened heldout/adversarial run, performs at most one no-retry request per case, and
  caches successful raw provider JSON by content before local Planner validation.
  Cache-only re-scoring consumes zero calls; provider-level and budget failures stop
  further requests while preserving explicit not-run rows. Reports bind input and
  implementation hashes, sanitized provider settings, cache/budget/token accounting,
  partition/category/trait metrics, quality gates, and a SHA-256 sidecar. The runner
  scores plans only and grants no graph execution authority.
- Add an independent 32-case Chinese relation-path Planner v3 draft and offline
  evaluator. Unlike the graph-preseeded structural retrieval fixture, every Planner
  gold path is justified by the question wording and governed relation definitions.
  The suite separates 12 explicit two-hop chains, 12 one-hop controls, and eight
  no-path cases, including inbound traversal, nearby-relation confusions, unsupported/
  ambiguous relations, non-relation requests, and an over-bound three-hop request.
  Metrics keep whole-path, hop, type, direction, entity, false/missed path, forbidden
  type, and error outcomes separate; planner exceptions cannot pass as abstention.
- Add a module-only experimental relation-path Planner v3 draft. It preserves the v2
  operation/time model while adding at most two exact typed/directed path steps and a
  whole-path confidence. Exact steps require host definitions with endpoint roles;
  soft v2 relation candidates and hard path constraints cannot coexist. The Reference
  adapter discards unknown fields, restores host-bound subject authority, reuses host
  calendar grounding, and rejects types outside the definitions. It has no scope,
  graph-execution, node-ID, memory-ID, Cypher, query-engine, or root-export authority.
- Record the first live Neo4j run of the bounded relation-path ablation and version its
  JSON result envelope. Across the 26-query draft, the typed path profile improved
  evidence recall from 0.667 to 1.000 and complete-evidence rate from 0.500 to 1.000,
  with zero forbidden hits, scope leakage, path-count failures, endpoint failures, or
  fixture residue. The report explicitly remains a narrow oracle-path development
  ceiling, not a natural-language planning or answer-quality claim.
- Add the repository-only `doppel-personal-relation-path-ablation-zh-v1` draft and
  zero-model live Neo4j runner. The deterministic builder produces 26 oracle-path
  queries across nine exact owner scopes: eight answerable two-hop chains, eight
  one-hop controls, eight wrong-type adversaries, one not-yet-valid second hop, and
  one orphan second hop. Reports compare typed one-hop, bounded path, and their union;
  evidence completeness, path count/endpoint correctness, forbidden hits, scope
  leakage, cleanup, and latency remain separate. Runtime failure is bounded and
  structured without persisting credentials. The dataset is explicitly unfrozen and
  not publication-ready; it does not add a natural-language Planner or product rules.
- Add a module-only experimental protocol for explicitly typed one/two-hop relation
  paths. `GraphitiRelationIndex.search_relation_paths()` uses one fixed bounded Cypher
  query, requires a host-selected relation type and direction at every hop, and rejects
  the complete path unless every edge stays in one exact scope, satisfies the requested
  time window, resolves through Graphiti Episode provenance, and reloads at least one
  eligible authoritative Store record. Existing one-hop `RelationQuery`, Planner v2,
  query-engine execution, root exports, and fingerprints are unchanged; no natural-
  language multi-hop planner or benchmark claim is introduced yet.
- Add an opt-in live Neo4j contract test for bounded relation paths. It creates
  uniquely prefixed Graphiti-compatible Entity/RELATES_TO/Episodic fixtures without
  constructing an LLM or embedding client, verifies one-hop/two-hop traversal,
  direction, time, orphan-provenance rejection, and same-name scope isolation, then
  deletes and independently counts its fixture nodes. Neo4j 5.26 completed the test
  with zero residual nodes and zero external model calls.
- Harden the Windows ablation-runtime preflight for a broken Docker Desktop pipe.
  Every read-only `docker version` probe now has a two-second process deadline, the
  optional Desktop start helper is hidden and bounded by `WaitSeconds`, and both paths
  fail with a clear timeout instead of hanging indefinitely under Windows PowerShell
  5. Existing running containers whose health is still `starting` now wait for their
  healthcheck instead of producing a cold-start false failure.
- Add structured `PersonalMemoryCandidateEvidence` to every personal-query hit.
  It exposes accepted lexical/semantic/relation sources, literal or relation-backed
  entity binding, and relation edge metadata while explicitly leaving
  `answer_support="unassessed"`; retrieval does not claim that related context proves
  an answer. Retrieval benchmark semantics v4 separately reports accepted-candidate
  evidence recall and candidate presence for no-evidence queries. The legacy empty-
  candidate "abstention" metric remains labeled as a deprecated compatibility alias
  and is no longer a planner-promotion gate. Dataset-excluded candidates remain
  visible diagnostics but no longer masquerade as answer or security failures.
- Partition graph/vector final-hit attribution by Planner mode. Real cached Planner
  replays now expose their own `graph_final_hit_attribution.per_mode` instead of
  silently reporting zero because the legacy attribution path only inspected oracle
  cases; the top-level compatibility fields remain oracle-only.
- Add opt-in `candidate_fusion="anchored_union"`. It preserves independent
  lexical/vector/relation discovery, but when a Planner supplies explicit entity
  mentions, a final candidate must bind one literal entity in authoritative Store
  content/relation metadata or carry a qualified relation edge. It performs no
  alias, ontology, predicate, or domain expansion. On the live 240-query v2 replay,
  typed-relation Recall@1/5, MRR, and evidence recall remained 0.9948 while
  no-evidence candidate-empty rate improved from 0.9167/0.0 to 1.0 for both
  relation-only and pgvector+relation profiles; this is a strict precision-mode
  diagnostic, not answer correctness. All scope, time, and provenance failures
  stayed zero.
- Add a non-destructive Windows Docker preflight for the PostgreSQL/pgvector and
  Neo4j benchmark services. It can start Docker Desktop and existing containers,
  waits for health, reports the WSL data disk, and never resets WSL or changes
  containers, volumes, credentials, or Docker data.
- Treat a v2 `prior` retrieval view as eligible for both ended `historical`
  records and non-expiring `timeless` facts. This keeps completed attribution,
  origin, authorship, and performed-action evidence available without admitting
  current-only mutable state or future plans. A zero-paid 240-query replay over
  PostgreSQL, pgvector, and Neo4j raised the v2 typed-relation profile's Recall@1,
  Recall@5, MRR, and required-evidence recall from 0.9479 to 0.9948 while scope,
  temporal, and provenance failures remained zero.
- Let the zero-paid retrieval benchmark replay v1 and v2 Planner reports together
  as `report_v1`/`report_v2` over one authoritative Store and one set of pgvector/
  Graphiti indexes. V2 drafts retain their orthogonal operation/time semantics,
  source schemas are verified to prevent swapped arms, the dataset calendar timezone
  reaches the query engine, and reports include per-profile deltas plus a conservative
  paired promotion gate. The legacy single `report` mode remains supported.
- Add host-authoritative calendar timezone grounding to personal-memory planning.
  `PersonalMemoryQueryRequest`, the query engine, and `DoppelClient` accept
  `calendar_timezone` as UTC, a bounded fixed offset, or an available IANA zone.
  Explicit numeric dates resolve at local noon and month/year spans at local calendar
  boundaries before conversion to UTC. The binder canonicalizes provider-supplied
  points and closed spans while leaving one-sided ranges Planner-owned. Reference
  Planners move to v13/v2 and deterministic Planners to v6/v2; v1 Draft/Plan wire
  shapes and the default v1 path remain unchanged.
- Give the 240-query relation dataset independent v2 operation/time-view gold rather
  than deriving it from legacy intent, and add a separate generated 72-case matrix
  covering every lookup/list/count and temporal-view combination. The paired runner
  now evaluates 312 cases per arm and includes operation-suite completion, coordinate,
  count-memory-type, and exact-semantics metrics in its promotion gate.
- Add an opt-in personal-query Plan v2 beside the unchanged v1 Planner and wire
  models. V2 separates retrieval `operation` (`lookup`/`list`/`count`) from
  `temporal_view` (`unbounded`/`current`/`prior`/`planned`/`as_of`/`interval`),
  allowing combinations such as an exact count over a historical interval without
  overloading one intent label. The query engine executes both schemas, retains a
  deterministic legacy-intent projection for observability, and applies lifecycle,
  temporal, semantic, relation, evidence, reranking, and exact-count gates from the
  orthogonal fields. Existing v1 plans, fingerprints, defaults, and
  serialized field shapes remain unchanged; V2 remains opt-in pending a paired
  240-query evaluation.
- Add a repository-only paired v1/v2 Planner ablation over those same 240 queries.
  It fixes identical provider settings and per-arm call ceilings, separates raw
  caches by complete schema/prompt identity, records immutable plans/reports with
  hashes, stops on input drift, and applies a no-regression promotion gate across
  operation, temporal, subject, entity, relation, and relation-type planning. V2
  reports expose authoritative orthogonal metrics by partition/category while
  retaining the legacy intent projection only as an explicitly labeled diagnostic.
- Move the relation-Planner benchmark cache from processed query drafts to the
  raw `StructuredOutputModel` boundary. The new versioned namespace stores every
  successful provider JSON object, including output that later fails Planner
  validation, and re-runs current projection, calendar grounding, subject binding,
  and strict validation on every hit. Provider calls—not Planner executions—consume
  the hard budget. Legacy final-draft files are never read, malformed envelopes fail
  closed to a live miss, atomic writes and content-addressed request/model binding
  remain, and reports identify cache kind/schema/namespace explicitly.
- Let the Reference personal-memory Planner project one narrowly incomplete
  `as_of` draft long enough for host-owned explicit-calendar grounding, then
  strictly revalidate the complete draft before returning it. This changes no
  prompt, schema, or provider generation identity: only a missing `as_of` coordinate
  may be temporarily admitted, while invalid, ambiguous, relative, reversed, or
  otherwise malformed time structures still fail closed.
- Preserve Planner-selected ontology types as soft Graphiti relevance in opt-in
  candidate-union mode. A suggested type match may rank an already authorized
  candidate, while a type-conflicting lexical edge is kept observable at the
  adjacency score floor. Legacy `relation_gate` still forces provider-suggested
  types below its evidence threshold, host `required_relation_types` remain the
  only hard type authority, and a configured relation reranker remains able to
  supply an independent match.
- Add a separate draft v2 personal-relation retrieval dataset: 72 authoritative
  memories, 240 queries, 12 exact owner scopes, fixed dev/held-out/adversarial
  partitions, same-entity cross-owner collisions, time transitions, negated
  predicates, unknown entities, and context-without-proof cases. Every query carries
  complete corpus-wide 0/1/2 relevance judgments so future runs can report nDCG
  without treating missing labels as irrelevant. A deterministic checked-in generator,
  semantic integrity gates, and annotation notes keep it reproducible. Direct evidence
  is checked against relation, entity, and query time, while forbidden evidence must
  remain grade 0. Explicit direct/context/empty retrieval expectations keep useful
  context recall separate from downstream answer abstention; the dataset remains
  explicitly unfrozen pending independent review.
- Add a domain-neutral explicit-calendar grounding layer between Planner output and
  trusted plan binding. One numeric full date or month/day becomes an `as_of` point;
  one numeric calendar month or year becomes a closed interval. Existing provider
  coordinates are normalized under the host calendar policy, while contradictory
  lookup/current/history shapes are canonicalized before temporal gates. Count/list/planned intent stays
  intact, historical interval aggregation can inspect eligible inactive evidence,
  and relation retrieval receives the interval instead of silently querying `now`.
  Invalid or multiple date expressions remain Planner-owned rather than guessed.
- Bump the deterministic personal-memory Planner to v5. It shares the same calendar
  parser, contains no entity/domain vocabulary, and removes recognized calendar text
  from lexical search text without introducing benchmark-specific query rules.
- Split replay-benchmark attribution between the immutable source Planner draft and
  the effective bound plan. Planner hard gates continue to expose original intent,
  temporal, entity, relation, and hard-filter misses, while retrieval attribution
  uses the post-binding structure. Reports count calendar-grounding recoveries rather
  than incorrectly crediting those repairs to the source Planner.
- Add an opt-in, bounded personal-memory reranking protocol after authoritative
  Store reload and all scope, subject, authority, lifecycle, temporal, score, and
  optional evidence gates. It exposes only the raw question, opaque request-local
  IDs, and authorized content; it can reorder but never add/remove candidates or
  participate in exact counts. Strict score binding, timeout/input bounds, stable
  ties, content-free diagnostics, and baseline-order fallback are covered by tests.
- Wire the local benchmark cross-encoder into that runtime protocol and record a
  paired PostgreSQL + pgvector + Neo4j/Graphiti + CUDA run. On the draft v1.5
  relation set, candidate membership stayed identical while Recall@1 changed from
  0.88 to 0.92 and MRR from 0.91 to 0.93; p50 changed from 97.608 ms to 204.837 ms.
  All scope, temporal, provenance, and inactive-record safety counts stayed zero.
- In opt-in candidate-union mode, preserve independent semantic recall when a
  structured non-count Planner draft has entity/relation anchors but an empty
  `search_text`: the raw question is used only for bounded candidate discovery and
  the fallback is surfaced in warnings/traces. The bound plan and all authority,
  temporal, lifecycle, provenance, score, and Store-reload gates remain unchanged;
  legacy `relation_gate` behavior is unchanged.
- Add an opt-in `FallbackPersonalMemoryQueryPlanner` that tries a primary planner
  exactly once and then invokes a host-chosen fallback. Fallback use is preserved in
  the bound plan explanation with content-free planner/error identities; raw provider
  errors are neither copied nor logged. Scope, subject, and relation authority remain
  bound by the query engine.
- Correct two post-run relation benchmark labels and bump the draft dataset to v1.5:
  “last year” now carries its complete calendar interval, while asking when a passport
  was renewed is an enduring event lookup rather than a superseded-state query.
- Clarify Reference personal-query Planner v12 around mutable present state versus
  enduring attribution/provenance, explicit points versus historical intervals, and
  minimal relation-type candidate sets. Unknown provider fields are projected out as
  inert at the Reference boundary without weakening validation of recognized values;
  all authority and scope binding remains host-owned.
- Bump the draft relation dataset to v1.4 after a full intent/temporal-shape review.
  Calendar months and years now use interval gold, the reviewed “after” query keeps
  both legitimate lower-day readings, and scoring v3 reports interval presence and
  boundary accuracy instead of accepting an arbitrary representative point.

- Add an offline whole-candidate reranking replay benchmark. It validates exact
  source/dataset identity, sends opaque candidate IDs, requires a full score
  permutation, never changes candidate membership, and compares raw questions
  with separately reported model-suggested Planner context. No runtime default
  changes and no external LLM calls are implied by this diagnostic.

- Clarify Reference personal-query Planner v11 intent semantics: past-tense
  attribution/origin questions remain ordinary lookup unless the user requests
  a prior state or historical occurrence. Add dataset validation for lookup gold
  that incorrectly accepts history despite exclusively current/timeless targets;
  correct seven attribution/origin queries and bump the relation draft to v1.3.

- Add opt-in `candidate_fusion="union"` for personal retrieval and a matching
  ablation CLI switch/report field. Keep independent vector candidates when
  relations are soft hints; preserve explicit host relation constraints and
  fail closed on unavailable hard-constrained relation lookup. Defaults, weights
  and legacy plan fingerprints are unchanged. Live quality gains are unmeasured.

- Add explicitly annotated, pool-relative nDCG@5 to retrieval benchmarks with
  unavailable/coverage accounting; preserve legacy exclusions, empty-output
  metrics, safety gates and unannotated dataset fingerprints. Correct unnamed
  single-index source contribution and expose relation attribution by planner
  mode. No retrieval algorithm or dataset gold changes in this step.

### Optional evidence verification

- Add an opt-in, exclusion-only evidence-support gate to personal queries, with
  a provider-neutral protocol and Reference StructuredOutputModel adapter in
  `doppel_memory.evidence`. Defaults and ranking weights remain unchanged.
- Bound candidate count, input characters, batch size and total timeout; validate
  all decision IDs and fail closed on provider/format failures. Return structured
  verification status and content-free diagnostic events. Exact counts are
  explicitly unsupported when verification is enabled.
- Add offline contract and engine regression tests. These do not establish real
  model quality; paired live evaluation is required before default enablement.

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

- Add opt-in bounded personal-query traces (`trace_limit=0` by default) on engine
  query/execute and client query methods, with provisional trace models and an
  optional result field. Engine source/reload/qualification/ranking events preserve
  ranking behavior and plan fingerprints; identifiers from foreign or orphan
  candidates and raw text/errors are not copied. The benchmark exposes
  `--query-trace-limit`; index-internal rejection coverage is explicitly excluded.
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
