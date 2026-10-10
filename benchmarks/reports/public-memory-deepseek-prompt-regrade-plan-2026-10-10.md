# DeepSeek regrade with pinned LongMemEval prompts (diagnostic only)

User explicitly elected to keep DeepSeek Flash because GPT-4o is unavailable.
This **supersedes the immediate live GPT-4o step, not its preserved implementation
or preflight**. No official GPT-4o/LongMemEval/AML score will be claimed.

Use the same 28 immutable answers (seven opened cases, four correlated arms) from
`public-memory-response-policy-live-v1.json`, SHA-256
`0545aec92c8febd1cc55e6d4ce76714b8f634c9dee0242eae326766119295c33`.
No new Reader, retrieval, embedding, graph or Store writes. Old labels remain.
The hash-checked upstream prompt and substring-yes parsing are unchanged. This
isolates prompt/rubric differences from the previous DeepSeek meaning-only judge;
it does **not** provide an independent-model validation or measure judge accuracy.

Request `deepseek-v4-flash`, temperature 0, max_tokens 10, thinking disabled,
one user message, no system prompt or JSON mode. DeepSeek's documented interface
does not expose OpenAI's n parameter; omit it and require exactly one returned
choice. Record returned model and strict yes/no/completion validity separately.
Current [DeepSeek documentation](https://api-docs.deepseek.com/) says the legacy
Flash alias is served by V4.1-Flash; authenticated `/models` listed `deepseek-flash`
and `deepseek-v4-pro`. This is not a pinned historical model snapshot. Only the
explicit Flash returned-name allowlist is accepted; no automatic fallback.

Separate run directory: `data/doppel/public-memory-deepseek-prompt-regrade-v1/`.
Free preflight: `data/doppel/public-memory-deepseek-prompt-regrade-preflight-v1.json`,
SHA-256 `887a0ae7958189956576b3fb77dfc8079b4056175c45a85796335cb6906337f9`.
Plan fingerprint:
`287c698ad98c0659696605a1dbe62ff46b7977c53a6106a65f39fb9072fb13c4`.
Bind all request/transport/export/input/runtime hashes before execution.

Budget: at most 28 new generation HTTP attempts, failures included, no automatic
retry. Balance observations are free; stop before the next generation when the
observed cumulative debit reaches 1 CNY or the balance is nonpositive. This is
post-spend protection, not exact billing attribution or a hard currency ceiling.
Initial free account check observed 5.13 CNY. Missing usage is unknown, not zero.
Secrets use only the existing `DEEPSEEK_API_KEY` environment variable.

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_memory_prompt_regrade `
  --live `
  --frozen-preflight data/doppel/public-memory-deepseek-prompt-regrade-preflight-v1.json `
  --output data/doppel/public-memory-deepseek-prompt-regrade-live-v1.json
```

After completion, use the same command with `--cache-only` and a **new output**
`data/doppel/public-memory-deepseek-prompt-regrade-replay-v1.json`; no key required.
Do not overwrite old outputs or delete failure receipts to rebill.

Pre-live verification: 14 new offline tests; 63 directed tests including the
unaltered GPT-4o harness. Ruff and new-file Pyright pass. No paid call before this
preregistration commit. The prior full-suite count 1,627 belongs to the GPT-4o
entrypoint build, not a fresh full-suite run of this addition. `uv.lock` unstaged.

Report the four arms, per-case label disagreements, usage/returned model/strict
validity and key-free replay. Do not select or repair rows by the new score. Keep
citation faithfulness, language and plan-to-fact safety separate from task labels.
