# Official-protocol regrade of existing opened answers

## Scope and freeze

This is **not a new retrieval or Reader experiment**. Regrade all 28 answers
already produced by the seven-case paired response-policy diagnosis, without
changing an answer, a citation, an old label, a context, a graph or a core default.
Cases are opened diagnostics; there are seven independent questions, not 28.
The four arms remain separate:

| Export | Context | Existing Reader policy | Questions |
| --- | --- | --- | --- |
| hypotheses-context0-policy0.jsonl | S raw-vector + reranker | reader_v2 | 7 |
| hypotheses-context0-policy1.jsonl | S raw-vector + reranker | grounded_advice_v1 | 7 |
| hypotheses-context1-policy0.jsonl | Full S-derived evidence sessions, no retrieval | reader_v2 | 7 |
| hypotheses-context1-policy1.jsonl | Full S-derived evidence sessions, no retrieval | grounded_advice_v1 | 7 |

Original IDs are preserved. No case selection by score and no reserved cases.
References come from the same S source used to generate these answers, not the
separately dated upstream oracle variant. Gold goes only to the judge/export;
there are no Reader requests in this module.

Frozen original answer report:
`data/doppel/public-memory-response-policy-live-v1.json`, SHA-256
`0545aec92c8febd1cc55e6d4ce76714b8f634c9dee0242eae326766119295c33`.

Preflight: `data/doppel/public-memory-official-regrade-preflight-v1.json`, SHA-256
`966c6236477a6a0338ab85d9fbfbe1f0f0a0fc64763cc8ff3b4f51d47dab6abb`.
Plan fingerprint:
`eb98ca3d1cdadbd2219c60756d04a481da40042534d3a834d85386503026733b`.
This binds source/manifest, original answers, row order, exports, exact requests,
transport settings, scorer/runtime source and endpoint. Exports and future receipts
live in `data/doppel/public-memory-official-regrade-v1/`, an ignored local directory.

## Upstream alignment and deliberate wrapper differences

The [vendored snapshot and MIT attribution](../upstream/longmemeval/README.md)
record the source URL and canonical-LF content hash. An upstream commit ID was
not resolved; do not describe the snapshot as commit-pinned. Runtime extracts only
the hash-checked `get_anscheck_prompt` function; it does not execute the upstream
imports, CLI or backoff wrapper.

Unchanged upstream scoring settings:

- Model: `gpt-4o-2024-08-06` (no automatic model migration or fallback).
- Exactly one user message containing the upstream category-specific prompt.
- `temperature=0`, `n=1`, `max_tokens=10`.
- No system prompt, JSON schema/mode, thinking parameter or extra judge criteria.
- `_abs` in the question ID selects the original unanswerable-question prompt.
- Original parsing: strip text, then case-insensitive substring `yes`.

The wrapper also reports exact yes/no validity and finish reason. An ambiguous
or truncated completion preserves its original upstream label but stops this run;
it is not counted as a clean verdict. HTTP/model-shape/authentication errors stop
without automatic retry. HTTP status and allowlisted error codes are retained,
not bodies, headers or API keys. Returned model identity must match the snapshot;
a compatible service's model string is not independent proof of authenticity.

Durable allowance: **at most 28 new HTTP attempts**, including failed attempts,
with a 100 KB local request-envelope limit per attempt. Serial execution, immutable
stage receipts, interruption markers and content-addressed cache prevent silent
rebilling on resume. Missing usage is unknown, not zero. No exact currency cap or
invoice attribution is claimed. The 28 actual wire request bodies total 34,210
UTF-8 bytes; this is not a token estimate. No full histories are sent to the judge.

## Run on the official endpoint

Free preflight has already completed. Do not overwrite its output. In PowerShell 7,
set the key in the same window that will run Python, without putting it into a
command-history literal or repository file:

```powershell
cd D:\project\Doppel
$env:OPENAI_API_KEY = Read-Host 'OpenAI API key' -MaskInput
```

Then, only when an account can call the exact GPT-4o snapshot:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_memory_official_scoring `
  --live `
  --frozen-preflight data/doppel/public-memory-official-regrade-preflight-v1.json `
  --output data/doppel/public-memory-official-regrade-live-v1.json
```

This reads only `OPENAI_API_KEY`, not a DeepSeek key. Default endpoint is
`https://api.openai.com/v1`. No Docker or GPU is required. If this window closes,
its environment variable disappears. A compatible service needs its own explicit
`--base-url`, **new run directory and new frozen preflight**, with the channel
recorded as unverified; do not run it against the official-endpoint plan.

If execution stops, preserve the failed receipt and report. Do not delete receipts
or create a fresh directory merely to evade the cap. Any paid retry/recovery needs
an explicit new plan and cumulative accounting; the CLI does not do that itself.

After a complete live run, reproduce verdicts without a key:

```powershell
Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m benchmarks.public_memory_official_scoring `
  --live --cache-only `
  --frozen-preflight data/doppel/public-memory-official-regrade-preflight-v1.json `
  --output data/doppel/public-memory-official-regrade-replay-v1.json
```

## Reporting and follow-up

Report per-arm ordinary/refusal counts, original-vs-official label disagreements,
raw verdict, strict validity, returned model, usage and zero-call replay. A new
judge is not infallible; disagreement calls for inspecting the unchanged answers,
not automatically declaring the former or latter label true. Official QA scoring
does **not** grade citation faithfulness or detect every plan-to-fact overstatement.
Keep that separate semantic diagnosis visible. These answers used DeepSeek Readers,
so official GPT-4o grading does not make this an AML academic-compliant run.

As of this freeze: exports/preflight and fake-HTTP tests completed; **zero live
GPT-4o requests**, no official labels. OpenAI key/channel setup is outstanding.

Validation: 49 new offline tests; full suite **1,627 passed, 33 skipped, three
subtests passed** (one existing Graphiti/Pydantic deprecation warning). Whole-repo
Ruff passes; both new Python files pass format checks and Pyright. All frozen
source/export hashes were rechecked after the final code changes. The full-suite
result is not a live API or benchmark-quality result. `uv.lock` remains untouched
and unstaged; no database/journal/index/old cache modifications were made.

After regrading, prepare a separately frozen generic Reader-policy correction:
clearly distinguish new advice, plans, completed experience and explicitly stated
versus directly inferable premises. Validate on unrelated controls before touching
these opened answers. Do not add question-, entity- or benchmark-specific branches.

Do not extend expensive S eager backfills now. Retain existing graph assets for
later eager comparison. Any lazy/query-time analysis remains competition-only
experimental work, not a replacement for Doppel's long-term personal-memory core.
