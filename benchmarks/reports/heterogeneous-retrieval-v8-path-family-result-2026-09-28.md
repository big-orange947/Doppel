# Heterogeneous retrieval V8 — first semantic path-family result

V8 was opened only after commit `0e0fd731573b80171d512df2f0c97261ad240c85`
froze its algorithm, result contract, corpus, and gates. The run used all 480 queries
and 9,504 memories from the unchanged V4 topology-adversarial dataset, fingerprint
`0b0d0c8ab8aaf35350e465325540acc3b8c81f00496ed0d02901bc9f10e6a771`.
PostgreSQL/pgvector, Neo4j/Graphiti, local `bge-small-zh-v1.5`, and local CUDA
`bge-reranker-v2-m3` were live. External HTTP, LLM calls, and provider tokens were
zero.

The ignored raw report is
`data/doppel/heterogeneous-retrieval-v8-path-family-opened-live.json`. Its canonical
payload SHA-256 is
`5f44ac144ca1d266945dac5df7a27ba6ad1c29d671618198f698198ac92acce9`; its file
SHA-256 is
`a7d9a2b5e07c949ef3616a537e0684b9d672445ef00449a3ac1626602f846614`.
The payload hash verifies, and the report records only the pre-existing user-owned
`uv.lock` as tracked dirty state.

## Frozen-gate outcome

The run exits nonzero because one and only one frozen check fails:
`oracle_mrr_non_regression`.

| final profile | recall@5 | recall@10 | complete@10 | related@10 | MRR |
| --- | ---: | ---: | ---: | ---: | ---: |
| V7 semantic paths | 0.975379 | 0.990530 | 0.988426 | 0.862500 | 0.921142 |
| V8 semantic family completion | 0.998106 | 1.000000 | 1.000000 | 0.879167 | 0.919985 |
| oracle exact-path control | 0.960227 | 1.000000 | 1.000000 | 0.850000 | 0.921142 |

V8 recovers all five V7 object-holder-location failures and exceeds the oracle on
recall@5 and related-context recall. Its p50/p95 latency is 399.034/627.111 ms versus
V7's 401.316/632.480 ms in the same run; these are observations, not stable latency
claims.

Path semantic reranking reports 144 `completed`, 336 `not_run`, zero fallback, and
zero membership violations. Memory reranking reports 432 `completed`, 48 `not_run`,
and zero membership violations. The new topology completion pass also reports zero
membership violations. Hard-forbidden, scope, subject, eligibility, temporal,
orphan-provenance, Store-revalidation, and path-budget failures are all zero. Neo4j
cleanup and PostgreSQL reset both pass.

## MRR failure localization

The complete-path move changes first-required-evidence rank in exactly three one-hop
queries:

- `q-u17-holder`: rank 2 to rank 3;
- `q-u25-holder`: rank 2 to rank 3;
- `q-u33-holder`: rank 2 to rank 3.

In each case the semantic scorer ranks the competing `LOANED_TO` branch above the
required current-holder evidence. V7 leaves the competing branch's second-hop location
later, so the required independent memory remains rank 2. V8 correctly recognizes and
completes that branch as a topology family, but atomic reservation places both its
first and second memories before the required independent candidate. This is safe and
complete, but slightly worse first-answer ranking.

The result shows that path completeness does not establish answer sufficiency. The
next experiment must not classify these relation names or question categories. It
should preserve the already-selected independent base-reserve order, then place the
complete path inside the remaining top-10 budget. That maintains a broad evidence
bundle for the downstream model while preventing an exploratory graph branch from
displacing stronger independent evidence. The V8 failed gate remains unchanged.
