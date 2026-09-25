# Heterogeneous retrieval V2 — opened dev diagnostic

This V2 run opened the same 120 dev queries after the evidence-role correction. No
sealed or adversarial result was opened. Retrieval order was intentionally unchanged
from V1.

- implementation commit: `84239eb00f7a4ab69b28b723d66bff5e11e4311c`
- dataset fingerprint:
  `78e647233d025926529efab6e4f855f6240537c071f3b4cbbcb5e155ffe96649`
- report payload hash:
  `e0760d3ea5bfff2f5987121024957a1e473575070f1ff3825f788f472efe3c50`
- ignored raw file SHA-256:
  `7292cfe1999093bbd95ad536f238b785f5a4012c139e7edf6f086284b3ca66e4`
- external HTTP / LLM calls / provider tokens: `0 / 0 / 0`

The headline metrics were identical to V1, as required: the highest-quality profile
reached 0.811 evidence recall@5, 0.880 complete evidence@10, and 0.847 MRR. V2 removed
all 12 false hard-forbidden labels. Scope, subject, lifecycle/authority, time,
provenance, Store reload, reranker membership, path budget, and backend cleanup all
passed. Reranker accounting also correctly accepted 108 completed calls plus 12
`not_run` results whose candidate sets were empty.

The new candidate-window diagnostic established two distinct remaining causes:

- every related-but-insufficient buyer memory was present in the unchanged 64-item
  independent candidate window, but only 5/12 reached rank 10 after answer-relevance
  reranking; all 12 remained inside the final 20-item context;
- all 12 episode-count queries had empty candidate windows because exact count bypasses
  bounded semantic retrieval and the oracle plan provided no memory type/topic filter.

The first issue motivates a generic, bounded literal-entity reservation in hybrid
assembly—not a buyer/holder keyword rule. The second motivates explicit generic oracle
count-plan fields so retrieval execution and natural-language planning are not scored
as the same component. Neither change lowers a threshold or alters sealed query text.
