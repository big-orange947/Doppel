# Reference-only task accuracy over frozen fifty-question answers

The first fifty-question run completed all 150 Reader/primary-Judge rows and
replayed identically without a key. Spot inspection then exposed a scoring defect:
the primary Judge accepted eight owner-memory pure refusals on answerable
assistant-history questions, explicitly excusing them because retrieval omitted
the answers. Those responses can be justified refusals without being correct
benchmark answers. Keep the original labels, Reader outputs, caches and reports.

This single bounded regrading assesses task accuracy separately from supplied-
context support. It sees only question, reference answer and immutable candidate
answer text. No retrieved context, profile, abstention flag or previous grade is
sent. A pure refusal on a reference-answerable question is incorrect; a qualified
derivation that provides the expected result can be correct. Preserve incompatible
answers and arithmetic errors. Use one generic instruction for all questions.

## Frozen execution

- Original QA report SHA-256:
  `89c1e888f278b71bd4df87446604db8a2bc5ee7e65647af03dadc235c67189aa`.
- Dataset SHA-256:
  `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
- Preflight SHA-256:
  `a480f4626903ecd368bb4cbc93de56ccaa1b48256f959f38862e765294620b8e`.
- Plan fingerprint:
  `37712b516d8b8a32e1ffba18874072ce686e79825f03dcac0f036ff5f1137cbb`.
- Six frozen unrelated synthetic controls: exact answer, answerable refusal,
  qualified arithmetic, reference-unanswerable refusal, wrong arithmetic and
  contradictory answers. All six must match their fixed expectations before the
  150-row arm. Passing these controls only checks this known scoring boundary.
- Durable cap: 6 control attempts + at most 150 grading attempts = 156, single
  attempt per request, no retries. Identical requests may share cache. Preserve
  invalid/failed outputs and unscored rows. Do not repeat Reader or retrieval.
- DeepSeek v4 flash, JSON object, temperature 0, thinking disabled, max_tokens
  768, timeout 120. New instructions/schema/source/request hashes and budget
  identity; old scorer files and expectations are unchanged.
- Correctness denominators are separate from the old support-quote gates. The
  two unanchored primary support observations remain unanchored; this stage does
  not fix or reassess citation support. Labels remain same-model provisional.

```powershell
& D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_task_accuracy `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --answers data/doppel/longmemeval-expansion-50-quality-v1.json `
  --run-dir data/doppel/public-memory-expansion-50-task-accuracy-v1 `
  --output data/doppel/longmemeval-expansion-50-task-accuracy-v1.json `
  --frozen-preflight data/doppel/longmemeval-expansion-50-task-accuracy-preflight-v1.json `
  --live
```

Read the key only from `DEEPSEEK_API_KEY`. Follow with key-free `--live --cache-only`
replay to a fresh output. Report full fifty-question denominators, type groups,
failures and label changes. This is a public diagnostic, not an independent blind
evaluation, complete LongMemEval or AML score. No case-specific production rule,
new context selection, source write or reserved-history execution is introduced.
