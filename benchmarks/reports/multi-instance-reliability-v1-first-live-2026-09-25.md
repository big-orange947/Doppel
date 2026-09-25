# Multi-instance reliability V1 — first live result

This is the immutable first live result for the preregistered V1 multi-instance
reliability gate. It ran from commit
`0b3e99f` after the runner, workload, and thresholds were committed. The result failed
two gates and is preserved without reinterpretation or rerun.

## Reproducibility

- workload fingerprint:
  `6b93af919c506f65f466314da7f539ede4fe641ec9af00a222d0731457cd40fd`
- report payload hash:
  `0cac99c31446c667dd639515b8a261f7d36f5c92015cea3884767c48cd9bcba4`
- raw JSON file SHA-256:
  `b7f5cee8c88e1ed55e87ed2964e414b960b796199aa4b82ecf9771d7f6187bb2`
- raw local result: `data/doppel/multi-instance-reliability-v1-first-live.json`
- instances / scopes: 4 / 8
- logical records / concurrent write attempts: 128 / 512
- PostgreSQL / pgvector: dedicated `doppel_ablation` / extension 0.8.6
- embedding: local `BAAI/bge-small-zh-v1.5`, 512 dimensions
- graph: four local Neo4j drivers through typed Graphiti relation paths
- external HTTP / LLM calls / provider tokens: 0 / 0 / 0
- fixture cleanup: PostgreSQL and Neo4j both complete, zero cleanup errors

## Passed correctness gates

The burst produced exactly 128 created writes and 384 scope-local duplicates. There
were zero write errors, idempotency violations, physical duplicate rows, scope leaks,
or optimistic transition-race violations. Each of eight expected-state races had one
winner and one conflict.

Vector search misses, graph path misses, stale graph hits, reconciliation failures,
and restart failures were all zero. Expired memories remained in the authority but
were removed from the vector projection; hard deletes cascaded out of pgvector; stale
Neo4j relations were suppressed by authoritative Store reload. After lifecycle repair,
the index contained exactly the expected 104 active records. Restarted pools could
search both pgvector and still-live graph paths.

## Failed gates

1. `vector_failures=3`, against a threshold of zero. The final index state is correct,
   replay mutations are zero, searches pass, reconciliation passes, and restart passes.
   V1 aggregated initialization and replay exceptions into one counter and did not
   retain their types or messages, so this result cannot honestly name the failing
   operation. V2 must add stage-specific failure observations before trying to fix the
   underlying race.
2. Store write p95 was 781.1 ms, against the preregistered 500 ms ceiling. Median was
   710.6 ms and p99 was 783.4 ms. This workload deliberately launches all 512 attempts
   at once through four eight-connection pools, so the number measures saturated burst
   queueing plus database work, not steady-state single-request latency. It still
   fails the exact V1 contract and must not be waived after observation.

Vector search passed at p50/p95 33.5/37.1 ms. Typed graph path search passed at
p50/p95 395.3/423.8 ms.

## Conclusion and V2 boundary

V1 provides positive evidence for database-level idempotency, isolation, lifecycle
races, Store-authoritative derived-index filtering, reconciliation, and restart
recovery under a concurrent workload. It does **not** establish a passing
multi-instance production gate because vector initialization emitted three unclassified
exceptions and burst write latency exceeded the frozen target.

V2 may add failure-stage/type/message accounting, operation throughput, pool-wait
diagnostics, and a versioned connection-pool or Store implementation change. It must
not edit this report, relabel the V1 failures, or present a tuned V1 rerun as another
first result.
