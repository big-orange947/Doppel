# Judge v2.1: one bounded revision, preserved Reader v1 answers

Starting commit `1f72a2b`. Keep v2 code, artifacts, six spent calls and control
expectations unchanged. No Reader, retrieval, ingestion, index, DB, reserved group
or core algorithm changes. `uv.lock` belongs to the user and is not staged.

## Narrow rubric revision

New module/plan/cache/budget identities. Same output observations with a new schema
title and instruction hash. Explicitly classify supplied-items-scoped "I have no
record" as context reporting, not by itself a person/world fact. A global claim
that an event never happened remains assessable. Mixed restated facts remain claims.

Preserve model commitment, then derive `refused_conflicting_premise` only for an
explicit model refusal with a model-observed false absence claim or cited-record
contradiction. This is deterministic composition of **model observations**, not
proof of semantic truth. Do not turn a committed/hedged answer into a refusal.
Report `claims_scope_conflict` without overriding support. Contradiction caps an
otherwise supported row below supported. A missing normalized quote anchor fails
that output; preserve it, do not silently repair or retry. Anchoring is not entailment.

Clarify that observation and effective times differ: explicit bounds/textual time,
corrections and cancellations matter; newest observation does not automatically win.
No reference-answer phrase detector, automated packing attribution, benchmark
entities/numbers/expected labels in the prompt. Reference answers are judging-only.

## Fixed arms and limits

| Arm | Logical cases | Lifetime new-call cap |
| --- | ---: | ---: |
| Existing development controls | 6 | 6 |
| Preserved v1 answers | 18 | 18 |
| Citation-order stability | 6 | 6 |

Maximum new attempts **30**, no retries and no mid-run prompt or budget revision.
DeepSeek v4 flash, json_object, temperature 0, thinking disabled, 3072 max_tokens,
120-second timeout. Key from `DEEPSEEK_API_KEY` only. Requests deduplicate by content;
cache-only replay uses no key/network and preserves cumulative ledger accounting.

Controls file `benchmarks/datasets/judge-v2-controls-v1.json` unchanged. These controls
reuse opened question content; explicitly development regressions, **not** independent
transfer tests. The old gate remains: all six outputs valid and anchored, fewer
than two frozen-label mismatches. One mismatch is reported, not hidden. If gate
fails, stop paid execution here; do not keep revising to chase these six labels.

Rows require a complete matching controls report, recomputing labels/gate from raw
observations rather than trusting a `passed` boolean. Bind report hash to rows plan.
Original answer artifact `data/doppel/longmemeval-answer-comparison-v1.json`, comparison
`data/doppel/longmemeval-memory-comparison-v1.json`, original dataset and audit
decisions unchanged. Audit comparison is reporting-only and never enters requests.

Stability uses original row indices **1, 5, 6, 7, 9, 11**, reversing only the cited-id
array. Full context, reference, answer and all other input fields remain identical.
Bind complete rows report, preserve model outputs and report agreement per dimension.
No reference paraphrase, no expectation-conditioned sample replacement.

## Validation and stopping condition

Test blind payloads, old-artifact preservation, taxonomy/claims flags, anchor failure,
control-report tampering, case-payload fingerprinting, fixed caps, cache replay,
no retry and citation-order-only transformations. Fake tests validate harness rules,
not the live model. Run full suite/lint/types before committed live execution.

After execution, separately replay every completed arm in a key-free process. Compare
all model outputs, derived labels and metrics; zero new calls. Record usage, failures,
control mismatches, audit disagreement and citation-order instability. Do not force
13/18 or any preferred profile ranking. Preserve old and new scores with provenance.

Then stop and report. No Reader v2, data enlargement, AML profile or core fix this
turn. Whether gate passes or fails, six development controls cannot validate a judge
and three opened questions cannot establish benchmark performance.
