# Combined retrieval V2 — full hybrid memory-reranking preregistration

This protocol was frozen after the semantic-only reranking result and before opening
the new memory-reranked profile on the complete 144-query combined corpus. Existing
profiles, dataset labels, graph fixtures, topology outputs, filters, and the legacy and
exploration gates remain unchanged.

## Additive profile

The new profile is:

`independent lexical/vector candidates → local whole-memory reranking → bounded merge
with typed plus explored Graphiti paths → authoritative Store-backed assembly`.

Only the first 64 independent candidates may be reordered. Typed and explored graph
paths do not enter the reranker and retain the existing atomic path assembly. The
cross-encoder cannot add candidates, execute a path, set evidence authority, or bypass
scope, lifecycle, provenance, valid-time, and Store gates. Final context remains bound
to 20 records with a five-record independent reservation.

The model and runtime are unchanged from the opened semantic-only experiment:
local `BAAI/bge-reranker-v2-m3`, SentenceTransformers, CUDA, and one sigmoid over raw
logits. No LLM, external HTTP, or paid provider is used.

## Frozen success gate

Compared with the already-opened `assembled_hybrid_with_exploration` profile, the new
profile must satisfy all of the following:

- overall evidence recall@5 does not regress;
- complete evidence@10 does not regress;
- MRR does not regress;
- semantic-nonrelation evidence recall@5 is at least `0.85`;
- complete evidence@10 does not regress independently for one-hop relations, two-hop
  relations, and temporal incomplete-path adversaries;
- first-64 independent candidate membership changes in zero queries;
- all 144 reranking calls complete rather than silently degrading;
- hard-forbidden hits, scope leakage, exposed ineligible records, orphan provenance,
  temporal complete-path failures, actual Store revalidation failures, and path-budget
  omissions are all zero;
- maximum final candidates remains at most 20;
- Neo4j fixtures and the dedicated PostgreSQL benchmark schema are cleaned.

The old topology, typed-only, and exploration gates remain separately visible. The new
gate does not require the failed text-only topology baseline to pass. Latency is
reported but not gated in this first complete quality composition test.
