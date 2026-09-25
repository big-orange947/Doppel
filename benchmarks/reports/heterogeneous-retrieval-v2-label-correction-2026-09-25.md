# Heterogeneous retrieval V2 — evidence-role correction before sealed run

V1 remains frozen and its first dev-only result is preserved. No sealed or adversarial
result was opened on V1. V2 is generated deterministically from V1 and makes one
semantic-label correction discovered on the open dev partition.

## Exact change

For each of the 48 `subject_correction` queries, the owner-corrected fact remains
required. The wrong-subject friend fact remains hard-forbidden. The peer's earlier,
superseded guess moves from `hard_forbidden_memory_ids` to `related_memory_ids` because
it is relevant conflict context but insufficient answer support.

V2 changes no memory, entity, edge, query text, partition, category, domain, relation
route, required answer evidence, temporal coordinate, threshold, retrieval profile, or
backend rule. Automated tests compare all memory/entity/edge payloads and every query
text across versions and require exactly 48 label-only query changes.

- suite: `doppel-heterogeneous-retrieval-zh-v2`
- version: `2.0.0`
- canonical dataset fingerprint:
  `78e647233d025926529efab6e4f855f6240537c071f3b4cbbcb5e155ffe96649`
- committed file SHA-256:
  `7c6d349ebf2b033a9561be10367daf3ab03bf79fd734b308bf7d2cf164dc1885`

The original V1 thresholds remain unchanged. V2 is still synthetic, author-known, and
`publication_ready=false`. The runner remains dev-only by default; opening all 480
queries still requires the explicit `--partition all --sealed-first-run` pair after
this correction and its runner diagnostics are committed.
