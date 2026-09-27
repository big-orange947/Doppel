# Heterogeneous retrieval V8 — semantic path-family completion plan

This protocol is frozen before the first V8 live result. V8 is an opened follow-up to
the preserved V7 failure, using the same author-known V4 topology-adversarial corpus.
It is not a sealed or publication-quality claim.

## Fixed evidence and hypothesis

V7 showed that whole-path semantic ranking correctly separated the holder branch from
the competing loan branch, but five correct one-hop holder prefixes scored above their
own correct two-hop city extensions. Since assembly atomically reserves only the first
path, the prefix consumed the reserve and the second-hop evidence fell to ranks 17–19.

V8 tests one generic composition rule: semantic ranking selects a branch family, then
the best semantic strict extension of a path moves immediately before that prefix.
This should retain V7's semantic discrimination between unrelated branches while
restoring the complete-evidence behavior supplied by V5's structural preference.

## Frozen algorithm and boundaries

The V7 semantic scorer and its text-only boundary are unchanged. After it returns an
exact permutation of bounded explored paths:

1. Each path is represented internally by its ordered edge-ID and direction signature.
2. A path is a strict prefix only when another already-retrieved signature begins with
   that exact signature and contains at least one additional hop.
3. The highest semantic-ranked extension moves immediately before its prefix.
4. All other paths keep semantic order. No path is added, removed, authorized, or
   filtered, and RRF rank contributions are recomputed from the resulting order.

The completion pass reads no relation names, facts, query text, query category, entity
names, scope/user/subject identifiers, memory IDs, authority, lifecycle, timestamps,
provenance, labels, or answers. Edge IDs are used only for equality/prefix topology
inside the already-authorized bounded result and never leave the process.

The existing semantic-path profiles remain in the report unchanged. The new evaluated
profile is
`assembled_semantic_path_family_exploration_hybrid_memory_reranking`; it receives no
oracle exact route. A separate membership counter must remain zero.

## Unchanged corpus and gate

- Dataset: `heterogeneous-retrieval-zh-v4.json`, fingerprint
  `0b0d0c8ab8aaf35350e465325540acc3b8c81f00496ed0d02901bc9f10e6a771`.
- Workload: all 480 queries, 9,504 Store memories, 384 entities, and 384 graph edges in
  48 exact owner scopes.
- Runtime: local PostgreSQL/pgvector, Neo4j/Graphiti, `bge-small-zh-v1.5`, and CUDA
  `bge-reranker-v2-m3`; zero external HTTP, LLM calls, and provider tokens.
- Bounds: 20 final candidates, five independently retrieved reservations, one literal
  entity reservation, and one complete path reservation.

The evaluated profile must satisfy every V7 absolute and oracle-parity requirement:
recall@5, complete evidence@10, related-context recall@10, and MRR must match or exceed
the unchanged oracle final control. Per-category recall, exact episode counting,
hard-forbidden evidence, scope/subject/eligibility/time/provenance safety, Store
revalidation, path omission, both reranker status ledgers, both reranker memberships,
the new completion membership, boundedness, and backend cleanup remain hard gates.

A pass supports an opt-in highest-quality composition; it does not establish Planner
quality, final-answer correctness, real-world generalization, or publication readiness.
A failure is preserved and must not be repaired with named relation or query-category
rules.
