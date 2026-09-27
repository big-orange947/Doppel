# Heterogeneous retrieval V4 — exploration-only opened ablation

This protocol is frozen before running the V4 result. It is an **opened regression
ablation**, not a new sealed or publication-quality generalization claim: all 480 V3
queries and their prior results have already been inspected. Its purpose is narrower:
determine whether a production candidate pipeline still needs an exact relation path
supplied by an oracle or natural-language path Planner.

The immutable V3 all-partition result supplied the structural motivation. Across its
480 queries, the exact oracle path returned candidates for 96 queries. Every one of
those memory IDs was also returned by bounded Graphiti exploration; exact paths added
zero unique memory IDs, while exploration added 144 related-context IDs. Exact paths
may still affect rank, so candidate-set containment alone is not accepted as proof of
equivalence.

## Frozen comparison

The V2 runner retains all six existing profiles and adds two profiles:

1. `assembled_exploration_only_hybrid`: independent lexical/pgvector candidates plus
   bounded Graphiti exploration, with no exact-path candidates;
2. `assembled_exploration_only_hybrid_memory_reranking`: the same graph source after
   reorder-only whole-memory reranking of the independent candidate window.

Both profiles use the same authoritative PostgreSQL Store reload, exact scope,
subject, authority, lifecycle, temporal, provenance, 20-memory context bound,
five-record base reservation, and one-record literal-entity reservation as V3. The
evaluated profile's latency excludes the oracle exact-path query. The runner still
executes and reports the oracle profile solely as an in-run comparison.

## Frozen gate

The exploration-only reranked profile must satisfy every existing absolute quality and
safety threshold. It must also be no worse than the existing oracle-path plus
exploration reranked profile on:

- evidence recall at 5;
- complete evidence rate at 10;
- related-context recall at 10;
- mean reciprocal rank.

The gate additionally retains exact episode-count accuracy, per-category recall,
zero hard-forbidden/scope/subject/eligibility/time/provenance failures, zero Store
revalidation failures, zero path-budget omissions, strict reranker membership,
20-record bounded output, complete reranker accounting, and both backend cleanup
checks. A failed non-regression is preserved as evidence; it is not repaired by
changing the opened corpus or adding query/category special cases.

## Interpretation boundary

A pass would justify making exact relation-path planning optional for **candidate
recall** in this evaluated topology. It would not make the entire Planner optional.
The Planner remains responsible for lookup/list/count intent, time/as-of/interval
semantics, entity grounding, and any constrained relation hints supplied by the host.
It also would not establish answer sufficiency: Graphiti exploration returns related
context, while the answering model or an optional verifier decides whether that
context proves the requested claim.

The run uses local PostgreSQL/pgvector, Neo4j/Graphiti, BGE embeddings, and the local
CUDA reranker. External HTTP, paid LLM calls, and provider tokens must remain zero.
