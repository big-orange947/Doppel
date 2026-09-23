# Candidate path generation V3 review: opened regression

Date: 2026-09-23

Status: review improved precision and one-hop direction; complete gate still failed

This run added one non-authoritative review pass to the cached V2 first-pass outputs
for the 12-case heldout/adversarial selection. The corpus and V2 observations were
already open. The result is architectural regression evidence, not an unseen quality
claim, and no graph query was executed.

## Reproducibility

- Implementation commit: `4e960cf`
- Generator: `doppel.reference-candidate-relation-path-generator-v3`
- Protocol: `v3_two_pass_review`
- Local result:
  `data/doppel/candidate-path-generation-v3-reviewed-heldout-adversarial.json`
- Result SHA-256:
  `998089c84ab69a3f478aa27f30829b5837b7b3e5c3527039f0f9c22f916d25bd`
- Cache hits/misses: 12 / 12. Every V2 first pass was reused; only the 12 review
  requests reached the provider.
- Usage for review calls: 26,642 input, 386 output, and 27,028 total tokens; 10,112
  input tokens were provider-reported cached input.
- Provider/validation errors: zero.

## Result

| Metric | V2 single pass | V3 reviewed | Gate | V3 pass |
| --- | ---: | ---: | ---: | :---: |
| Required-route recall | 0.667 (6/9) | 0.778 (7/9) | >= 0.80 | No |
| One-hop recall | 0.800 (4/5) | 1.000 (5/5) | >= 0.80 | Yes |
| Two-hop recall | 0.500 (2/4) | 0.500 (2/4) | >= 0.75 | No |
| No-path false-candidate rate | 0.250 (1/4) | 0.000 (0/4) | <= 0.25 | Yes |
| Extra routes per case | 0.333 (4/12) | 0.167 (2/12) | <= 0.50 | Yes |
| Extra types per generated route | 0.778 (7/9) | 0.375 (3/8) | <= 1.00 | Yes |
| Invalid compilations | 0 | 0 | 0 | Yes |
| Provider/validation errors | 0 | 0 | 0 | Yes |

The V3 complete gate failed required-route and two-hop recall. Required recall missed
the 0.80 threshold by one route, but the unchanged two-hop result is the decisive
failure.

## What review fixed

- The purchase-venue inverse query changed from an outbound binding to the correct
  `PURCHASED_AT/inbound` route.
- The unspecified relationship control changed from a low-confidence bundle of
  location/storage/custody candidates to an empty observation.
- One-hop recall became 5/5, no-path rejection became 4/4, and excess candidates fell
  without introducing any disconnected topology or provider error.

## What review did not fix

The borrower-to-item-to-owner and adoption-origin-to-pet-to-owner questions retained
their first-pass one-atom outputs unchanged. In both cases the missing second predicate
was explicitly present in the question, but the reviewer anchored on the fallible first
observation instead of reconstructing the complete predicate inventory. Additional
wording changes against these known examples would be prompt overfitting.

## Decision

Stop candidate-prompt iteration on this corpus. The next controlled comparison should
reuse Doppel's existing V7 relation-atom Planner as a path backbone, convert its trusted
host-compiled exact route into a retrieval-only candidate topology, and score it on the
same opened cases. This tests an existing architectural component rather than adding
case rules. If the Planner backbone cannot meet the two-hop gate, accept the current
Flash structured-planning ceiling and move the remaining recall burden to independent
pgvector/Graphiti semantic candidates in an end-to-end hybrid evaluation.
