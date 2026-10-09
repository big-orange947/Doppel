# Fifth history: fixed next-source authoring freeze

Freeze before any fifth-history paid authoring. The fourth source graph is settled
and unchanged. Its source-name schema/QA can run concurrently as read-only work;
no second graph writer or schema/data migration is permitted in those scopes.

The unchanged additive runner deterministically selects predecessor ordinal +1:
fifth ingestion history, 208/208 eligible confirmed memories. No dataset/questions,
answers or annotations are read for graph selection. The previously opened
50-history manifest and durable ingestion journal stay fixed; reserved histories
remain untouched. This is a development subset, not formal benchmark validation.

- Predecessor: `data/doppel/public-memory-next-graph-scope04-live-v1.json`, complete.
- Preflight: `data/doppel/public-memory-next-graph-scope05-preflight-v1.json`.
- SHA-256: `efb117bf93b9ef6144e1640c3b80ccb39d01d50b3d968c8096b4e7204f48a683`.
- Envelope: `668a6df4e8e591e836d24ba93d126b9b2de0427e2441ee0d74e35ca822ae2bdc`.
- Graph plan: `315d02732c2432a9e1d15ad02a320585466854e8365d98d854df4dee09033642`.
- Scope: `dpl_8a7a77769ee1e1b0a7ccc92f1a09d7f41f05feb987dcd1cf13148edd68aaa84a`.
- Run dir: `data/doppel/public-memory-next-graph-scope05-v1`.
- Output: `data/doppel/public-memory-next-graph-scope05-live-v1.json`.

Same ceilings: 1500 attempted requests, 500000 canonical bytes per request,
32000000 aggregate bytes; not a hard token/CNY cap. Same existing Graphiti writer,
DeepSeek flash JSON-object/disabled thinking/8192 cap, local BGE, serial calls and
durable content cache. No retry/funding/key replacement. On failure preserve spent
usage, successful projections and partial owned slots; never skip an incomplete
predecessor to claim a larger completed sample.

Preflight verifies all 219 predecessor projections, and protects all other 49
diagnostic graph scopes: snapshot `9298d550632b216579095c636c3dda4a0db54cae9d6d5c843b6803273ecef415`
(1847 nodes, 3541 edges). Store/vector connections are read-only and must retain
their fixed fingerprints. Projection completion is not perfect relation extraction.

Only after completion: separate source-name-only ontology preparation and a fresh
natural-query preflight under the explicitly declared `provided-history-v1`
clock, unchanged highest-config/Reader/judge/context policy. Report calls, tokens,
evidence recall, answer accuracy, citations and execution warnings separately.
Do not merge this profile with old strict-reference scores or call five opened
histories an independent aggregate benchmark score.
