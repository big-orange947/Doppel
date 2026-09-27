# Heterogeneous retrieval V6 — topology-adversarial plan

This protocol is frozen before the first V6 live result. V6 is an opened stress
extension of the author-known V3 corpus, not a sealed or publication-quality claim.
It tests the exact limitation left by the V5 pass: a complete path can be preferred
over its own prefix, but that does not prove the first retained path is the correct
branch when several valid paths leave the same entity.

## Deterministic corpus delta

V6 keeps all 480 query texts, answer labels, owner-disjoint partitions, and 9,216 V3
memories unchanged, then adds the same structural adversaries to each of 48 scopes:

- an unrelated one-hop `MADE_BY` edge;
- a competing `LOANED_TO -> WORKS_IN` two-hop branch;
- two opposite `RELATED_TO` edges that would form a repeated-node cycle;
- an expired `HELD_BY` edge and historical Store record;
- six provenanced memories and five new entities per scope.

The resulting corpus has 9,504 memories, 384 entities, and 384 edges. The graph query
must exclude the repeated-node cycle as a two-hop path and the expired edge at the
query time. The no-answer relation question labels the live branch memories as related
but insufficient context; it does not treat them as proof of a buyer. The stale holder
is hard-forbidden for all three relation-query forms.

The dataset fingerprint is
`0b0d0c8ab8aaf35350e465325540acc3b8c81f00496ed0d02901bc9f10e6a771`.

## Frozen execution and gate

The already-frozen V3 runner and V5 topology-aware policy execute unchanged. No
relation-specific ordering, semantic path scorer, threshold, output budget, or quality
gate is added for this run. The evaluated profile still receives no oracle exact-path
candidates and must match the oracle control on recall@5, complete evidence@10,
related-context recall@10, and MRR, while satisfying all absolute, per-category,
count, hard-safety, Store-revalidation, boundedness, accounting, and cleanup gates.

This is intentionally capable of failing. In particular, complete-path preference
does not distinguish two unrelated maximal branches, and the one-path reserve may
choose an irrelevant but valid one-hop edge. A failure would justify a new, generic
path-level semantic ranking protocol. It must not be repaired by naming these relation
types in the Planner or adding category/query special cases.

The run uses local PostgreSQL/pgvector, Neo4j/Graphiti, BGE embeddings, and the local
CUDA reranker. External HTTP, paid LLM calls, and provider tokens must remain zero.
