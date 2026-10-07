# Public-history extraction pilot, before live responses

This is the next stage of the existing opened LongMemEval diagnostic, not a new
blind test, AML submission or retrieval/QA result. Freeze this configuration before
reading model responses. Do not replace a failing chunk or loosen evidence gates.

- Keep the original cleaned-S source SHA-256, manifest and three diagnostic
  histories: 145 sessions, 1,513 nonblank transport messages, 147 Add chunks.
  Reserved histories are not run. All chunks follow original supplied order;
  no source is selected by question, answer, labels or category.
- Persist both roles as attributed raw events. User is explicitly bound to owner;
  historical assistant is agent, with `agent_output` authority, never owner fact.
- Use existing ReferencePersonalMemoryAnalyzer v8 / PersonalMemoryMiner v1,
  DeterministicMemoryConsolidator v3 / ProposalWriter / IndexMaintainer, actual
  PostgreSQL Store and pgvector with the same local 512-dimensional
  BGE-small-zh-v1.5 / FastEmbed identity as the preceding comparison.
- Endpoint/model are explicit CLI inputs, not inferred from a key. The initial
  development profile is DeepSeek `deepseek-v4-flash`, json_object, temperature 0,
  thinking disabled, `max_tokens=8192`, 120-second timeout, no automatic retries.
  This does **not** satisfy the later AML unified-model profile.
- The benchmark host explicitly confirms attributed proposals after the existing
  evidence gates. This is not truth verification or a change to the core candidate
  default. Minimum confidence .75; both owner/agent input allowed; require one
  source actor and matching draft subject. Max 100 drafts per chunk, with excess
  causing a failure, not truncation. The transport bound remains 20 messages.
- The first invocation may attempt at most three not-yet-completed chunks.
  Previously completed chunks are revalidated/index-repaired but do not count as
  new chunks. First failure stops the prefix; later chunks cannot skip it.
  A later `--max-new-chunks 0` replay checks only the completed prefix, reads no key
  and configures cache-only model access, so it cannot make a paid model request.
- Shared durable ledger: at most 147 provider attempts for this fixed extraction
  budget. Raw-output cache survives invalid model drafts; successful responses
  are not billed again on normal replay. Failed attempts are not refunded. This
  is an attempt/JSON-byte bound, not an exact-billing or total-token guarantee.
- New profile-specific `public_memory_*` PostgreSQL schema, separate from the raw
  baseline, and an ignored local run directory. Never reset/delete an earlier
  schema, database, source, report or Docker volume.
- Persist query-free source maps and the full non-secret plan before extraction.
  Bind provider/miner/analyzer/consolidator/embedding identities. Changing the
  profile needs a new run directory, not silently overwriting the prior binding.
- Persist per-chunk valid/invalid schema observations and saved proposal-plan
  low-confidence/duplicate counts. Missing observations remain unknown, not zero.
  Record complete/pending stages separately. Replayed observations replace one
  chunk's counts, not increment them. On evidence-binding failure, valid schema
  drafts may exist without any saved/persisted proposals: report both honestly.
- Audit actual raw/derived Store records, roles, states and evidence resolutions.
  Provenance/actor checks do not establish semantic truth or answer relevance.
- Graph, natural Planner, search, reranking and answer reader remain unexecuted in
  this ingestion runner. No new recall/QA score or publication acceptance follows
  from an ingestion completion. Compare raw/derived/combined retrieval only after
  complete histories and verified indexing, then score a fixed reader separately.

The default CLI mode only builds a preflight report: no database, provider, key
access or model loading. Live mode reads secrets exclusively from named process
environment variables. Run output and local caches may contain private generated
memory text; they remain under ignored `data/`, not in Git.
