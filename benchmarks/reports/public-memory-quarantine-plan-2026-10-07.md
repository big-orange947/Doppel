# Opt-in evidence quarantine: preregistered cached replay

This opened LongMemEval diagnostic changes only the generic host acceptance policy,
not the corpus, questions, labels, model, analyzer prompt or authority rules. It
does not repair model understanding or constitute a retrieval/QA/AML score.

- Preserve the existing manifest and source hashes, three diagnostic histories,
  original role/order/timestamps and all 147 chunks. Reserved groups remain unrun.
- Keep ReferencePersonalMemoryAnalyzer v8, Miner v1, deterministic consolidation
  v3, DeepSeek development transport and the local 512-dimensional BGE profile.
  No new request instructions or question-specific rules are introduced.
- Default `evidence_error_policy="fail_batch"` and its old configuration/plan
  fingerprints remain unchanged. Explicit `quarantine` uses a new journal/run
  directory and PostgreSQL schema; never migrate, reset or overwrite the failed
  old profile. Use `public-memory-ingestion-quarantine-v1` for the new profile.
- Quarantine only closed, per-draft evidence violations: unknown reference,
  excluded source actor, mixed source actors, subject/source mismatch or untrusted
  subject identity. Preserve citations, source attribution and authority. Never
  select a convenient citation or change an assistant into owner evidence.
- Persist rejection count, reason counts and original schema-valid analysis-list
  index (not raw JSON ordinal). Each draft records its first failing evidence gate.
  Do not persist rejected content, IDs or exception text in these diagnostics.
- Reconcile valid drafts with accepted proposals plus low-confidence, duplicate
  and evidence-rejected drafts. An all-rejected batch retains raw source records
  and completes with zero accepted proposals and explicit rejections; it is not
  evidence that the source was noise or that the model understood it correctly.
- Schema, provider, storage/index and maximum-draft failures still stop the run.
  Quarantine requires subject/source matching and durable rejection accounting.
- First run: process only the eight previously returned provider responses using
  strict read-only parent cache access and cache-only mode. No key read, paid
  request, parent cache mutation or copying raw outputs to the new cache.
  Missing/malformed/mismatched envelopes fail closed instead of calling a model.
- Check completed stages, raw/derived/governance Store records, source resolutions,
  rejection partition and provider ledger separately. Store provenance checks do
  not establish semantic truth. Retain the original eighth-chunk failure.
- A later bounded live continuation may process the same remaining chunks in
  order with the new journal, the same parent cache and at most 147 new attempts.
  New-profile usage excludes the old eight calls; report both explicitly when
  discussing cumulative cost. No automatic retries or inference of missing usage.
- Do not run retrieval or a reader on partial histories or publish quality metrics
  from this ingestion-only stage. The model profile is not AML compliant yet.

This policy is tested on synthetic sources before inspecting cached execution
results. It is an opt-in reliability/observability feature, not benchmark tuning.
