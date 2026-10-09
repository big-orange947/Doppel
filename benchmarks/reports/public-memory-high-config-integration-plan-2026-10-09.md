# Full high-config composition: integration and corpus readiness

## Assessment change

The main evaluation must exercise an explicit, host-owned high-resource composition,
not call the raw/owner-memory/combined vector ablation the full Doppel system.
The existing fifty-question scores remain opened diagnostics; no score changes here.
Keep raw vector + the same cross-encoder as a strong baseline, and use component
removal only for attribution. Do not spend the next rounds optimizing every low-resource
combination or changing the labels of the existing answers.

## Runtime delivered

`doppel_memory.high_config.HighConfigRetrieval` is a new opt-in, module-only composition:

1. A host-supplied path Planner (normally Reference V7) is invoked once per request;
   its internal two model passes remain unchanged. Project its query fields to V2.
2. The real `PersonalMemoryQueryEngine` binds scopes/subjects and grounds calendar
   time, then executes lexical + semantic + single-edge candidates and memory reranking.
3. Search exact typed paths when planned; bounded ontology-governed exploration runs
   when explicit anchors exist. Both use the host-bound subject and time.
4. Recheck every path's Store support with the same production structural gate,
   including subject, lifecycle, authority and validity. Reject expired edge intervals
   independently of memory validity. Apply the unchanged evidence-rich V8 helper.
5. Independently retrieve/rerank confirmed raw dialogue, keeping assistant messages
   as `agent_output` rather than promoting them into owner facts.
6. Resolve derived citations through the host's durable event mapping and reload raw
   source text from Store. Missing/incorrect backing is visible, not replaced by summary
   text or an index candidate's text.

Exact counts stay on the engine's complete-scan path; top-k graph hits do not become
an exact count. The result keeps the base count/conflicts and separates derived
memory, paths, raw dialogue and source backing. Answer generation and byte-budget
context packing are outside this module. A downstream adapter must consume all
relevant channels; these separate lists must not be concatenated without a budget.

This newly wired profile is not identical to an earlier benchmark profile and has no
LongMemEval quality result yet. It does not change the stable default API, initialize
indices, insert graph fixtures, grant cross-scope access or certify corpus coverage.
Scorer fallback is reported; missing graph dependencies are not silently downgraded.

## Live readiness result

The existing diagnostic pgvector and Neo4j containers are healthy. The read-only
preflight binds the completed ingestion plan and all fifty diagnostic scopes, excludes
reserved scopes, reloads Store inventory and checks the existing vector fingerprints.

- Store: 34,762 records; before/after corpus fingerprints match.
- Existing vector profile: 34,760 entries; zero missing, unexpected or stale entries.
- Neo4j: **50/50 diagnostic scopes have zero Episodes and zero non-fallback edges**.
- Preflight status: blocked; exit 1. A running unrelated graph is not graph coverage.
- No LLM requests, embedding generation, data/index writes, or reserved-history runs.
  Store initialization may issue its existing idempotent schema DDL.
- Local artifact: `data/doppel/longmemeval-expansion-50-high-config-preflight-v2.json`.

## Next execution sequence

1. Materialize a derived Graphiti index from committed eligible memories, through
   the production Graphiti index writer and a budgeted, cached provider. Do not
   re-run the 2,420 historical ingestion chunks or create answer-targeted graph edges.
   Begin with a manifest-order bounded smoke, then resume the full diagnostic corpus.
2. Persist a coverage receipt binding Store fingerprint/version, graph projection,
   embedding identity, host ontology and completed per-record indexing checkpoints.
   Audit Episode-to-memory provenance and actual rich-edge participation. Graph index
   writes must be explicit, scoped and separate from retrieval's read-only accounting.
3. Wire a common bounded context adapter for the new structured result and the raw
   baseline. Freeze its policy, model identities and request/call limits before live
   answering. Preserve authority, source text, temporal fields and path grouping.
4. Run the fifty opened questions through the full path and the raw baseline with
   the same Reader/task scorer. Report answer accuracy, source coverage, graph
   participation, actual context/token usage and degradation separately. No oracle
   plans, domain-specific query shortcuts or missing-profile substitutions.
5. Check unopened reserved histories only after configuration freeze; later expand
   coverage and align the competition models/protocol. This is not AML readiness.

No new answer score is claimed by this integration/readiness step.

## Verification

- New synthetic runtime/readiness tests: 19 pass, with no paid provider calls.
- Final focused regression: 165 pass across the composition, preflight, stable
  query engine, path retrieval/assembly and V7 Planner tests.
- One full-suite run: 1,374 pass, 33 skip and 3 subtests pass. That run collected
  before the final two edge-validity/backend-failure tests were added; those two
  are included in the final focused run, not claimed as part of the full run.
- Ruff passes repository-wide; Pyright reports zero errors for the new runtime.
  The optional `neo4j` import in the preflight retains the environment's existing
  optional-dependency type-resolution limitation; it works in the actual venv.
- `uv.lock` remains the unrelated, unstaged pre-existing modification.
