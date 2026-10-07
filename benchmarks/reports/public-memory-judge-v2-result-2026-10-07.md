# Judge v2: control-arm result and stopped rows arm

This follows the [frozen plan](public-memory-judge-v2-plan-2026-10-07.md). The real-model
test ran on the six frozen controls; **the gate failed and the preserved-rows arm was not
executed**. Reader v1, all preserved answers, the original judge labels, the provider
caches, the Store and the three reserved histories are untouched. No mid-run policy
change was made and no control expectation was adjusted after seeing output.

Still a three-question opened diagnostic, not a full LongMemEval run, a blind
evaluation, an independent verification or an AML academic score. There are **no
rows-arm results**: none exist and none are implied by the controls.

## What ran

| Step | Result |
| --- | --- |
| Preflight, rows arm (zero provider) | 18 logical rows, **16 distinct requests**, no profile names, old labels or audit labels in any request |
| Preflight, controls arm (zero provider) | 6 controls, 6 distinct requests |
| Live controls arm | 6 new calls, 0 failures, 10,620 reported tokens (8,757 in / 1,863 out), 0 store writes |
| Gate | **failed** — 2 of 6 controls disagree with their frozen labels (C3, C4); all outputs schema-valid |
| Preserved-rows arm | **not executed** (18 of the planned 24 calls unspent) |
| Cache-only replay | not run; there is no rows-arm result to replay |

Artifacts: preflight rows `data/doppel/longmemeval-judge-v2-preflight-v1.json`
(`b8a36428…`), preflight controls `…-preflight-controls-v1.json` (`e9c8a78c…`), live
controls `…-judge-v2-controls-v1.json` (`aa05f096…`), run directory
`data/doppel/public-memory-judge-v2` with the bound plan and six cached judge responses.

## Control results

Four of six controls matched all five frozen dimensions on the first live attempt.

| Control | answer_match | commitment | citation_support | contradiction | faithfulness | result |
| --- | --- | --- | --- | --- | --- | --- |
| C1 grounded refusal restating a fact | incorrect | refused_unavailable | supported | false | grounded | **match** |
| C2 conditional derivation | correct | hedged_derivation | supported | false | grounded | **match** |
| C3 refusal on a contradicted premise | incorrect | refused_unavailable | partially_supported | true | partly_grounded | commitment mismatch |
| C4 no-record answer with no claims | incorrect | refused_unavailable | unsupported | false | grounded | support mismatch |
| C5 assistant recommendation | correct | committed | supported | false | grounded | **match** |
| C6 temporal previous/current | correct | committed | supported | false | grounded | **match** |

All citation quotes in all six controls were verbatim hits **inside the single record
they named** (10 of 10 entries), and all 7 absence-claim quotes were found in the answer
they came from. The lenient rule worked as frozen: C2's hedged derivation was matched as
correct, and C6 resolved previous-versus-current by observation time while both records
carried the same `current` label.

## The two mismatches

**C3 — the taxonomy branch, not the reasoning.** The judge detected the contradiction
itself: it flagged `citation_contradiction=true`, `citation_support=partially_supported`,
`faithfulness=partly_grounded`, and its absence check marked the claim "the records do
not say how many mugs you bought" as false for the supplied context. Its own
commitment reason says the candidate *"declines to compute the per-mug price, reporting
that the number of mugs is not recorded, **though the supplied context does state 5
mugs**"*. It nevertheless chose `refused_unavailable` instead of
`refused_conflicting_premise`. The refusal read literally ("I cannot compute") is
indistinguishable from an unavailability refusal unless the model is told to escalate
it; the label should not depend on that choice.

**C4 — the scope of "I have no record".** The answer says it has no record of the
conversation and that the supplied items contain no such recommendation. The judge set
`answer_makes_factual_claims=true`, which made the derived support `unsupported` instead
of `not_applicable`. Its reason shows the reading: *"declines to provide the requested
recommendation and reports that no record of it exists in the supplied items"* —
correct about the content, but treated "I have no record of X" as a claim rather than an
items-scoped absence report. The frozen definition ("false only when its sole
assertions are about what the supplied items do or do not contain") did not settle a
statement about the assistant's own record, and the judge's other four dimensions were
right.

Neither mismatch is a hidden quality score: in both cases the judge's *evidence* is
correct and the frozen label rule is what the model had to guess. The gate did its job
by stopping the arm that would have produced sixteen judgments under an ambiguous rule.

## What is proposed for v2.1 (nothing changed here)

1. **Derive the commitment escalation in code.** Keep the model's base commitment, then
   set the row to `refused_conflicting_premise` deterministically when the answer is a
   refusal (or reports unavailable information) **and** any of its absence claims is
   false for the supplied context, or any cited record contradicts a claim in it. This
   is the same failure the audit found in row 7 and removes the model's taxonomy guess.
2. **Close the claims-scope definition.** Add one frozen sentence: a statement that the
   assistant has no record of something, when the answer scopes it to the supplied
   items, is an items-scoped absence report and does not by itself make a factual claim.
   In addition, report (do not enforce) a `claims_scope_conflict` flag when
   `answer_makes_factual_claims=true`, every absence check is true and there are no
   citations, so the ambiguity is visible in the results instead of silently changing a
   support count.
3. **Keep the frozen control expectations unchanged.** C3 still expects
   `refused_conflicting_premise` and C4 still expects `not_applicable`; the fix is in the
   rubric and the derived rule, not in the tests. Adjusting the controls to match the
   model would destroy the gate's meaning.
4. **Re-freeze and re-run.** A v2.1 plan binds the new rubric hash and a fresh budget
   identity: controls ≤ 6 calls, preserved rows ≤ 16–18 calls, no retries, failures
   preserved. The six calls spent here are sunk and are not "refunded" by the new
   identity; the failed control report stays as evidence.

## Accounting and verification

- New calls this stage: **6** (all in the controls arm), 10,620 reported tokens, 0
  missing usage, 0 failed attempts, 0 retried requests. The 18-call rows budget was not
  touched.
- Deterministic guarantees verified by the preflight and by the run's own checks:
  no profile name, original judge label or audit label in any judge request; no
  reference-answer phrase check in the pipeline; no retrieval/packing attribution
  emitted; `not_applicable` never counted as supported (four offline tests cover the
  support rule, the counts and the cache-only path).
- Offline verification before the run: **24 judge-v2 tests pass** and the full suite is
  **1204 passed, 33 skipped, 3 subtests passed**; Ruff clean; Pyright reports no error in
  the new files (the 21 remaining whole-repo notices are the known missing optional
  `graphiti`/`fastembed`/`neo4j`/`asyncpg` installs).
- The gate is a rubric check on synthetic controls, not a score; a passed gate would not
  have proven the judge correct on the opened questions either.

## Limits

Six synthetic controls cannot validate a judge. The rows arm has no results, so this
stage says nothing about the eighteen preserved answers under Judge v2. The two
mismatches are diagnosed from the judge's own quoted reasons, not from a second human or
model review, and the v2.1 fixes are proposals: they must be frozen, committed and
re-gated before any preserved-row judging happens.
