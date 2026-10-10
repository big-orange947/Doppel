# Seventh natural highest-config QA freeze

Before five paid QA requests. Complete seventh source/schema; unchanged natural
V7 Planner, Reader V2, DeepSeek flash, BGE, CUDA reranker and 20 whole-item/24000
UTF-8-byte packing. No question-specific prompt, answer-aware selection or old
score changes. Opened development question, not independent LongMemEval/AML.

Schema receipt `data/doppel/public-memory-next-schema-scope07-live-v1.json`, SHA-256
`7b29681c3833a27368c15346f29d708a49d76fd3a357288356e4767133c415e9`:
139 definitions, six successful requests/13125 reported tokens, zero missing usage,
graph unchanged. Definitions are inferred, not verified semantic truth.

- Preflight: `data/doppel/public-memory-next-query-scope07-preflight-v1.json`.
- SHA-256: `098c7f14e3fe95b7ba038efa2d913e0aa471871d4fe2f5bf4c1363d6acbe7aca`.
- Plan: `059532f5ac1fdd3dc6b8f573178118b3aa2417d3c101c6bd3bc48eef28473d8b`.
- Run dir: `data/doppel/public-memory-next-query-scope07-v1`.
- Live output: `data/doppel/public-memory-next-query-scope07-live-v1.json`.

Uniform provided-history-v1: question reference/observation horizon
`2023-05-30T08:29:00Z`, latest provided observation `2023-05-30T06:09:00Z`;
483 turns, none after reference. Gold never chooses clocks or candidates.
Ceiling two Planner/one Reader/one task judge/one citation judge; no retries.
Preserve errors, answers, warnings and usage. Empty-key checkpoint/cache replay
after completion, not fresh model/reranker execution. Report task, evidence,
citations and actual graph contribution separately, including failure cases.

Loss-telemetry instrumentation regression: **1523 passed, 33 skipped, three
subtests passed**, one existing Graphiti/Pydantic deprecation warning, 192.47s.
Ruff and explicit local-interpreter Pyright pass. Eighth graph paid authoring
started only after regression passed, under its previously committed source plan;
its scope is the sole graph writer. Seventh QA is read-only; `uv.lock` untouched.
