# Eighth consecutive natural QA freeze

Before paid QA calls. Complete eighth graph and names-only schema, no retrieval
or Reader changes. Source order, not answer selection; opened development only.

- Query preflight: `data/doppel/public-memory-next-query-scope08-preflight-v1.json`.
- SHA-256: `979d650c47aa50dc5ce288d91521dae5e09c8aac1252e11908e93666c5edcb6c`.
- Plan: `a3a2e3b7a1d43f8556a50a3694820019d6bf6044e5b73499cea75e46c680adf3`.
- Run dir: `data/doppel/public-memory-next-query-scope08-v1`.
- Output: `data/doppel/public-memory-next-query-scope08-live-v1.json`.
- Graph: `data/doppel/public-memory-next-graph-scope08-live-v1.json`.
- Schema: `data/doppel/public-memory-next-schema-scope08-live-v1.json`.

127 relation definitions, six schema calls/11954 reported tokens, graph unchanged.
Keep provided-history-v1 observation policy, unchanged Reader V2, BGE 512-vector,
CUDA BGE reranker, raw pool 80/output 20, whole-item cyclic packing 20/24000 bytes.
Planner at most two requests; Reader/task/citation judges one each; no retries.
Freeze source hashes and budget/cache identity; failures/spent usage stay retained.
Run empty-key cache-only replay afterwards. Keep task accuracy separate from
citation judge and execution compliance. No graph-uplift or AML score claim.
Ninth source-only authoring remains the sole graph writer in its separate scope.
Any source-window extension needs its own controls, plan and cache/run directory.
