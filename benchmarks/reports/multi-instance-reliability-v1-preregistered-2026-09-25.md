# Multi-instance reliability V1 — preregistered live gate

This protocol is frozen before its first live result. It evaluates a missing production
claim separately from retrieval quality: whether multiple Doppel instances can share
one PostgreSQL authority, pgvector projection, and Neo4j relation index without losing
idempotency, isolation, lifecycle consistency, provenance, or restart recovery.

The default deterministic workload uses four independent PostgreSQL connection pools,
four pgvector adapters, four Neo4j drivers, eight exact owner scopes, 16 logical
records per scope, and four concurrent attempts per logical event. This produces 128
logical records and 512 writes. The same idempotency keys intentionally repeat across
different scopes to prove that deduplication does not cross tenant boundaries.

After concurrent schema initialization and writes, the runner verifies exactly one
physical row per scope/key, indexes all authoritative records with local
`BAAI/bge-small-zh-v1.5`, concurrently replays index upserts, and performs exact-scope
semantic searches. It then seeds two typed `HELD_BY` relations per scope in run-scoped
Neo4j groups and performs four rounds of concurrent path reads through independent
drivers.

For lifecycle pressure, two Store instances race the same expected-state transition;
exactly one must win. A separate relation record is expired while its graph edge is
left intact, and another record is hard-deleted. Graph retrieval must suppress the
stale relation by reloading the authoritative Store. Two independent index maintainers
then reconcile every scope. Finally all PostgreSQL pools are closed and recreated;
semantic and still-live relation queries must survive restart.

Hard gates require zero migration/write/idempotency/duplicate/isolation/state-race,
vector/replay/search, graph-path/stale-edge, reconciliation, restart, membership, and
cleanup failures. Warm workload p95 must stay at or below 500 ms for Store writes and
1,000 ms for vector and graph searches. The 20-record answer-context benchmark is a
separate quality track; this infrastructure gate does not score answer sufficiency.

The benchmark resets only the dedicated `doppel_ablation` PostgreSQL database and
deletes only its generated Neo4j group IDs. It uses local embeddings, makes zero
external HTTP and LLM calls, and never persists credentials. Graphiti/LLM concurrent
episode extraction is explicitly outside V1: this run tests typed relation reads and
authoritative stale-edge revalidation without conflating infrastructure reliability
with provider behavior or token budget.

The first live result remains evidence whether it passes or fails. If it exposes a
defect, this V1 result must be preserved and any fix evaluated under a versioned V2
contract rather than overwriting the first observation.
