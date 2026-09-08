# Personal-memory reranking runtime validation — 2026-09-08

This is a paired local validation of the provisional `PersonalMemoryReranker`
runtime path. It is not a publication-ready benchmark or an answer-quality claim.

## Fixed inputs

- Doppel commit: `4b6fc82c0ec8614dc62e8f077e5568562b08d733`
- Dataset: `personal-relation-ablation-zh-v1` v1.5, fingerprint
  `74b4ea6dd558cc113cef81272bb673eaeec64cb24187b84df2cd06e8279dd378`
- Planner: hash-bound cached Reference Planner v12 report; 64 valid drafts and one
  preserved source failure (`rel-q25`)
- Candidate fusion: `union`
- Authoritative Store: PostgreSQL
- Semantic candidates: pgvector, FastEmbed `BAAI/bge-small-zh-v1.5`, 512 dimensions
- Relation candidates: Neo4j/Graphiti rich edges, with authoritative Store reload
- Edge and memory scorer: local `BAAI/bge-reranker-v2-m3`, SentenceTransformers
  6.0.1, sigmoid-normalized raw logits, CUDA on an RTX 4070 Laptop GPU
- External LLM/HTTP calls and paid tokens: zero

The control and treatment use the same committed source, data, planner report,
databases, model, thresholds, and profile. The only treatment change is
`--memory-reranker` with a 64-candidate, 100,000-character, 30-second bound.

## Paired result

| Metric | Control | Memory reranker | Delta |
|---|---:|---:|---:|
| Recall@1 | 0.88 | 0.92 | +0.04 |
| Recall@5 | 0.94 | 0.94 | 0.00 |
| MRR | 0.91 | 0.93 | +0.02 |
| Required-evidence recall | 0.94 | 0.94 | 0.00 |
| Legacy forbidden anywhere in returned window | 24 | 24 | 0 |
| Legacy forbidden at rank 1 | 10 | 6 | -4 |
| Abstention accuracy | 0.7692 | 0.7692 | 0 |
| p50 latency | 97.608 ms | 204.837 ms | +107.229 ms |
| p95 latency | 484.284 ms | 939.156 ms | +454.872 ms |

The candidate set changed in zero cases. Runtime reranking completed in 63 successful
non-count queries; one successful exact-count query correctly reported `not_run`.
The source Planner failure is retained in the metric denominator.

Top-1 gains were `rel-q03`, `rel-q37`, and `rel-q38`; the single top-1 loss was
`rel-q39`. The gain therefore is not a hidden candidate-recall improvement: it is a
net two-query ordering improvement over 50 evidence-bearing attempts. The unchanged
window-level forbidden count is expected because the protocol cannot delete a
candidate. The rank-1 reduction is useful but remains a legacy relevance label, not a
security metric.

## Safety and cleanup

Both arms reported zero scope leakage, temporal violations, provenance failures, and
inactive-record acceptance. The reranker receives only the raw question plus opaque
request-local IDs and authorized memory content; it never receives scope or memory
identifiers. After each run the PostgreSQL benchmark schema contained zero public
tables and Neo4j contained zero benchmark preseed episodes. Both containers remained
healthy.

Report hashes:

- control: `1596388bf4e2825a493144575bd9d91401cfee0eee394cb2b6063768b3e7f366`
- treatment: `b1ed8deafc32f2e111b1104bb6ccf085128a93e2f982778c4c337de118f036d1`

## Honest limitations

The 65-query relation dataset is still draft, partly post-hoc, and has no completed
graded-relevance judgments (`nDCG@5` unavailable). It measures retrieval ordering,
not final answer correctness. `rel-q45` and `rel-q54` remain missing because the
Planner supplied the wrong temporal/intent shape; reranking correctly cannot recover
candidates rejected by the time gate. `rel-q25` remains a source Planner failure.

The latency pair is a single local sequential run after Docker/GPU cold start, not a
capacity or concurrency benchmark. The observed quality/latency trade-off supports
keeping memory reranking opt-in for the highest-quality profile; it does not justify
enabling it by default until a larger frozen held-out/adversarial set and repeated
warm latency runs exist.
