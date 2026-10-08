# Reader v2: frozen reader-only opened-context development comparison

Starting commit `2d4c870`. This is a **new Reader-only protocol**, not a passing
replacement for the failed Judge v2/v2.1 gates. Keep both failed gates, expectations,
old answers and scores unchanged. Do not execute either judge's blocked rows arm.

## Intervention and scope

Implement generic answering instructions and an optional `derived` block with kind,
input memory IDs and result. Permit justified arithmetic/inference, state assumptions,
avoid inventing equal allocation or completed events, check every supplied item
before claiming an input is missing, and scope absence claims to supplied items.
Keep answer/abstention consistent and follow the question's language. Preserve source
authority and assistant recommendations without turning assistant text into owner
facts. Distinguish observed time from effective time and do not assume newest wins.

No entity/value-specific instruction, query rewrite, source expansion, packing change,
retrieval change, new memory extraction or core algorithm intervention. Same 18 packed
contexts from the three opened questions. Same model and **all generation settings**
as v1 (DeepSeek v4 flash, json_object, temperature 0, thinking disabled, 2,048 output
tokens, 120-second timeout). The only intervention is Reader instructions/schema.
Baseline and gold are absent from Reader requests. Gold is not used for structural
checks. Old answers appear only in the side-by-side reporting artifact.

## Binding and accounting

Frozen comparison: `data/doppel/longmemeval-memory-comparison-v1.json`, SHA-256
`a152356232524db418bcdcc9b6104f9ce90c8d94627338effd379440e7195ae7`.

Frozen v1 answer baseline: `data/doppel/longmemeval-answer-comparison-v1.json`, SHA-256
`ba005911d5639394ea473dcc1a52d8711c036a74f7fdd67079ef14c22cedbdbd`.

Original manifest/dataset integrity checks and diagnostic partition selection remain.
Each old row must match the reconstructed v1 request hash, index, case and profile.
The new plan binds actual v2 request hashes, source hashes, canonical baseline content,
prompt/schema, model settings and a fixed lifetime **18-new-attempt cap**. Identical
requests deduplicate; no retry/repair. An attempted run directory can only be replayed
cache-only, not resumed with new paid attempts. New cache/run/budget identity; v1
caches, databases, reserved groups and user-owned `uv.lock` unchanged.

Zero-provider preflight reconstructs 18 logical rows and **16 distinct requests**.
Frozen executable plan fingerprint:
`45c4f617c95f86d5c367651903eba9f15dbba1d2a5618becf99e8fc22196a969`.
Ignored preflight artifact `data/doppel/longmemeval-reader-v2-preflight-v1.json`,
SHA-256 `d0d2340bc923a7f77e961b33156a0db8d51c9a9d06639f5c7d2308038aabf4d2`.

Commit implementation, tests and this plan before paid execution. Use the existing
environment key without printing or persisting it. No Judge calls (cap **0**), no
paid control-label calibration, no citation-order arm. No other paid tasks this round.

## Report, not a score

Report completion/failure, per-row old/new answers and citations, abstention changes,
derived blocks, source legality, duplicate/uncited/unknown derivation sources and
derived-plus-abstained structural conflicts. Preserve outputs with structural issues;
flag them without silently repairing, grading or retrying them.

These checks do **not** verify arithmetic, semantic entailment, answer correctness,
absence truth, language or natural-language/flag consistency. `answer_correct` and
`citation_supported` remain null; `qa_metrics_available=false`. Changed answers,
fewer refusals and more derived blocks are not automatically improvements. No default
retrieval-profile ranking is selected. No automated numeric QA claim from the old
unreliable judge or from reference-value substring matching.

After live execution, replay in a separate process without a key using cache-only;
verify equal answers, derived blocks, structural checks and metrics with zero new
calls. Preserve failures and usage; missing usage is unknown, not zero. Stop after
recording outcomes. Any grounded semantic audit, primary-label re-scoring or unopened
history evaluation is a separate stage, not silently folded into this run.

## Validation and limitations

Offline fake tests cover payload blindness, optional derivation schema, no semantic
claims from legality, request/context/baseline/config binding, fixed caps, retained
failures, no rebilling, redaction, preflight without keys and cache-only replay.
Run full tests/lint/types before live execution. Synthetic tests validate software
contracts, not model intelligence. Three opened questions are development diagnostics,
not full LongMemEval, independent validation, blind evaluation or AML results.
