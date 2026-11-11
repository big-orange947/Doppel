# Synthetic lifecycle on real PG/pgvector, 2026-11-11

Five separate processes exercised four synthetic scopes using the existing healthy
PG container after the user manually started Docker. No real-chat content was
exported or used; no paid LLM, downloads, graph build or old-data reset occurred.

- Dedicated retained schema: `doppel_lifecycle_20261111`.
- Journals: `data/examples/lifecycle-pg-20261111`.
- Index: `pgvector:dplv_bd356b4301164b5d`, existing offline 512d PyTorch BGE on CPU.
- Fixture analyzer: explicit scripted drafts, eight total logical analyzer calls.
- Real local embedding calls: 38. Paid LLM calls: zero.

| Stage | Fixture analyzer calls | Embedding calls | Audited Store records | Result |
|---|---:|---:|---:|---|
| seed | 4 | 14 | 10 | Initial state completed |
| interrupt | 3 | 10 | 20 | Expected writer failure; one stale inactive vector retained |
| resume | 0 | 4 | 20 | Remaining maintenance completed; stale vector removed |
| update | 1 | 6 | 24 | Third update completed; current evidence correct |
| replay | 0 | 4 | 24 | Same full Store fingerprint digest as update |

The 98 row audits are repeated observations across stages, not 98 independent
memories or test queries. The interrupted scope was deliberately incomplete and
was not counted as a clean manifest pass. Its current query returned only stable
background even though the expired source's vector was physically still present.

Cancellation/retraction left no current hit. The revised scope returned its latest
value. The temporary scope initially returned stable+temporary and later stable
only. Every completed scope's active fingerprints matched the vector manifests,
and inactive entries were absent. Query output was checked for exact requested
scope. This is not an adversarial multi-tenant benchmark.

The interrupt/resume Store digest was identical: maintenance repaired only derived
state. Update/replay digest was identical: no repeated extraction/governance writes.
Final digest: `e71831e695c149f852feecbda0265e8bddc8833d60b8e773bfb6dc3cea91a875`.
All 24 source/derived records remain for inspection; raw events and superseded or
expired audit snapshots are included in that count.

## Artifacts and validation

Five receipts: `data/doppel/lifecycle-pg-20261111-{stage}.json`.
Aggregate: `data/doppel/lifecycle-pg-20261111-summary.json`, containing all five
receipt hashes and runner source hash. `llm_calls=0` denotes generation calls,
while `local_embedding_calls=38` records local model computation.

Runner source SHA-256: `8ad987dd7903288eb353c42528fc77739a48617b4c288d945ca926ac4053cc44`.
Execution used the working tree based on `8f6baa8` with this new runner. Five new
offline driver/order controls and 91 related tests pass; full-repository Ruff and
runner Pyright pass. No full-suite rerun in this round.

The fault is synthetic at the IndexWriter boundary. Database/vector storage and
queries are real; actual network loss, server restart, concurrent writers and
Graphiti lifecycle behavior remain unvalidated here. No retrieval/answer score,
default promotion or release readiness is inferred from these four scripted cases.
