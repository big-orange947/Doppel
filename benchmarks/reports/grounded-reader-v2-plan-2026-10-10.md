# Grounded Reader V2: generic controls, then gated paired diagnosis

Candidate instructions extend unchanged `grounded_advice_v1` with source-modality
preservation, directly supported inference instead of exact wording requirements,
coherent conclusions and question-language consistency. Input/output schema,
source authority and time metadata are unchanged. No core/default switch, parser
special cases, question keywords, retrieval, graph or database writes.

The nine [frozen synthetic controls](../datasets/reader-grounded-policy-controls-v1.json)
cover elapsed plans, new advice grounded in plans, explicit later completion,
direct causal paraphrases, unsupported correlation, arithmetic, assistant/owner
conflict, historical assistant advice and source/question language differences.
They do not reuse opened questions, entities, numbers or reference answers.
Their scoring rubrics never reach the Reader. Control text is test data, not
runtime query/answer handling logic.

Controls compare fresh baseline/candidate outputs: nine rows × two policies,
**at most 18 Reader calls and no judge calls**. Provider configuration remains
DeepSeek Flash, thinking disabled, temperature 0, json_object, max_tokens 2048.
Use a new budget/cache directory, preserve all old receipts and failures; no retry.
Order alternates per context. Stop after structurally invalid citations/derivation
or failed attempts; do not repair an output.

Preflight: `data/doppel/grounded-reader-v2-controls-preflight-v1.json`, SHA-256
`81fca77a65788bd1165d3d8cd0da45f13b6403e9188ad3e5834f68e748c2e4fa`.
Plan: `bf24641a28246c4c80ddaf7047e308e9448ce1b7dfa3743b972cfdedcf826cd1`.
Run directory: `data/doppel/grounded-reader-v2-controls/`.

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_memory_grounded_reader controls `
  --run-dir data/doppel/grounded-reader-v2-controls `
  --live --frozen-preflight data/doppel/grounded-reader-v2-controls-preflight-v1.json `
  --output data/doppel/grounded-reader-v2-controls-live-v1.json
```

Semantic review is **manual by Codex, not independent validation**. Review all
18 outputs against the unchanged rubrics, preserving baseline failures. Decisions
must bind the complete output hash and exact answer/source quotations. The tool
checks identities, complete coverage and quote anchoring, **not the truth of a
semantic judgment**. State this limitation in results. Structural validity alone
does not pass the semantic gate. All nine candidate rubrics and structural checks
must pass; baseline must be reviewed but need not pass. No criterion relaxation or
control edits after outcomes. Failure ends this candidate run without paired work.

Only if that gate passes, freeze a separate paired preflight using exactly the
previous seven opened questions in 14 unchanged S/raw and full-session contexts.
Fresh `grounded_advice_v1` versus `grounded_advice_v2`: at most 28 Reader and
28 short DeepSeek judge calls, pinned LongMemEval prompts, no official-model claim.
This is a downstream response-policy diagnosis, not a retrieval ablation. References
go only to the judge. Preserve old answers/labels and expose disagreements. Inspect
plan-to-experience claims separately from task labels, since the QA judge does not
see source citations. No new S graph backfill or unopened cases.

Every phase uses a durable attempt cap and an observed 1 CNY debit stop before the
next call. This is not exact billing attribution or a hard currency ceiling.
Secrets are environment-only. Cache-only child-process replay needs no key and
must reproduce complete rows. Controls and paired artifacts remain ignored/local.

Pre-live: 17 new offline tests, 52 directed tests passing; Ruff/new-file Pyright
pass. A full regression run will be reported separately. No paid calls before
the preregistration commit; `uv.lock` remains unstaged.
