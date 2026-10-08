# Reader v2: completed development run, no new QA score

## Scope and outcome

Starting commit `2d4c870`; implementation, 23 offline tests and the
[reader-only plan](public-memory-reader-v2-plan-2026-10-08.md) were committed as
`ca21837bc183ddbdf2355c2450527061912c104b` before live execution.

The 18 preserved packed contexts produced **18 completed outputs through 16 distinct
requests**, zero failed requests and no retries. Key-free cache-only replay reproduced
all outputs, derived blocks, structural checks and metrics exactly with zero calls.
No Judge, retrieval, extraction, index, Store or reserved-history operation ran.
The old Judge v2/v2.1 failures remain failed; their blocked arms were not executed.
This is a separate Reader-only protocol, not a replacement passing Judge gate.

Same model and all generation parameters as Reader v1: DeepSeek v4 flash,
json_object, temperature 0, thinking disabled, 2,048 maximum completion tokens,
120-second timeout. Only generic instructions/schema changed. No case-specific
values, entities, query rules or gold were added to Reader requests; old answers
appear only in side-by-side reporting. Core retrieval/memory algorithms did not change.

## Structural and behavioral observations

| Observable | Result | What it does not establish |
| --- | ---: | --- |
| completed outputs | 18/18 | correct answers |
| structurally valid outputs | 18/18 | evidence support or arithmetic correctness |
| derived blocks | 7/18 | justified derivations |
| abstained flags | 4/18 | appropriate refusals |
| abstention flags changed versus v1 | 0/18 | unchanged semantic quality |
| answer strings changed versus v1 | 18/18 | improvement |

All cited and derived-input IDs belong to their supplied contexts. No duplicate,
unknown or uncited derivation ID, and no derived-plus-abstained structural conflict.
Checks do not inspect gold substrings or infer semantic absence/entailment.
`answer_correct`, `citation_supported` and semantic abstention consistency remain
**null**, with `qa_metrics_available=false`. Derived blocks occur at rows 2/3
(temporal-status inference) and 6/8/9/10/11 (conditional arithmetic); row 7 has none.
Refusal flags remain true at rows 0/4/14/15. These describe output fields, not scores.

### Visible unresolved behavior, not a completed semantic audit

All three original questions are English. On inspection, **16 of 18 answer bodies
are predominantly Chinese**; only rows 14/15 are English despite language-following
instructions. This visible instruction-adherence problem is not an independent
language-classifier result. No automatic translation or post-run prompt change was used.

Row 7 still withholds the per-item price and keeps `abstained=false`. It cites a
total-cost record and a separate quantity record, but expresses uncertainty that
they describe the same purchase. Its opening missing-count claim and later quantity
mention need source-bound review. The new partial-answer rule also means old
flag-consistency labels cannot simply be copied across. Structural validity does not
settle whether the refusal, qualification or flag is defensible. Other arithmetic
rows record conditional results; this stage does not count them correct automatically.

Rows 2/3 infer held status from eligibility wording and qualify that assumption.
A valid derived block does not prove eligibility equals actual possession. Rows
12/13/16/17 answer from assistant records; citation legality alone does not establish
complete or faithful recommendations.

This run establishes **reproducible outputs**, not that Reader v2 is better. No v3
prompt, new QA count, profile winner or default strategy was selected after inspection.

## Usage and accounting

Sixteen new Reader requests, zero Judge requests/retries/missing usage reports.
Reported usage: **62,842 input + 3,930 output = 66,772 tokens**, including 13,568
cached input tokens and zero reasoning tokens. Sixteen of the fixed eighteen lifetime
attempts were used; unused attempts were not spent on extra samples.

Reader v1 used 58,031 reported tokens for sixteen requests. V2 uses 8,741 more,
approximately **15.1%**: token-volume overhead, not a billing, latency or
quality-adjusted efficiency result. No hard total-token cap or exact billing
guarantee is claimed. Old calls and costs remain separately preserved.
An attempted run directory only permits cache-only replay, not further paid attempts.
No failure repair, resampling, hidden retry, old-cache rewrite or budget reset occurred.

## Provenance and reproduction

Plan fingerprint:
`45c4f617c95f86d5c367651903eba9f15dbba1d2a5618becf99e8fc22196a969`.

| Ignored local artifact | SHA-256 |
| --- | --- |
| `data/doppel/longmemeval-reader-v2-preflight-v1.json` | `d0d2340bc923a7f77e961b33156a0db8d51c9a9d06639f5c7d2308038aabf4d2` |
| `data/doppel/longmemeval-reader-v2-live-v1.json` | `89c83feeff2ecb187bd51dfb3b820e5c9285c5518920c131fb9745d1e77549db` |
| `data/doppel/longmemeval-reader-v2-replay-v1.json` | `5a57b588b9b210b009566e75732140ab52926cb94be87e6d16b7cfc07031e032` |

Run directory: `data/doppel/public-memory-reader-v2-v1`. Live execution records
`ca21837` with only the pre-existing `uv.lock` tracked modification. Module SHA-256:
`1c4cc3e6e0fb88f4e057acac0620b1227ef16daf1a2a84c4656c6d6c0152002a`.
Core runtime hash remains
`508a9787a13159bcba494f3a37f44dc3dac0b9850fad9312259d38a49fbe4ce7`.

A separate-process replay removed `DEEPSEEK_API_KEY` and used `--live --cache-only`:
`api_key_read=false`, 16 cache hits, zero new calls, unchanged cumulative sixteen
attempts. Serialized outputs/checks/metrics were compared directly. File hashes differ
because execution/cache metadata differ. No key is printed or persisted in artifacts.
Old answer baseline, retrieval comparison, failed v2.1 controls and `uv.lock` hashes
were rechecked unchanged after live. Source hashes, canonical baseline content,
actual request hashes and unchanged generation settings are bound before execution.

## Verification and next stage

- **23 new offline tests** pass: blinded requests, derivation schema, structural
  checks without semantic grading, source/baseline/config binding, fixed caps,
  no rebilling, failure retention, redaction, key-free preflight and replay.
- Full suite before live: **1,247 passed, 33 skipped, 3 subtests passed**; one
  upstream Graphiti/Pydantic deprecation warning.
- Repository Ruff lint passes; new Python files pass format checks; scoped Pyright
  with the workspace interpreter reports zero errors and warnings.

Stop at the planned boundary. Next: source-bound semantic review of the actual v2
outputs, especially same-event derivation inputs, absence/partial-answer scope and
eligibility versus held status. Keep disputed judgments explicit instead of fitting
another Judge taxonomy to six controls. Then freeze an unopened-history stage to
test transfer before changing defaults or claiming generalized gains. Language drift
needs a separately bounded intervention, not silent repair of these stored outputs.

Three opened questions are not complete LongMemEval, independent validation, a blind
benchmark or an AML score. No new QA count supersedes the old v1 audit's lenient
13/18 or strict sensitivity 9/18 reading.
