# Multi-instance reliability V2 — first live result

This is the first live result for the preregistered V2 repair contract, run from
`7c5900a6dbd96cd1fcb675ab3ef7271d5f37537c`. It passed every frozen correctness,
recovery, cleanup, and latency gate. V1 remains the immutable failed first observation;
this report does not replace it.

## Reproducibility

- workload fingerprint:
  `46c392122ba4b4f516f2619e05e5279baf253a0c9848b55488c92a55783f9d94`
- report payload hash:
  `ed161db3b094f3a2cb5ead08dc25414fdae0ded90517ebe23bea9814bd885af4`
- raw JSON file SHA-256:
  `765f1f808270ac665c091502852c7bec81fc39be59002695227d35a156d1e7fa`
- raw local result: `data/doppel/multi-instance-reliability-v2-first-live.json`
- instances / connection budget: 4 / 8 total (2 per instance)
- scopes / logical records / simultaneous writes: 8 / 128 / 512
- created / database-deduplicated writes: 128 / 384
- PostgreSQL / pgvector: dedicated `doppel_ablation` / extension 0.8.6
- embedding: local `BAAI/bge-small-zh-v1.5`, 512 dimensions
- graph: four local Neo4j drivers through typed Graphiti relation paths
- external HTTP / LLM calls / provider tokens: 0 / 0 / 0
- credentials persisted: false
- PostgreSQL and Neo4j fixture cleanup: complete, zero errors

## Correctness and recovery

All checks passed with zero migration or write errors, idempotency violations, physical
duplicates, scope leaks, transition-race violations, vector failures, unclassified
vector failures, vector replay mutations, vector search misses, graph path misses,
stale graph hits, reconciliation failures, restart failures, or cleanup errors.

Four simultaneous first-use pgvector initializers completed without the three
`pg_extension_name_index` races observed in V1. The shared vector profile accepted two
full concurrent replays as skips. Eight expected-state races each produced exactly one
winner. Expired records were removed by independent reconcilers, hard deletes cascaded
out of pgvector, and graph edges whose authoritative records became inactive were
suppressed despite remaining in Neo4j. The vector index contained exactly the expected
104 active records before cleanup. New PostgreSQL pools recovered vector searches and
still-live graph paths after restart.

## Performance

| Operation | p50 | p95 | p99 |
|---|---:|---:|---:|
| 512-write burst, end-to-end | 214.3 ms | 303.3 ms | 310.7 ms |
| exact-scope pgvector search | 33.1 ms | 37.2 ms | 37.9 ms |
| typed Graphiti relation path | 266.9 ms | 278.2 ms | 281.9 ms |

The complete write burst finished in 339.6 ms, or approximately 1,508 operations per
second. End-to-end call latency includes async pool waiting. Relative to V1's four
eight-connection pools, the contention-aware eight-connection total budget reduced
write p95 from 781.1 ms to 303.3 ms while retaining the same 512 simultaneous calls.
This supports a deployment rule, not a universal magic number: size the total database
connection budget across all Agent instances; do not multiply a large per-process pool
by the worker count.

## Scope of the claim

V2 closes the concrete multi-process-style gaps caught by V1 for PostgreSQL authority,
pgvector initialization/replay/reconciliation, typed Graphiti reads, authoritative
stale-edge filtering, and process-style pool restart. It is a deterministic local burst
test, not a long-duration soak or distributed network-partition test. It also does not
exercise concurrent LLM-driven Graphiti episode extraction. Those remain separate
future evidence tracks and must not be inferred from this pass.
