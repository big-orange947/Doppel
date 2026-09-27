# Heterogeneous retrieval V9 — base-reserve guard plan

This protocol is frozen before the first V9 live result. V9 is an opened composition
experiment on the same author-known V4 topology-adversarial corpus. It addresses only
the MRR regression preserved by V8 and does not change path discovery, semantic
scoring, topology completion, corpus labels, or any quality threshold.

## Fixed evidence and hypothesis

V8 recovers every required two-hop memory by rank 10, but three one-hop queries move
their first required independent candidate from rank 2 to rank 3. The cause is not a
missing or unsafe candidate: an incorrect but higher-scored explored branch is made
complete, and both of its memories are sorted ahead of the independent base reserve.

V9 tests the generic precedence already implied by Doppel's additive-index boundary:
independent retrieval owns its explicitly reserved positions; graph paths add a
complete evidence bundle inside the remaining bounded context, but do not reorder the
reserved independent candidates.

## Frozen assembly delta

The new `preserve_base_reserve_order` option defaults to false. Only the V9 profile
sets it true. Candidate selection and validation are unchanged:

1. select one literal-entity base candidate and the remaining independent candidates
   up to the fixed base reserve of five;
2. retain the first semantically ranked, topology-completed path atomically;
3. include its Store-revalidated supporting memories subject to the existing limit;
4. order the selected literal and base-reserve candidates first in their existing
   reserved order;
5. order newly added supporting memories from the reserved path next;
6. order all other selected candidates by the unchanged combined score.

The option cannot change the candidate set, path selection, path scorer input, Store
filters, or authorization. It reads no relation names, facts, query categories, gold
labels, or answer IDs. The existing V7 and V8 profiles remain in the same report as
direct controls.

## Unchanged workload and gate

- Dataset fingerprint:
  `0b0d0c8ab8aaf35350e465325540acc3b8c81f00496ed0d02901bc9f10e6a771`.
- Workload: 480 queries, 9,504 memories, 384 entities, 384 edges, and 48 exact owner
  scopes.
- Runtime: local PostgreSQL/pgvector, Neo4j/Graphiti, `bge-small-zh-v1.5`, and CUDA
  `bge-reranker-v2-m3`; zero external HTTP, LLM calls, and provider tokens.
- Bounds: 20 final candidates, base reserve five, literal reserve one, complete-path
  reserve one.

The evaluated profile is
`assembled_base_guarded_path_family_exploration_hybrid_memory_reranking`. It must
match or exceed the unchanged oracle final control on recall@5, complete evidence@10,
related-context recall@10, and MRR. Every existing per-category, count, hard-safety,
Store-revalidation, omission, scorer-status, membership, boundedness, and cleanup gate
remains mandatory.

A pass supports this composition as an opt-in highest-quality candidate policy. It
does not prove natural Planner quality, final-answer correctness, real-world
generalization, or publication readiness. A failure is preserved without changing the
gate or adding relation/query special cases.
