# Combined retrieval V2 — first full hybrid memory-reranking result

This result was opened after commit `13d516f` froze the additive profile and gate in
`combined-retrieval-memory-rerank-preregistered-2026-09-25.md`. No dataset label,
threshold, topology output, graph fixture, filter, candidate window, or final context
bound changed after opening the result.

## Runtime and binding

- dataset fingerprint:
  `f35257ad354f5132c49f152b0b705fbba2cc7ce04dec4635237c91c505a84f6b`;
- 144 queries, 36 owner scopes, and 3,600 memories;
- PostgreSQL authoritative Store, pgvector, and live Neo4j/Graphiti;
- candidate embedding: FastEmbed `BAAI/bge-small-zh-v1.5`, 512 dimensions;
- local independent-candidate reranker: `BAAI/bge-reranker-v2-m3`,
  SentenceTransformers 6.0.1, CUDA, sigmoid over raw logits, 64-candidate bound;
- zero LLM calls, external HTTP calls, or provider tokens;
- report SHA-256:
  `2b0fc09159f7dcb50a4cfae5e94898e8feb46ba9bf35e5f7f547e7ca733d87af`;
- Neo4j fixtures and the dedicated PostgreSQL schema were cleaned.

## Result

| Profile | Evidence recall@5 | Complete evidence@10 | MRR | p50 | p95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| independent lexical + vector | 0.667 | 0.556 | 0.815 | 81.1 ms | 94.3 ms |
| reviewed typed path | 0.590 | 0.500 | 0.394 | 9.1 ms | 27.7 ms |
| bounded explored path | 0.750 | 0.667 | 0.333 | 16.7 ms | 27.5 ms |
| independent + typed path | 0.785 | 0.713 | 0.815 | 131.8 ms | 173.2 ms |
| independent + typed + explored path | 0.854 | 0.806 | 0.616 | 150.8 ms | 192.9 ms |
| previous + independent memory reranking | **1.000** | **1.000** | **0.796** | 419.6 ms | 542.7 ms |

The final profile reached 1.000 evidence recall@5 and 1.000 complete evidence@10 in
every category:

- one-hop relation: 1.000 / 1.000;
- two-hop relation: 1.000 / 1.000;
- temporal incomplete-path adversaries: 1.000 / 1.000;
- semantic non-relations: 1.000 / 1.000.

MRR improved from 0.616 to 0.796. It is not 1.000 because graph-supported questions
retain atomic multi-record evidence and the metric evaluates the positions of all
required records, not only whether the first returned record is relevant.

## Safety and composition

All preregistered checks passed:

- 144/144 reranker operations completed;
- first-64 independent candidate membership changed in zero queries;
- zero hard-forbidden hits, scope leakage, exposed ineligible records, orphan
  provenance, temporal complete-path failures, actual Store revalidation failures, or
  complete-path budget omissions;
- final candidates never exceeded 20;
- one-hop, two-hop, and temporal complete-evidence rates did not regress;
- both backend cleanup checks passed.

The larger 64-candidate input caused 294 authority/lifecycle filter rejections during
final assembly. All were reported as expected `filter_mismatch`; none was a stale Store
reference or post-read scope mismatch. The reranker therefore improved ordering but
did not gain evidence or authorization authority.

## Decision and limit

This supports the following highest-quality architecture for Doppel:

1. lexical plus embedding retrieval generates a bounded independent candidate window;
2. an optional local whole-memory cross-encoder reorders that independent window;
3. typed and bounded-exploration Graphiti paths remain outside the reranker;
4. atomic path fusion and authoritative Store validation produce at most 20 context
   records.

The latency premium is material: p50 increased by about 269 ms and p95 by about 350 ms
over the exploration-only hybrid. The reranked profile should therefore remain an
explicit highest-quality option rather than the unconditional lightweight default.

The perfect recall and complete-evidence score is still development evidence, not a
publication claim. The corpus is frozen and provider-unseen, but author-known; its
semantic slice uses 12 base phrasings across three wording cycles and its graph
topology is synthetic. A larger domain-diverse, independently authored corpus remains
necessary before claiming general 1.000 retrieval quality.
