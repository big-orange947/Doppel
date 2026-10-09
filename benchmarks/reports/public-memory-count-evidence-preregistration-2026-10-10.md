# Generic count evidence repair: freeze before development replay

Preserve the failed third natural-query receipt and its wrong answer. The numeric
engine count coincidentally matches gold but includes an unrelated event; it must
not be counted as a success. This next run is development on the same opened
question, not independent test data or a new denominator.

## Production rules and independent tests

- Episode without explicit `valid_to` is a point at its supplied valid/event time,
  or observation fallback when no event time exists. State without an end remains
  ongoing. Explicit episode durations remain supported. No textual date parsing
  or manual source metadata repair is added.
- A relevance-qualified free-text/entity/relation predicate cannot certify exact
  cardinality merely because Store was fully scanned. Report indeterminate with
  observed candidate/key counts, including for zero matches. Exact cardinality
  remains for complete explicitly structured sets with stable event keys.
- High-config count queries also obtain bounded, independently reranked raw
  dialogue and Store-revalidated source backing. Neither channel overwrites or
  certifies cardinality. Continue skipping top-k graph aggregation; raw agent
  messages keep their role/authority, and the observation cutoff and exact scope
  checks remain mandatory.

Synthetic cases use unrelated sensor/camera/opaque event fixtures: point vs state
vs explicit duration, empty/nonempty fuzzy predicates, stable-key deduplication,
missing validity rescued only by separate raw evidence, exact count retained with
source backing, and cross-scope raw rejection. Existing cardinality-only tests now
make their structural-set assumption explicit; natural-language count tests retain
the question and assert indeterminate. The old quality dataset/gold is unchanged
and now exposes **one count error** rather than having its expected answer edited.

No query keywords, activity name, benchmark IDs, reference values or annotated
positions enter production code. The missing extracted timestamp remains missing.
No new ingestion, schema authoring or graph projection is needed.

## Exact new preflight

Run directory `public-memory-count-evidence-regression-03-v1`, under ignored
`data/doppel/`. Preflight file SHA-256:
`9fa2498f5844fa566f101d2edd3158999186f607ed585729928dd461d7cd6ab0`.
Query plan fingerprint:
`107bd71797c803deddc1d76672929f6060fc4e5262eedb0e54ccb92b10f3903a`.
All 222 graph projections, Store corpus and 34760 vector manifests revalidate.

At most two natural-planner calls, one unchanged Reader v2, one reference-only
task judge and one citation judge; no retries or old checkpoint replacement.
Same source-only ontology, local BGE, CUDA ranker, 20 whole items/24000 UTF-8 bytes,
authority policy and caller clock as the failed run. Read gold only downstream of
retrieval/Reader. Report evidence coverage, raw/source roles, count status and
answer correctness separately; a correct answer cannot certify completeness.

After live execution, exact empty-key checkpoint/cache replay must add no requests.
Retain all warnings, usage and immutable failed parent. Independent observation/
question clocks and broader sample expansion remain separate subsequent changes.
