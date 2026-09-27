# Heterogeneous retrieval V7 — first whole-path semantic reranking result

V7 was opened only after commit `ccb0eb56d78a7fc385483f8f9fd73b3b3c8d3b6a`
froze its implementation, output contract, corpus, and gates. The local run used the
V4 topology-adversarial dataset fingerprint
`0b0d0c8ab8aaf35350e465325540acc3b8c81f00496ed0d02901bc9f10e6a771`,
all 480 queries, 9,504 memories, PostgreSQL/pgvector, Neo4j/Graphiti, local
`bge-small-zh-v1.5` embeddings, and local CUDA `bge-reranker-v2-m3`. External HTTP,
LLM calls, and provider tokens were all zero.

The raw ignored report is
`data/doppel/heterogeneous-retrieval-v7-path-rerank-opened-live.json`. Its canonical
payload SHA-256 is
`ca562747507bfdec85d46c5c9aabffaa99f78aa0f7ae6d37fa29d8e4ecceeaf9`; its file
SHA-256 is
`0d0123c6169623da3579f167e9f66b66b88fedd99e4b29d77fb7cbaa59da8b77`.
The report records only the pre-existing user-owned `uv.lock` as tracked dirty state.

## Frozen-gate outcome

The run exits nonzero because one and only one frozen check fails:
`oracle_complete_evidence_rate_at_10_non_regression`.

| final profile | recall@5 | complete@10 | related@10 | MRR |
| --- | ---: | ---: | ---: | ---: |
| V6 topology-aware exploration | 0.912879 | 0.946759 | 0.862500 | 0.917670 |
| V7 semantic-path exploration | 0.975379 | 0.988426 | 0.862500 | 0.921142 |
| oracle exact-path control | 0.960227 | 1.000000 | 0.850000 | 0.921142 |

V7 exceeds the oracle aggregate on recall@5 and related-context recall, and exactly
matches oracle MRR. It does not match complete evidence at 10, so it is not promoted.
The semantic-path final profile observes 406.873 ms p50 and 626.387 ms p95 versus the
oracle control's 409.943/566.583 ms in this single run; these are environment-specific
observations, not stable latency claims.

Path reranking reports 144 `completed`, 336 `not_run`, zero fallback, and zero
membership violations. Memory reranking reports 432 `completed`, 48 `not_run`, and
zero membership violations. Hard-forbidden, scope, subject, eligibility, temporal,
orphan-provenance, Store-revalidation, and path-budget failures are all zero. Neo4j
fixture cleanup and PostgreSQL reset both pass.

## Failure localization

Exactly five of 48 two-hop questions miss complete evidence at rank 10:

- `q-u13-object-city`: location evidence rank 17;
- `q-u20-object-city`: location evidence rank 19;
- `q-u24-object-city`: location evidence rank 19;
- `q-u25-object-city`: location evidence rank 18;
- `q-u38-object-city`: location evidence rank 17.

In all five, the object-to-holder memory is rank 1 and the required holder-to-city
memory remains present before rank 20. Discovery, authorization, time filtering,
provenance, and the 20-candidate bound are therefore not the failure.

A focused live Neo4j probe of `q-u13-object-city` reproduces the decisive ordering:
the correct one-hop `HELD_BY` prefix scores 0.891509, its correct
`HELD_BY -> LIVES_IN` extension scores 0.734188, and the competing
`LOANED_TO -> WORKS_IN` branch scores 0.318218. The scorer identifies the correct
branch family, but the current global path order lets the prefix consume the single
atomic path reservation. The city memory is consequently flattened at rank 17.

The next experiment must preserve semantic ordering between unrelated first-hop
families while preferring a complete descendant over only its own strict prefix inside
the selected family. This is a topology rule over opaque edges, not a relation-name,
query-category, or gold-answer special case. The V7 result and failed gate remain
unchanged.
