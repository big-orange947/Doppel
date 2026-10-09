# First diagnostic history: complete graph projection plan

Freeze before live calls. This is a source-only graph-index preparation run, not
a LongMemEval answer score, an independent blind test, or an AML result.

## Selection and unchanged inputs

Use the same completed fifty-history ingestion, exact Store snapshot
`11aab45f1bdfaebeea23bee822e53e5cdd94aef24f68bb020d90e9eda35e9cc3`, existing BGE
512-dimensional vectors and production `GraphitiSemanticIndex.index_record`.

The first ingestion scope contains 210 confirmed eligible personal memories.
Select the first 210 under the previously frozen scope/created-at/memory-ID order.
Do not inspect questions, answers, required evidence or query successes to select
records. The three completed smoke projections are revalidated and reused. Only
graph-derived data may be added; Store, vector contents and reserved histories
remain unchanged. No seeded fixture facts or case-specific rules.

## Explicit budget and durability

Separate run directory `data/doppel/public-memory-graph-first-history-v1` and
frozen preflight `data/doppel/public-memory-graph-first-history-preflight-v1.json`.
Maximum 1,500 provider attempts across all resumes, 500,000 canonical bytes per
request and 8,000,000 total canonical request bytes. These are ceilings, not a
request to spend the budget; no automatic retry/extension. Use the unchanged
DeepSeek v4 flash JSON-object bridge, temperature zero, thinking disabled and
8,192 output-token cap (respect smaller requested caps). Credentials stay in
process and are not written into any artifact.

Provider ledgers, content-addressed caches and exact record checkpoints persist.
One writer lock and one Graphiti coroutine. On failure retain diagnostics and
completed data; never silently turn a partial scope into full coverage. The large
scope may require more calls than the three-record smoke because deduplication and
temporal resolution become active. Token usage and unknown usage are reported as
observed, not extrapolated into an exact cost claim.

## Evidence before answer evaluation

For all 210 records require matching Episode metadata/version, Episode-listed
edges and actual Episode-linked edges. Report rich and fallback participation
separately: fallback completion does not mean useful relational extraction.
Verify production relation/path retrieval through the read-only source probe;
these intentionally source-anchored probes do not measure natural planning or
semantic fact accuracy. Confirm the full Store snapshot is unchanged.

Only after scope completeness should a separate frozen highest-configuration
natural-query pilot be prepared, including graph-schema binding, original-dialogue
backing, fixed packing/Reader budgets, and honest failure accounting. Do not label
the earlier vector-only 50-question results as this new configuration. Full-corpus
graph readiness remains false until all 9,744 eligible records are projected.
