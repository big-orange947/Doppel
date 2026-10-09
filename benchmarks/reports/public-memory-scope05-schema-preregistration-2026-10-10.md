# Fifth history: settled graph and source-name schema freeze

Before schema calls; fifth source selection frozen in `2838d21`. Development
diagnostic, not a blind sample, complete LongMemEval score or AML result.

208/208 projections complete: 133 rich, 75 fallback-only; 216 distinct rich edges,
217 per-projection provenance links, 158 relation names. 862 successful provider
calls, 3594348 reported tokens, zero failed/interrupted requests or missing usage.
Three missing-target warnings remain extraction losses: IS_ENTHUSIAST_OF twice
(projection 8), WANTS_TO_EDUCATE_SELF_ABOUT (projection 136). No fabricated repair.
Store/vector/all other 49 diagnostic graph snapshots unchanged. Coverage is now
5/50 ready histories, 1042 projections, not full-corpus coverage.

- Graph receipt: `data/doppel/public-memory-next-graph-scope05-live-v1.json`.
- SHA-256: `cfd98d8191c7df6a86ebda01d1d2618e0aa5568b56d46664ede81b205ffded09`.
- Schema preflight: `data/doppel/public-memory-next-schema-scope05-preflight-v1.json`.
- SHA-256: `144ebfee008345e8c337fa8a116b021b72a4fccec2798d3d3d3522305e69a281`.
- Schema plan: `6ee1b76d0b08a1f1fe68e60b8cf107acc4affdcd1ab2eefa9e2c3c613070eb2a`.
- Run dir: `data/doppel/public-memory-next-schema-scope05-v1`.
- Output: `data/doppel/public-memory-next-schema-scope05-live-v1.json`.

158 names only, 24 per batch, seven new calls maximum, 4096 output-token cap.
No questions, facts, entities, gold or annotations; no graph rewrites. Definitions
are inferred/fallible, not independently verified semantic truth. No retries;
preserve failure and spent usage. Freeze a separate current-V3 highest-config
query preflight before its five-call QA ceiling. Keep unchanged Reader V2 and
the existing judges; do not tune personalization/count rules to opened failures.
Clock is uniform source-derived provided-history-v1; validity reference unchanged.

Report task/evidence/citation/execution metrics separately, with empty-key replay
after completion. Do not merge these developer diagnostics with strict causal
profiles or count retrieval evidence as a correct final answer.
