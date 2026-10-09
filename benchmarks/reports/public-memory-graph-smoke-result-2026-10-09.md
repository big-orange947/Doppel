# Real committed-memory Graphiti writer: integration smoke

This closes the frozen three-record smoke plan. It is not a LongMemEval answer
score, a natural-language recall measurement, or an AML result. No benchmark
question or reference answer was provided to graph authoring or probe queries.

## Real authoring and durability

At implementation `4509e4c`, the production `GraphitiSemanticIndex.index_record`
projects all three selected committed records through real Graphiti 0.29, Neo4j
and the injected DeepSeek chat/completions bridge. Episode names/fingerprints and
source versions match the authoritative Store, and each Episode lists and links
to at least one actual graph edge. Two records have a non-fallback edge; the third
has a fallback projection. The graph data is retained for subsequent evaluation.

The first invocation performs three index writes and eight successful provider
attempts, with zero failed/interrupted attempts, retries or missing usage:

| Observed usage | Value |
| --- | ---: |
| Input tokens | 19,112 |
| Output tokens | 403 |
| Total tokens | 19,515 |
| Cached input tokens | 2,560 |
| Cache-miss input tokens | 16,552 |
| Canonical request bytes | 72,199 |
| Durable attempt ceiling | 48 |

These are provider-reported tokens and canonical request bytes, not an exact
currency charge or an enforced token cap. Keys/credentials are not persisted.

Rerunning the identical frozen plan in the same directory rechecks all three
projections, performs **zero writes and zero new provider attempts**, and leaves
the ledger at eight. This is checkpoint-based no-call resumption, not an LLM cache
hit experiment. The API-key environment remains present; this live CLI invocation
is not a key-free replay (the independent bridge cache test covers key-free use).

## Production retrieval probe

At `206e8bb`, a read-only source probe calls production
`GraphitiRelationIndex.search_relations` and `search_relation_paths` against the
two real non-fallback relations. Both are returned with the expected
Edge → Episode → memory ID provenance. One-hop paths return the source memories;
wrong-subject requests return none, and the other exact scope cannot return either
source memory. The driver suppresses schema initialization and constructs no
provider/embedder; the probe performs zero provider calls and zero data writes.

The query text, source-entity anchor and relation type deliberately come from
stored edges. Therefore **2/2 probe success is connectivity, not recall@k, natural
planning, multi-hop reasoning, or correctness of the graph's extracted facts**.
It does not independently prove that every metadata field was semantically
extracted correctly.

All invocations verify the unchanged full Store snapshot:
`11aab45f1bdfaebeea23bee822e53e5cdd94aef24f68bb020d90e9eda35e9cc3`.
There are 9,744 eligible memories in the fifty-history corpus; three indexed
records never certify full-corpus readiness. No Store/vector contents, old scores,
reserved histories or `uv.lock` were modified.

## Artifacts

Ignored local artifacts (raw file SHA-256, not semantic-score hashes):

| Artifact | SHA-256 |
| --- | --- |
| `data/doppel/public-memory-graph-smoke-live-v1.json` | `2474ebad3838cb44cea811322e3db6ff5e0ceaf51444e46de7a6fc6fd85949bb` |
| `data/doppel/public-memory-graph-smoke-resume-v1.json` | `f974c486ef2546b4699b7391e647ed3aa8b6a25ce266ad8d33e3331a0f4f331a` |
| `data/doppel/public-memory-graph-smoke-probe-v1.json` | `14db52a7738cb32e90903d778692681ebea26d3d966993adfe49f6e096f036d2` |

Durable smoke budget identity:
`4e3e74ca74e0696974068ebfb8ccd8b86c14cc973c6f9e84d91cbec60944a1d7`.

Verification: 1,398 tests pass, 33 skip, three subtests pass. Ruff passes across
the repository; Pyright with the actual venv reports zero errors in the new
transport, backfill and probe modules. The full test run emits one upstream
Graphiti/Pydantic deprecation warning, not a test failure.

## Next stage, not a completed result

The separately frozen first-history plan selects all 210 eligible memories in
the first ingestion scope, reusing the three completed projections. Its live
backfill has been launched with its own 1,500-attempt/8,000,000-byte ceilings and
durable journal. Do not interpret this launch as a completed scope or a new QA
score. A complete scope-level projection audit, source-schema binding and a fixed
highest-configuration context/Reader protocol are still required before the first
natural-query answer comparison. Full fifty-history indexing/evaluation remains
unfinished. Actual graph authoring can drop malformed entity references; fallback
coverage must be separated from useful rich relations in the subsequent report.
