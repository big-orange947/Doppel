# Isolated speaker review V2: fewer false flags, incomplete fix, 2026-11-11

Frozen implementation `1e1be61`; [prospective plan](source-attribution-controls-plan-2026-11-11.md).
All twelve provider attempts and all eight case/profile runs completed, without
retry, invalid quote, response repair or rubric change. Annotation policy retained
all input contents; no Store/index writes, extraction, QA, embeddings or graph.

This is four authored development controls with eight drafts per arm, not a
representative precision/recall estimate or independent evaluation. The candidate
does not replace the default analyzer or V1 review. No previous opened lifecycle
case was re-executed or shown repaired here.

## Actual control observations

| Metric | V1 joint review | V2 isolated, speaker-framed review |
|---|---:|---:|
| Draft judgments matching frozen labels | 6/8 | 7/8 |
| False high-confidence flags on four supported drafts | 1 | 0 |
| Missed flags on four contradicted drafts | 1 | 1 |
| Uncertain decisions | 0 | 0 |
| Review calls | 4 | 8 |

Both correctly classified the two-person monitor predicates, Chinese contact vs
sibling negation, and assistant possibility vs owner completion. The final
distraction case passed in both; do not claim the live result proves V1 actually
used the other draft's source there. V2's physical absence of uncited sources is
separately enforced and tested, regardless of a review's semantic verdict.

The difference and remaining failure are in embedded speech:

> Omar told me, 'I cancelled my pass.' I renewed mine.

Source actor is the account owner. The supported draft is “The owner renewed
their pass.”; the contradicted draft is “The owner cancelled their pass.” Here
`owner` denotes Doppel's account-owner role, not any person owning a pass.

V1 flags the correct renewal with confidence 0.95, reasoning that the narrator is
“not clearly the owner” and that “the owner (Omar) cancelled”. It labels the wrong
account-owner cancellation supported, confidence 0.9.

V2 correctly supports renewal, confidence 0.9: “The quoted cancellation belongs
to Omar, not the owner.” But its separate cancellation judgment still says
supported, confidence 0.9: “The quoted first-person speech reports the owner
(Omar) cancelled his pass”. These incompatible interpretations of the same source
remain a genuine control failure. The quote is verbatim and correctly source-bound;
that does not make the subject interpretation correct. No label was relaxed or
additional attempt used to seek a better result.

## Implemented behavior and limits

The optional `SourceGroundedPersonalMemoryAnalyzerV2`:

- Reviews each draft in an independent request containing only its cited messages.
- Adds trusted source actor/subject identity frames, with opaque IDs derived from
  scope for owner/agent and source sender_id for contact.
- Prechecks all per-request byte limits before calling; validates exact coverage
  and original quote text after each response before making the next request.
- Retains the existing annotate policy, candidate content, authority gates and
  `semantic_support_verified=false`. No automatic confirmation, repair or deletion.
- Has a separate version identity. V1 instruction/schema/request shape and its
  version-binding formula remain compatible; offline tests pin those invariants.

This is a joint intervention, not evidence that frames alone or isolation alone
caused the single corrected judgment. One review per eligible draft increases
cost up to `config.max_drafts` calls per window, rather than one. Neither model
confidence nor exact quotes certify meaning. Withhold remains opt-in experimental;
these results do not justify making it a default safety gate.

## Accounting and replay

Requested/returned model: `deepseek-flash`, finish `stop` in all twelve receipts.
No pinned model snapshot. Json-object, temperature zero, thinking disabled and
max output 2,048 were frozen before execution.

| Profile | Calls | Input tokens | Output tokens | Total tokens |
|---|---:|---:|---:|---:|
| V1 | 4 | 3,228 | 561 | 3,789 |
| V2 | 8 | 8,001 | 658 | 8,659 |
| Total | 12 | 11,229 | 1,219 | **12,448** |

All calls have complete reported usage; no inferred free/zero-cost failures.
The candidate used about 2.29 times V1's reported total tokens on this sample.
That is an observation, not a universal cost multiplier or currency estimate.
Twelve new model calls are source reviews, not independent manual adjudications.

Cache-only replay: twelve hits, zero new attempts, identical rows and summary.
Result digest: `c220f6c8d6ae969ee4f64d4c5a409a4966e0543c5e2e1a83ed8dd704ec88f767`.
Artifacts: `data/doppel/source-attribution-controls-v1-{preflight,live,replay,summary}.json`;
the summary binds artifact hashes, per-profile usage and provider metadata. Run
directory `data/doppel/source-attribution-controls-v1` retains cache, receipts and
durable ledger. No real chat, credentials, database cleanup or Docker work.

## Validation and next work

Thirteen new offline controls plus the existing source-grounding suite: 30 tests
passed. Full-repository Ruff, changed-file formatting and candidate/runner Pyright
passed. Full-repository regression: **2,589 passed / 33 skipped / 3 subtests
passed**, one existing Graphiti/Pydantic deprecation warning, no test failures.

Keep this candidate available as an explicit source-isolation option. The next
quality step should bind source clauses/perspective during extraction, before
free-form paraphrasing, and then test a full fresh synthetic lifecycle. Another
unverified review label cannot substitute for fixing the ambiguous representation
or establish that the original blocked bicycle case is now solved. Preserve all
failed controls and use fresh prospective data for subsequent candidate changes.
