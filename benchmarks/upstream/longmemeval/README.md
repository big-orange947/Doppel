# Content-pinned LongMemEval scorer

`evaluate_qa.py.txt` is an unmodified snapshot retrieved on 2026-10-10 from
https://github.com/xiaowu0162/LongMemEval/blob/main/src/evaluation/evaluate_qa.py.
Upstream license: MIT, copyright 2024 Di Wu; see the adjacent LICENSE.

SHA-256 of UTF-8 text with LF newlines:
`ecce9c4c79dc89d99534ac17b383a5cbb5b9f0c69ee98adaf0684742e3d95251`.
The commit lookup was rate-limited; this is a **content-pinned snapshot**, not a
claim of an upstream commit pin. Runtime does not download or update this file.

The local wrapper extracts only `get_anscheck_prompt` from the hash-checked AST.
It preserves the upstream GPT-4o snapshot, one user message, temperature 0,
max_tokens 10, n=1 and case-insensitive substring-`yes` scoring. It does not run
the upstream CLI, its overwriting output writer, SDK or unbounded retry wrapper.
Local protections add a durable attempt cap, immutable receipts, usage accounting,
content-addressed caching and separate strict output-validity checks. These checks
do not silently rewrite the upstream label.

This is protocol-aligned local regrading of opened diagnostic cases, not an
official leaderboard result, independent blind evaluation or AML score. An
OpenAI-compatible endpoint's returned model name alone cannot establish that it
actually runs the requested OpenAI model.
