# Multi-instance reliability V2 — preregistered repair gate

V2 is frozen after the immutable V1 failure and before the first V2 live result. It
keeps the same 128 logical records, 512 simultaneous write attempts, four independent
instances, eight exact scopes, duplicate ratio, lifecycle races, vector workload,
Graphiti path workload, restart checks, cleanup rules, and latency thresholds.

Two versioned changes address evidence exposed by V1:

1. Doppel now takes a database-global PostgreSQL transaction advisory lock around
   pgvector extension discovery and creation. A minimal live reproduction proved that
   four simultaneous first-use initializers previously produced three
   `pg_extension_name_index` unique violations; the fixed implementation completed
   four of four initializers successfully. The existing vector-profile migration lock
   remains separate and unchanged.
2. Each of the four benchmark instances uses a two-connection pool, for a total
   connection budget of eight. This is not a lighter request workload: all 512 calls
   are still scheduled at once and their end-to-end latency includes pool waiting.
   Diagnostic trials on the same workload found that larger pools amplified unique-key
   contention: pool sizes 8/12/16 per instance produced roughly 606/425/306 ops/s,
   while two per instance produced roughly 1,058 ops/s and 440 ms p95. V2 freezes the
   contention-aware budget and retains the original 500 ms p95 gate.

V2 also records every vector failure with stage, exception type, and bounded message,
adds an unclassified-failure hard gate, and reports write wall time and throughput.
These are observation changes only; they cannot convert a failed operation into a
pass. All V1 correctness, isolation, stale-edge, reconciliation, restart, latency, and
cleanup thresholds remain in force.

As in V1, local embeddings are the only model execution. External HTTP, LLM calls, and
provider tokens must remain zero. Graphiti LLM-driven concurrent ingestion stays out
of scope and will require its own budgeted protocol. The first V2 result remains valid
evidence whether it passes or fails and must be preserved before any further change.
