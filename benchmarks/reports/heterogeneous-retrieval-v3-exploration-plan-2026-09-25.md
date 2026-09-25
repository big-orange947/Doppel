# Heterogeneous retrieval V3 — bounded exploration runner revision

This runner revision is frozen after the third dev diagnostic and before any sealed or
adversarial result. It does not change V3 data, labels, splits, thresholds, oracle
plans, embedding model, reranker, candidate window, final 20-record context bound, or
backend configuration.

It adds three separately observable profiles:

1. `bounded_graph_exploration` executes the existing ontology-governed Graphiti
   exploration contract for queries with explicit entity mentions;
2. `assembled_oracle_exploration_hybrid` combines independent candidates, exact oracle
   paths, and explored paths before authoritative Store revalidation;
3. `assembled_oracle_exploration_hybrid_memory_reranking` reranks only the independent
   branch, then assembles it with the same exact and explored graph paths.

The original `oracle_graph_path` and `assembled_oracle_hybrid` profiles remain in the
same report, so exploration gain or regression cannot be hidden. Exploration is
bounded to the corpus ontology, two hops, exact authorized scope, the query time, and a
20-path result limit. It cannot invent an edge, choose scope, add a memory not backed by
an Episode, bypass Store filters, or claim that a discovered relation answers the
question. Exact and explored paths are deduplicated before assembly, and complete path
support stays atomic.

The unchanged first-run gate applies to
`assembled_oracle_exploration_hybrid_memory_reranking` and compares MRR against the same
exploration-enhanced assembly without memory reranking. No sealed/adversarial output is
opened until this runner revision and its tests are committed.
