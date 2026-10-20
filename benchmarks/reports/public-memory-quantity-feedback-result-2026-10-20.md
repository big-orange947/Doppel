# Opened quantity routing: four-call result

Implementation/protocol were committed and pushed as **ae92d02** before paid
execution. All8 prior candidate views and query results were first replayed from
completed analyzer/planner receipts and checked exactly against the parent
report. Select its4 count plans by operation only; no old QA grade selection.

This is candidate-routing validation on opened development examples, not new QA
accuracy, independent validation, full LongMemEval or AML scoring. It does not
replace37/50 or the previous provisional raw6/8–structured7/8.

## Actual results

| Ordinal | Original hits | Discovery hits | Final hits | Model route | Applied |
| --- | --- | --- | --- | --- | --- |
| 03 | 0 | 4 | 4 | reported_quantity, confidence0.72 | yes |
| 05 | 4 | 7 | 4 | enumerate, confidence0.55 | no |
| 12 | 2 | 10 | 2 | enumerate, confidence0.55 | no |
| 19 | 3 | 3 | 3 | enumerate, confidence0.72 | no |

Ordinal03 now returns both relevant owner assertions:

- “Watched12 films in the last3 months, including5 MCU films.”
- “Watched4 MCU films in the last3 months (as of May2023).”

The previous count+episode gate excluded both state records. The actual refiner
recognizes reported quantities rather than counting their source messages, and
changes operation to lookup with no memory_type restriction. Both assertions
remain candidates; the refiner does not generate an answer, pick a winner or
overwrite either record. The final lookup also retains2 related planned movie
activities, explicitly tagged plan/planned. **Four hits is not the answer4**:
count.status=not_requested and value=null. Added context is not uniformly direct
answer evidence; downstream consumers still need attribution/type metadata.

The other3 cases preserve their original plans and exact original hits; no false
switch to reported-quantity lookup was observed here. Their counts remain
indeterminate, not asserted complete totals. Ordinal19 asks about distinct days;
preserving its enumeration route does not add a distinct-day aggregation
executor or equate event cardinality with days. Those semantics remain explicit
limitations. A model's route confidence is not probability calibration or proof
of global count completeness.

Totals:9 original hits,24 discovery hits,13 final hits;0 whole-item omissions,
13 model support links all bound to supplied candidates. No observation horizon,
query time range, scope, subject, authority/lifecycle, relevance or relation gate
was relaxed. The permitted changes are retrieval operation and planner-derived
memory_types only, with legacy intent projection, planner audit identity and
integrity hash rebound. Final lookup reloads authoritative Store records.

## Cost and replay

-4 new feedback calls,4 succeeded;0 retry, failure or missing usage.
-5714 input tokens (768 provider-cached),1047 output, **6761 total tokens**.
-19378 canonical request bytes total; within frozen4-call/30KB-per-request/
  120KB-cumulative request budget.
-0 new extraction/planner/Reader/judge/embedding/graph calls;0 persistent source
  writes; reserved histories remain closed. Existing extraction is replayed
  locally, not paid again. No new answer score is available.
-Separate process cleared DEEPSEEK_API_KEY and used cache-only mode:0 new calls,
  byte-identical output and cumulative usage. No key persisted.

Artifacts (ignored):

- Preflight: data/doppel/quantity-feedback-preflight-final-v1.json
- Plan: ec718e9b3890a0c47ec361da21909db54a39713068f129f9f552a9d16b0bed89
- Live: data/doppel/quantity-feedback-live-v1.json
- Replay: data/doppel/quantity-feedback-replay-v1.json
- Live/replay SHA-256:
  bd8f38b6b10ba08c7ce19bc2df881f755621e215986c426d02ab8f8655d1bdc1
- Durable run directory: data/doppel/quantity-feedback-v1

## Verification and next boundary

Sixteen new offline tests cover reported-total routing, preserved enumeration/
uncertainty/low confidence, unchanged trusted plan coordinates, subject/actor/
scope/lifecycle/observation eligibility, invalid support, whole-item byte bounds,
tampered plan rejection, empty/non-count skips, Store deletion during feedback,
and budgeted fake-provider/key-free replay. Related suite182 tests pass; full
suite **2135 passed,33 skipped,3 subtests**; Ruff and new-file Pyright pass.
The extension stays module-only opt-in; default query behavior and root API
remain unchanged. uv.lock was not modified or staged by this work.

This establishes a recovered candidate path, not a generalized quality win.
Next validate across newly frozen, cross-domain quantity/anchor controls and
bounded opened cases before promotion. Extraction decision-to-completion errors
and time precision/bounds inconsistencies are still uncorrected; retaining raw
sources and candidate labels does not make those interpretations true. Do not
add domain nouns/IDs as routing rules, harden a speculative date as fact, or spend
another full-history extraction pass merely to retest an existing candidate pool.
