# Heterogeneous retrieval V5 — topology-aware exploration plan

This opened ablation is frozen before its first live result. It follows the immutable
V4 failure and uses the same already-open 480 queries, 48 scopes, 9,216 memories,
backends, local models, output bound, and oracle comparison. It is not a new sealed or
publication-quality claim.

V4 proved that bounded exploration discovered the required two-hop memory IDs but did
not keep the second hop inside rank 10. The existing exact path succeeded because its
connected evidence received path-aware priority. V5 tests whether that property can be
expressed generically without an oracle route, benchmark relation labels, category
branches, or query-specific rules.

## Versioned policy

Two opt-in, default-off retrieval controls are added:

1. complete-path preference: when one explored path is a strict edge-and-direction
   prefix of another revalidated path, the complete bounded path ranks ahead of its
   redundant prefix. An unrelated one-hop path is not demoted merely because a
   different two-hop path exists;
2. path-evidence reserve: hybrid assembly may order every Store-revalidated memory
   supporting its first retained path as one evidence bundle. The existing independent
   base reservation and literal-entity reservation remain active.

Both controls operate only on candidates that Graphiti already returned and Doppel
already revalidated. They do not synthesize edges, expand the two-hop or 20-memory
bounds, select scopes, relax subject/authority/time/state/provenance checks, or claim
that the retained path proves an answer. The production defaults remain unchanged
until evaluation supports a broader decision.

## Profiles and frozen gate

The V3 runner retains the prior eight profiles and adds:

- `assembled_topology_aware_exploration_hybrid`;
- `assembled_topology_aware_exploration_hybrid_memory_reranking`.

The final topology-aware profile contains no oracle exact-path candidates. The oracle
plus exploration reranked profile remains an in-run quality reference. The V5 final
profile must satisfy every existing absolute quality and hard-safety threshold and
must match or exceed the oracle reference on evidence recall@5, complete evidence@10,
related-context recall@10, and MRR. Store revalidation, zero path omission, reranker
membership, 20-record boundedness, complete accounting, and backend cleanup remain
hard gates.

The result remains evidence if it fails. No threshold, corpus label, relation ontology,
or policy constant may be changed after inspecting the result under this version.
External HTTP, paid LLM calls, and provider tokens must remain zero.
