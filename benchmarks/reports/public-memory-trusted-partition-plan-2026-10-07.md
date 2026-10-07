# Deterministic consolidation v4: trusted partition replay plan

Declare this generic source-grouping correction before cached/live execution.
It is an opened LongMemEval diagnostic, not a new blind corpus or AML score.

- DeterministicMemoryConsolidator v4 partitions both topic-keyed and unkeyed
  groups by exact trusted actor, authority and kind before existing semantic,
  temporal and revision grouping. Runner compatibility checks stay unchanged.
  Do not canonicalize kinds, promote authority, infer corrections or use specific
  topics, questions, source IDs or answer labels to decide eligibility.
- Homogeneous groups retain existing merge/conflict/correction behavior; sources
  outside a compatible group remain unchanged. Synthetic variation tests cover
  all three dimensions across topic/unkeyed duplicates, conflicts, corrections
  and historical revisions; forced incompatible plans must still be rejected.
- Keep the same frozen source, manifest, all 147 chunks, three diagnostic owners,
  original order/roles/timestamps and untouched reserved histories. Keep Miner
  quarantine, Reference analyzer v8, confidence .75, provider transport and local
  BGE/pgvector settings unchanged. Questions/labels never enter ingestion.
- Use new run directory `public-memory-ingestion-quarantine-v2` and plan-derived
  PostgreSQL schema. Preserve both older profiles and the pending chunk-37 journal,
  raw outputs and reports. New component version must not resume an old binding.
- First execute exactly the 37 previously observed responses with cache-only mode
  and two strict read-only parents (`public-memory-ingestion-v1/provider-cache`
  and `public-memory-ingestion-quarantine-v1/provider-cache`). No key read, model
  request, parent rewriting or copied cache contents. Missing/invalid envelope
  stops rather than silently rebilling.
- Audit completed/pending stages, proposal rejection partition, authoritative raw/
  derived/governance records and source resolutions. A fully processed prefix is
  still not complete histories; source validity is not semantic correctness.
- After cached regression passes, continue the unchanged remaining 110 chunks in
  order. New-profile attempt bound remains 147, no retries. Report new usage apart
  from old 37 responses / 188,915 reported tokens. Stop on a hard error; never skip
  a failing predecessor or change thresholds/profile in place.
- Verify restart replay and indexing/provenance before any downstream retrieval
  comparison. No graph, natural Planner, ranking or reader score is emitted by
  this ingestion runner. Local BGE/DeepSeek is not the AML academic model profile.
