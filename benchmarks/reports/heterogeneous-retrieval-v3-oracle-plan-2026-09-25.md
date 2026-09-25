# Heterogeneous retrieval V3 — oracle count plan and entity coverage

V2 remains frozen and its dev result is preserved. No sealed or adversarial result was
opened on V1 or V2. V3 keeps the same 9,216 memories, 144 entities, 96 edges, 480 query
texts, evidence-role labels, owner-disjoint partitions, routes, times, and success
thresholds.

## Generic oracle count plan

Every query now carries three schema-bound oracle fields. They are empty for all lookup
queries. For the 48 count queries they declare:

- `oracle_search_text = ""`;
- `oracle_memory_types = ["episode"]`;
- `oracle_topic_keys = ["travel:completed"]`.

This is not a query-string special case. The runner copies structured fields from the
frozen query plan and has no branch for travel, cities, or case IDs. Exact count can
then perform its required exhaustive exact-scope scan and deduplicate stable
`event_key` values without relying on a bounded vector top-k. A future natural Planner
track must derive these fields from the question and will be scored separately; it
does not receive the oracle fields.

## Generic entity coverage reservation

Hybrid assembly gains an additive `literal_entity_reserve`, disabled by default. The
V3 highest-quality profiles set it to one within the existing five-record independent
reservation. It may promote only a candidate already accepted by retrieval, marked
with a literal binding to a Planner-supplied entity mention, reloaded from the
authoritative Store, and accepted by the same scope/lifecycle/authority filters. It
cannot add a candidate, infer answer support, execute a graph path, or bypass any
safety gate. Its discovery attribution is `entity_anchor_reserve`.

This generic coverage rule addresses the V2 observation that every named-object
related memory was present in the candidate window and final context but some were
pushed below rank 10 by an answer-relevance cross-encoder. The rule does not mention
buyer, holder, books, cameras, or any dataset value.

## Frozen identity

- suite: `doppel-heterogeneous-retrieval-zh-v3`
- version: `3.0.0`
- canonical dataset fingerprint:
  `ead91761f9da403c31c8b759d427c4551709daf7d29f35d26d786f94ec167f88`
- committed file SHA-256:
  `67a9e546a670ba745cc0d5ca6be3e7b566cab5898bcbdf015e3c779436f404c7`

V3 remains synthetic, author-known, and `publication_ready=false`. All original
first-run thresholds remain unchanged, and all-partition execution still requires
`--partition all --sealed-first-run` after this implementation is committed.
