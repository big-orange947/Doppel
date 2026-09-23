# Hybrid path-candidate assembly V2: corrected label contract

Date: 2026-09-23

Runner: `doppel.hybrid-path-candidate-ablation.v2`

The V1 opened run is preserved in
[`hybrid-path-candidate-first-live-2026-09-23.md`](hybrid-path-candidate-first-live-2026-09-23.md).
It exposed a benchmark-contract error: a valid first-hop memory was forbidden by the
path-only gold label because it could not prove the complete two-hop answer, even
though Doppel's assembled output exposes candidates with `answer_support=unassessed`.

V2 changes no retrieval, ranking, scope, time, Store, pgvector, or Graphiti code. It
changes only the generic label projection before a second opened run:

- a path-forbidden memory remains **hard forbidden** when it is outside the exact
  scope, inactive at the requested instant, not confirmed personal memory, Agent
  output, missing from the authoritative Store, or lacks evidence provenance;
- a confirmed, exact-scope, active, human-authoritative, provenance-bearing memory is
  **related incomplete context** when it cannot prove the complete path. It is counted
  with candidate noise, not as a security or temporal failure.

The projection does not inspect query IDs, entity names, relation types, categories,
or natural-language words. It therefore cannot special-case the opened orphan query.

All V1 profile definitions, runtime requirements, and gates remain fixed. In
particular, the assembled profile must match or exceed both individual branches on
evidence recall and complete-evidence rate; it must have zero hard-forbidden hits and
scope leakage; Store revalidation and path-budget omission counts must stay zero; and
both backend cleanups must succeed. Candidate noise/related-incomplete context remains
diagnostic. External HTTP and paid model use must remain zero.

Because the corpus and the V1 result are already opened, a passing V2 run is still a
development baseline, not publication evidence. It only validates the corrected
candidate-versus-proof contract before a future sealed combined corpus.
