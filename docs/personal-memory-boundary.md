# Personal memory ownership boundary

> Status: normative project direction for v0.9 and later.

Doppel is the authoritative personal-memory and personal-context core for a
long-running personal Agent. It is not a general Agent runtime and it does not try to
own every kind of state an Agent may use.

## What Doppel owns

Doppel owns durable claims **about a person and that person's evolving context**:

- personal facts, preferences, habits, relationships, experiences, plans, and
  commitments;
- current, historical, planned, cancelled, corrected, retracted, and conflicting
  interpretations of those claims;
- the actor, subject, authority, exact scope, validity interval, and recoverable
  evidence behind every claim;
- personal information promoted across explicitly authorized conversations or source
  systems;
- derived personal-memory materials that a host may choose to give to one or more
  Agents.

Chat is the first mature input adapter, not the definition of the domain. Files,
calendar entries, email, and tool observations may later provide personal evidence,
but Doppel stores only the durable personal claim or event plus a verifiable source
reference when copying the source payload would be inappropriate.

## What Doppel does not own

Doppel is not authoritative for:

- an Agent's short-term context window, workflow checkpoint, scratch state, or tool
  result;
- procedural lessons about how the Agent should execute tasks;
- complete documents or a general-purpose document knowledge base;
- the live state of calendar, email, task, finance, or other source systems;
- public or real-time knowledge;
- reply generation, routing, orchestration, or tool execution.

A host may combine those systems with Doppel. It must not create two independent
authorities that both extract and mutate the same durable personal claim. Cached or
rendered copies of Doppel memory remain non-authoritative and must retain their source
memory IDs.

## Authority and derived indexes

An InMemory, SQLite, PostgreSQL, or conforming custom Store is the authority for a
`MemoryRecord`. Semantic and graph systems are derived candidate indexes:

```text
personal evidence
       |
       v
authoritative Doppel Store
       |\
       | +--> pgvector semantic projection
       +----> Graphiti temporal/relational projection
                    |
                    v
              candidate memory IDs
                    |
                    v
       exact-scope Store revalidation
```

Graphiti is a positive temporal and relational enhancement, not a second source of
truth. A graph hit cannot establish scope, subject, authority, lifecycle, validity, or
provenance on its own. The query path must recover `(scope, memory_id)` and revalidate
the authoritative record before returning it.

Deterministic fallback graph edges guarantee discoverability and provenance when an
LLM does not emit a usable relation. They do not prove that rich relation extraction
succeeded and must remain distinguishable from model-extracted or structured imported
relations in quality reports and ranking features.

## Multi-Agent meaning

Multiple Agents may read the same person's authorized Doppel memory. Their workflow
state and procedural memory remain private to their runtimes unless a host explicitly
converts a durable human-related observation into a Doppel proposal.

Agent output is never promoted to a human fact merely because it appeared in a
conversation. The normal subject, actor, authority, evidence, scope, and policy gates
still apply.

## Retrieval direction

The highest-quality supported profile may require PostgreSQL, pgvector, Graphiti,
Neo4j, a high-quality embedding model, a query planner, and a reranker. Minimal setup
is not a v0.9 optimization target.

The full profile should obtain candidates from lexical, vector, temporal, and
relational retrieval, then deduplicate and reload every result from the authoritative
Store. Its value must be established by held-out and adversarial evaluation against
lexical-only, vector-only, graph-only, and ablated hybrid baselines.

Runtime code must not contain benchmark-domain dictionaries or import benchmark
fixtures. Generic structures such as current/as-of intent, interval constraints,
negation, correction, relation lookup, listing, and exact aggregation are allowed;
food, residence, travel, occupation, or fixture-specific query rewrites are not.
