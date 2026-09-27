# Heterogeneous retrieval V6 — topology-adversarial result

This report preserves the first result of the preregistered V6 topology-adversarial
extension. The corpus, builder, tests, unchanged V5 policy, and unchanged gate were
committed and pushed as `a466b288841b80caeda2cd157128218f55b79c5c` before the
run. V6 is opened, author-known stress evidence rather than a sealed or publication-
quality result.

V6 failed the frozen oracle-parity gate while passing every absolute quality, hard-
safety, boundedness, accounting, and cleanup check. The failure isolates a path-ranking
gap: bounded graph exploration contains the correct paths, but structural prefix
completion alone cannot choose among several valid maximal branches.

## Reproducibility

- dataset: `doppel-heterogeneous-retrieval-zh-v4` (`4.0.0`)
- dataset fingerprint:
  `0b0d0c8ab8aaf35350e465325540acc3b8c81f00496ed0d02901bc9f10e6a771`
- selection: all 480 queries, 48 exact owner scopes, 9,504 memories, 384 entities,
  and 384 graph edges
- implementation commit: `a466b288841b80caeda2cd157128218f55b79c5c`
- report payload hash:
  `ee6773efc3c78287762cb14f486e563f885d64009e14606876d7431918eb3d56`
- raw JSON file SHA-256:
  `7b9899580245bd26c3178de7d8207225fe8c45d9f8051d001763723eda19cea3`
- local stack: PostgreSQL/pgvector, Neo4j/Graphiti,
  `BAAI/bge-small-zh-v1.5`, and CUDA `bge-reranker-v2-m3`
- external HTTP requests / LLM calls / provider tokens: `0 / 0 / 0`
- tracked dirty path disclosed by the runner: the pre-existing user-owned `uv.lock`

The ignored raw result is
`data/doppel/heterogeneous-retrieval-v6-topology-adversarial-opened-live.json`.

## Result

| Profile | Evidence recall@5 | Complete evidence@10 | Related context@10 | MRR |
|---|---:|---:|---:|---:|
| independent lexical + vector | 0.871 | 0.843 | 0.750 | 0.883 |
| bounded graph exploration | 0.182 | 0.222 | 1.000 | 0.044 |
| oracle + exploration + memory reranking | **0.960** | **1.000** | 0.854 | **0.921** |
| exploration-only + memory reranking | 0.913 | 0.947 | 0.854 | 0.921 |
| V5 topology-aware + memory reranking | **0.913** | **0.947** | **0.854** | **0.918** |

The failed frozen comparisons are oracle non-regression for recall@5, complete
evidence@10, and MRR. Related-context parity passes. The topology-aware profile still
clears every absolute threshold, which is useful operationally but does not justify
making it the highest-quality default.

## Localization

All 23 rank-10 failures are `two_hop_relation` queries. In that category:

- raw bounded graph exploration has evidence recall@10 `1.000` and complete
  evidence@10 `1.000`;
- topology-aware final output has evidence recall@5/@10 `0.531/0.760` and complete
  evidence@10 `0.521`;
- every required memory is still present by rank 20;
- `omitted_path_hits=0` and Store revalidation rejects no path.

The correct graph evidence is therefore discovered, authorized, temporally valid, and
within the final 20-record budget. It loses rank when flattened alongside valid but
question-insufficient branches. The first path-evidence reservation attributes only
144 memories across 144 relation queries--one memory per query--showing that unrelated
one-hop branches such as `MADE_BY` or `RELATED_TO` can become the first retained path.
Complete-path preference cannot demote them because they are not prefixes of the
correct two-hop path. A competing `LOANED_TO -> WORKS_IN` maximal branch creates the
same ambiguity among complete paths.

The independent reranker window reaches only `0.760` two-hop evidence recall, so
increasing independent vector overfetch is not a principled repair. In contrast, raw
graph exploration already contains all required two-hop evidence at rank 10. The next
component should rank **whole revalidated paths** against the query before reserving
one path atomically.

No-answer related-context recall is `0.854` for both oracle and topology-aware final
profiles. The additional branch memories are deliberately related but insufficient;
neither profile is rewarded for treating them as answer proof.

## Safety and cleanup

The topology-aware final profile has zero hard-forbidden stale-holder hits, scope
leakage, subject violations, ineligible state/authority hits, temporal violations,
orphan provenance, Store-revalidation failures, path omissions, and reranker
membership violations. The repeated-node cycle is not admitted as a two-hop path,
outputs remain bounded to 20 memories, all reranker outcomes are accounted for, and
both Neo4j and PostgreSQL cleanup pass.

## Decision

Keep V5's complete-path preference and path reserve default-off. The next version
should add a generic path-level reranker whose input contains only query text plus a
path's ordered relation types and facts. It must not receive scope, subject IDs,
memory IDs, answer labels, or authority fields; it can reorder already-revalidated
paths but cannot authorize facts or filter the Store. Failure must fall back to the
existing deterministic order. A new opened V7 ablation should freeze malformed-output
handling, membership preservation, and oracle-parity gates before execution.
