# Heterogeneous retrieval V7 — whole-path semantic reranking plan

This protocol is frozen before the first V7 live result. V7 is an opened repair
experiment on the already-opened, author-known V4 topology-adversarial corpus. It is
not a sealed or publication-quality claim. Its single question is whether generic
query-to-path semantic ranking can choose among valid graph branches that structural
“complete over prefix” ordering cannot distinguish.

## Fixed inputs and controls

- Dataset: `heterogeneous-retrieval-zh-v4.json`, fingerprint
  `0b0d0c8ab8aaf35350e465325540acc3b8c81f00496ed0d02901bc9f10e6a771`.
- Queries: all 480 dev, sealed, and adversarial queries, opened together using the
  existing `--partition all --sealed-first-run` guard.
- Memories/graph: 9,504 Store records, 384 entities, and 384 edges in 48 exact owner
  scopes; no corpus or label change from V6.
- Independent retrieval, oracle exact-path control, bounded Graphiti exploration,
  assembly bounds, memory reranker, thresholds, and safety checks remain unchanged.
- The V6 topology-aware and V4 exploration-only profiles remain in the same report as
  diagnostic controls.

## New stage and information boundary

The new stage operates only after bounded graph exploration and before atomic path
reservation. For each explored path it sends the existing local relation reranker:

- the natural-language query;
- an opaque sequential item ID;
- the path's ordered relation-type sequence;
- the path's ordered edge-fact text.

It does **not** send scope keys, user or subject identifiers, memory IDs, entity IDs,
path IDs, authority, lifecycle state, timestamps, provenance, query category, gold
labels, or answer IDs. No relation label receives a hand-written weight or branch.

The scorer has ranking authority only. It must return exactly one finite score for
every opaque item. It cannot add or remove a path, change supporting memories, grant
authorization, or assert answer sufficiency. Unknown, duplicate, missing, malformed,
non-finite, or exceptional output produces the pre-existing deterministic
topology-aware order. Store-backed assembly subsequently revalidates scope, active
state, time, provenance, and the complete supporting-memory set.

## Frozen evaluated profile and gate

The evaluated profile is
`assembled_semantic_path_exploration_hybrid_memory_reranking`. It uses no oracle exact
path. Its explored paths are semantically reordered, one first path is atomically
reserved, and independent memory candidates receive the already-frozen reorder-only
memory reranker.

It must satisfy all existing absolute gates and match or exceed the unchanged oracle
control on:

- evidence recall at 5;
- complete evidence rate at 10;
- related-context recall at 10;
- MRR.

It must also retain zero hard-forbidden, scope, subject, eligibility, temporal, and
orphan-provenance failures; zero Store-revalidation failures; zero path-budget
omissions; at most 20 candidates; and successful Neo4j/PostgreSQL cleanup. Both the
path scorer and memory scorer must account for all 480 queries using only `completed`
or `not_run`; any `fallback` fails the gate. Path and memory reranking must each
preserve exact candidate membership.

The local BGE reranker runs on CUDA. PostgreSQL/pgvector and Neo4j/Graphiti are local.
External HTTP calls, LLM calls, and provider tokens must all remain zero. Latency is
reported as an observation from this run, not a stable performance claim.

## Interpretation

A pass supports making whole-path semantic reranking an opt-in highest-quality
retrieval component. It does not prove natural-language Planner quality, final-answer
correctness, real-world generalization, or publication readiness. A failure is kept
as evidence and must not be repaired through per-query, per-category, or named
relation-type special cases.
