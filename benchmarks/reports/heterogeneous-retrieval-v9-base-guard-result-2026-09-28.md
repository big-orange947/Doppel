# Heterogeneous retrieval V9 — first base-reserve guard result

V9 was opened only after commit `817a057fc91bfbf0a53b37c12c05b5208f0dd273`
froze its implementation, corpus, result contract, and gates. It used the unchanged
480-query, 9,504-memory V4 topology-adversarial dataset with fingerprint
`0b0d0c8ab8aaf35350e465325540acc3b8c81f00496ed0d02901bc9f10e6a771`.
PostgreSQL/pgvector, Neo4j/Graphiti, local `bge-small-zh-v1.5`, and local CUDA
`bge-reranker-v2-m3` were live. External HTTP, LLM calls, and provider tokens were
zero.

The ignored raw report is
`data/doppel/heterogeneous-retrieval-v9-base-guard-opened-live.json`. Its canonical
payload SHA-256 is
`adeb19614b5ed2556cdb3c1ea79cd12043df8c488cdfe7d5065c21a6a8f15173`; its file
SHA-256 is
`7d17cc58263efae8219fc5bf6c472c3c8505879424b95137ead52f8ec5d93259`.
The payload hash verifies, and the report records only the pre-existing user-owned
`uv.lock` as tracked dirty state.

## Frozen-gate outcome

The run fails three frozen checks:

- absolute related-context recall at 10;
- oracle evidence recall at 5 non-regression;
- oracle related-context recall at 10 non-regression.

| final profile | recall@5 | recall@10 | complete@10 | related@10 | MRR |
| --- | ---: | ---: | ---: | ---: | ---: |
| V7 rank-first semantic paths | 0.975379 | 0.990530 | 0.988426 | 0.862500 | 0.921142 |
| V8 evidence-rich path family | 0.998106 | 1.000000 | 1.000000 | 0.879167 | 0.919985 |
| V9 five-item base guard | 0.910985 | 1.000000 | 1.000000 | 0.720833 | 0.921142 |
| oracle exact-path control | 0.960227 | 1.000000 | 1.000000 | 0.850000 | 0.921142 |

V9 confirms the expected tradeoff: preserving all five independent positions restores
MRR while keeping every required memory by rank 10, but pushes useful graph evidence
out of rank 5 and related graph context out of rank 10. Its p50/p95 latency is
411.611/646.505 ms in this run; this is an observation rather than a stable latency
claim.

All hard-safety, Store-revalidation, path omission, reranker-status, membership,
candidate-bound, and backend-cleanup checks pass. The failure is ranking utility, not
isolation, time, provenance, lifecycle, or cleanup.

## Decision

V9 remains default-off and is not promoted. A two- or three-position guard could be
selected to interpolate between the observed profiles, but doing so after V7–V9 have
opened the same corpus would be benchmark tuning. The current evidence supports two
honest controls instead:

- V7 is rank-first: oracle MRR, 0.975 recall@5, and 0.988 complete evidence@10.
- V8 is evidence-rich: 0.998 recall@5 and complete evidence@10 of 1.000, with an MRR
  cost of 0.001157 caused by three one-hop rank-2-to-rank-3 moves.

The project's stated goal is to give an Agent enough authorized evidence for the
downstream model to judge, so the next decision belongs in a newly frozen evidence-
bundle or final-answer utility benchmark. It must not be made by tuning another guard
against this opened dataset.
