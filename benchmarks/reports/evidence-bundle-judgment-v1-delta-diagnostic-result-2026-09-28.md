# Evidence-bundle judgment V1 — first opened delta diagnostic result

The result was opened after commit `e4356d4b9f4cc06a00f5a6475fc455efdf8e4c14`
froze the 16-case selection, information boundary, cache/budget behavior, scoring, and
V7/V8 comparison. The selection is explicitly post-hoc and publication-ineligible.

The ignored raw result is
`data/doppel/evidence-bundle-judgment-v1-delta-diagnostic-first-live.json`.
Its canonical report SHA-256 is
`f5553358e43b83f39b390e66e64e194da686431cdfe4d1ab2f3a8db38f657b59`;
its file SHA-256 is
`bbf2ae92e3feef18f35bb91d309bc86f57f66ec3ef4bb3a31ae3607af78d84ce`.
The canonical hash verifies.

## Runtime

- 16 cases across eight owner scopes and three frozen strata;
- 32 logical profile judgments;
- 24 provider calls and 8 content-addressed cache hits;
- 22,205 input, 405 output, and 22,610 total provider-reported tokens;
- zero provider, validation, unknown-item, or budget errors;
- `deepseek-v4-flash`, `json_object`, temperature zero, thinking disabled;
- Store IDs, gold labels, scopes, retrieval attribution, and graph scores were not
  exposed to the model.

## Aggregate result

| profile | retrieval sufficient | judgment accuracy | exact support | end-to-end support | no-answer abstention |
| --- | ---: | ---: | ---: | ---: | ---: |
| V7 rank-first | 0.375 (3/8) | 1.000 | 1.000 on sufficient bundles | 0.375 (3/8) | 1.000 (8/8) |
| V8 evidence-rich | **1.000 (8/8)** | 1.000 | 1.000 on sufficient bundles | **1.000 (8/8)** | 1.000 (8/8) |

The evidence-rich-minus-rank-first delta is +0.625 for retrieval sufficiency and
+0.625 for end-to-end support success. Judgment accuracy, exact support selection, and
no-answer abstention do not regress. No related or hard-forbidden item was selected as
support under either profile. The frozen comparison passes and
`policy_preference_supported` is true.

## Frozen-stratum result

| stratum | V7 | V8 | interpretation |
| --- | ---: | ---: | --- |
| five recovered complete paths | 0/5 end-to-end | **5/5** | V8's second hop is usable, not metric-only context |
| three one-hop rank shifts | 3/3 | 3/3 | rank 2 to rank 3 caused no observed judgment loss |
| eight relation no-answer controls | 8/8 abstain | 8/8 abstain | richer graph context caused no false purchase support |

On every V7-incomplete two-hop bundle the model correctly abstained rather than
guessing. On the corresponding V8 bundle it selected the exact two-memory support set.
This validates the evaluator's separation between retrieval failure and downstream
reasoning: the same model behaves differently only when the missing evidence enters
the bounded bundle.

## Decision and limitation

Promote V8 as the preferred **opt-in experimental** high-configuration policy. Keep V7
as the rank-first control and V9 as a negative control. Do not silently change the
stable query engine yet.

This is strong causal diagnostic evidence but not a generalization claim: the five
positive cases were selected because the opened retrieval report already showed V7/V8
membership differences. The next quality claim still requires a new owner-disjoint
blind corpus frozen before either policy runs. Product integration should preserve the
named policy boundary so the blind evaluation can compare or roll back it without
rewriting the stable query API.
