# Fourth history: natural highest-config QA freeze

Before five paid query/answer/judge calls. The source-order fourth history has
219 verified projections, 169 inferred type definitions from eight source-only
requests (16668 reported tokens). Schema receipt SHA-256:
`f7aa653ade96a5f968e7be7feae795e297b6dd083e63fe66f912344a20b2b11b`.
Graph source preparation and this QA are separate costs and evidence.

- Runner: `doppel.public-memory-consecutive-high-config-query.v3`.
- Preflight: `data/doppel/public-memory-next-query-scope04-preflight-v1.json`.
- SHA-256: `775668fd976aa6c1f8bbdbf8ca43b048aaeeeaab3655d1fe8fd916f37d2fd1b9`.
- Plan: `95d24b2ae584849516b027a827586f0166021173556a7b13d351fd2e09c3c8b1`.
- Run dir: `data/doppel/public-memory-next-query-scope04-v1`.
- Live output: `data/doppel/public-memory-next-query-scope04-live-v1.json`.

Frozen `provided-history-v1`: question reference and observation horizon both
`2023-05-30T20:02:00Z`; latest provided observation `2023-05-30T19:48:00Z`.
538 supplied turns, none after reference. Policy remains uniform and gold-free;
this item does not exercise a later-than-reference cutoff. Do not imply a clock
improvement from any correct answer here.

Same real production natural V7 planner, highest-config candidate/typed-path
composition, local BGE embeddings, CUDA cross-encoder and verified raw/backing
evidence. Fixed 20 whole items/24000 UTF-8 bytes, Reader V2, reference-only task
judge and source-anchored citation judge. No extra prompt/case/domain rules or
manual corrections. V3 query source hashes include the generic topic-identity
repair; old warnings/answers are not retroactively rewritten.

Ceiling: Planner 2, Reader 1, task judge 1, citation judge 1 (5 new calls).
No retries; preserve failed attempts and usage. After success attempt empty-key
checkpoint/cache replay; do not confuse it with fresh planner/reranker execution.
All reads bind authoritative Store/vector and the settled fourth graph. The
fifth graph writer is isolated to its own frozen scope and protects the fourth.

Report task result, annotated-turn/session coverage, legal citations, quote support,
actual path contribution, execution/metadata warnings, language drift and usage
separately. A correct answer is not a graph-uplift or publication claim. This is
one more already-opened development question, not full LongMemEval or AML.
