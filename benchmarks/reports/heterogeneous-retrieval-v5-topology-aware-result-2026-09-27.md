# Heterogeneous retrieval V5 — topology-aware exploration result

This report preserves the first result of the preregistered V5 opened ablation. The
runner, policy, tests, schema, and gate were committed and pushed as
`a47bd5a56dc64dcf0b0ab055a0dec10eff2efea1` before the run. The corpus was already
opened by earlier experiments, so this is architectural regression evidence rather
than a sealed or publication-quality generalization claim.

V5 passed every frozen gate. Its evaluated profile uses no oracle exact-path
candidates and matches the oracle quality reference on every gated aggregate metric.

## Reproducibility

- dataset: `doppel-heterogeneous-retrieval-zh-v3` (`3.0.0`)
- dataset fingerprint:
  `ead91761f9da403c31c8b759d427c4551709daf7d29f35d26d786f94ec167f88`
- selection: all 480 queries, 48 exact owner scopes, and 9,216 memories
- implementation commit: `a47bd5a56dc64dcf0b0ab055a0dec10eff2efea1`
- report payload hash:
  `dc578eaa9316dd9ba2f1a2da0b8f0a29a5f7a5db116780a6b8ab8dca788b3a93`
- raw JSON file SHA-256:
  `d683d65a8ee3d29ccb0455ab0da5faa4b0006fa8238017ebbbf7a1f4ab9481f3`
- authoritative Store: PostgreSQL
- independent retrieval: PostgreSQL lexical plus 512-dimensional pgvector cosine
  search using `BAAI/bge-small-zh-v1.5`
- graph retrieval: local Neo4j/Graphiti exact paths and bounded exploration
- reranker: local `bge-reranker-v2-m3`, CUDA, 64-record window
- final context bound: 20 memories
- external HTTP requests / LLM calls / provider tokens: `0 / 0 / 0`
- tracked dirty path disclosed by the runner: the pre-existing user-owned `uv.lock`

The ignored raw result is
`data/doppel/heterogeneous-retrieval-v5-topology-aware-opened-live.json`.

## Result

| Profile | Evidence recall@5 | Complete evidence@10 | Related context@10 | MRR | p50 / p95 ms |
|---|---:|---:|---:|---:|---:|
| independent lexical + vector | 0.871 | 0.843 | 0.646 | 0.898 | 79.1 / 94.0 |
| oracle + exploration + memory reranking | **0.998** | **1.000** | **1.000** | **0.933** | 348.7 / 449.6 |
| V4 exploration-only + memory reranking | 0.956 | 0.949 | 1.000 | 0.933 | 334.0 / 439.8 |
| topology-aware exploration, no memory reranking | 0.962 | 0.954 | 1.000 | 0.898 | 169.9 / 219.6 |
| V5 topology-aware exploration + memory reranking | **0.998** | **1.000** | **1.000** | **0.933** | 328.8 / 433.9 |

The old V4 failure reproduced in the same process, while V5 restored oracle-level
quality. This controls for a backend or model-state explanation. V5 observed about
20 ms lower p50 and 16 ms lower p95 than the oracle control because it does not execute
the exact route for its own assembly; one sequential run is not a stable latency
benchmark, so these numbers are descriptive rather than a performance claim.

## Failure repair and category behavior

V4 had 22 incomplete rank-10 two-hop queries. V5 restored all of them: the
`two_hop_relation` category reached 1.000 evidence recall@5/@10, complete evidence@10,
and MRR. One-hop relations, temporal queries, event counts, document facts,
cross-conversation facts, and related-only no-answer cases also remained at 1.000 on
their applicable quality metrics.

The only aggregate Recall@5 miss is unchanged from the oracle control:
`q-u46-corrected-role` places the corrected role at rank 10. Subject-correction MRR
also remains the known 0.531 weakness because useful peer conflict context can precede
the owner's corrected claim. Neither issue was touched by the path policy.

The V5 and oracle profiles do not produce identical lists: 76 of 480 queries have a
different full candidate order. Their evidence, completeness, related-context, MRR,
count, and safety metrics nevertheless match. This confirms that the result is not an
accidental replay of oracle ordering. V5 records 288
`path_evidence_reserve` attributions, corresponding only to memories already carried
by its first retained, Store-revalidated exploration path.

## Safety and accounting

V5 recorded zero hard-forbidden hits, scope leakage, subject violations, ineligible
state/authority hits, temporal violations, orphan provenance, Store-revalidation
failures, path-budget omissions, and reranker membership violations. Every output
stayed within 20 memories. All 480 reranker outcomes were accounted for (432 completed,
48 legitimate empty-window `not_run`), and both Neo4j and PostgreSQL cleanup passed.

## Decision boundary

The result supports a narrower architecture decision: on this topology, candidate
assembly does not need an exact oracle relation route when bounded exploration can
prefer a complete path over its strict prefix and reserve one revalidated path as an
atomic evidence bundle. It does **not** eliminate the Planner's intent, time, count,
entity-grounding, or optional relation-hint duties, and it does not prove answer
sufficiency.

The controls remain default-off pending a dedicated topology-adversarial corpus with
branching paths, cycles, unrelated one-hop paths, competing two-hop continuations, and
tight candidate budgets. That corpus must verify that prefix completion raises recall
without allowing graph breadth to erase independent evidence or violate scope/time/
provenance constraints.
