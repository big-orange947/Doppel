# Fifth QA and sixth source-only schema freeze

Frozen before new paid calls. No core algorithms, Reader V2, old scores, caches,
questions or annotations are modified. Both histories are already-opened
development items, not independent LongMemEval/AML validation.

## Fifth natural highest-config QA

- Preflight: `data/doppel/public-memory-next-query-scope05-preflight-v1.json`.
- SHA-256: `ca92cbec642c64b8f354174e0daee8a66c50624c1012ca6d6568c9b102500b6d`.
- Plan: `f11fd7982179745e2d4805ec5a067d03349387336821538483ceb2e16d427ed6`.
- Run dir: `data/doppel/public-memory-next-query-scope05-v1`.
- Live output: `data/doppel/public-memory-next-query-scope05-live-v1.json`.

Uniform gold-free `provided-history-v1`: question reference
`2023-03-28T01:25:00Z`, supplied observation horizon/latest observation
`2023-03-28T22:56:00Z`; 534 turns, 485 after reference. This is supplied-history
evaluation, not causal replay. Keep the reference clock unchanged for valid-time
reasoning. Source graph/schema are complete; source-derived definitions remain
fallible. Same natural planner, local BGE, CUDA cross-encoder, typed graph paths,
memory/raw/backing whole-item packing (20 items/24000 UTF-8 bytes).

Ceiling five new calls: planner two, Reader one, task judge one, citation judge
one. No retries or manual answer corrections. Empty-key checkpoint/cache replay
after completion; it is not fresh planner/GPU execution. Retain wrong answers,
judge disagreements, warnings and usage; report evidence coverage separately.

## Sixth settled source graph and schema

Graph receipt: `data/doppel/public-memory-next-graph-scope06-live-v1.json`, SHA-256
`dfa04111d944a9f9b1353f24d95d0113b5c611c699a945758d0a92f884f01c5d`.
164/164 verified projections: 100 rich, 64 fallback, 182 per-projection rich-edge
links. All authoritative Store/vector and other-scope snapshots unchanged.
683 successful provider calls, 2866914 reported tokens, three cache hits, zero
failed/interrupted calls or missing usage. Retained terminal output was truncated;
absence of extractor warnings cannot be certified. Completion is not proof of
perfect relation extraction. Six source graphs are prepared, not six QA successes.

- Scope: `dpl_b0d08ccf2caba7d91a903ba07b221e399154d5d42b8ce7666ee5d4e5622a47d3`.
- Schema preflight: `data/doppel/public-memory-next-schema-scope06-preflight-v1.json`.
- SHA-256: `64664439d1244cd32ced85ec98813c4527b2127ce804447d9df4b874ea3372e1`.
- Plan: `8509c132e6ab3139de280f4ec33f52d20a39bbe423e5d4ca2c6598f2a21ef079`.
- Run dir: `data/doppel/public-memory-next-schema-scope06-v1`.
- Live output: `data/doppel/public-memory-next-schema-scope06-live-v1.json`.

107 source relation names only, at most five calls, unchanged schema runner.
No source facts, entities, questions, gold answers or grading labels supplied.
Read-only graph/Store/vector. No funding, retries, key replacement or database
resets; spent usage and failures retained if the provider balance is exhausted.
Separate fresh committed sixth QA preflight is required before sixth paid QA.
