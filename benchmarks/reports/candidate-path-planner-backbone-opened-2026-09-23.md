# V7 Planner-backed candidate paths: opened comparison

Date: 2026-09-23

Status: failed; do not unify exact and candidate path protocols

This controlled comparison adapted Doppel's existing two-pass V7 exact-path Planner
into retrieval-only candidate topologies. It ran on the same 12 opened heldout and
adversarial cases as V2/V3. The host deterministically converted compiled directions
back into candidate atoms; no graph query or scope authority was granted.

## Reproducibility

- Implementation commit: `b1b4ff7`
- Protocol: `v7_planner_backbone`
- Local result:
  `data/doppel/candidate-path-planner-backbone-heldout-adversarial.json`
- Result SHA-256:
  `08ffe9e7c60fee2b807628fdf0557199ed5814d5fbad314cc0d89ee752f7ca8b`
- 24 provider calls, zero cache hits, zero provider/validation errors.
- Usage: 87,551 input, 4,486 output, and 92,037 total tokens; 55,296 input tokens
  were provider-reported cached input.

## Result

| Metric | V3 candidate review | V7 Planner backbone | Gate | Backbone pass |
| --- | ---: | ---: | ---: | :---: |
| Required-route recall | 0.778 (7/9) | 0.444 (4/9) | >= 0.80 | No |
| One-hop recall | 1.000 (5/5) | 0.400 (2/5) | >= 0.80 | No |
| Two-hop recall | 0.500 (2/4) | 0.500 (2/4) | >= 0.75 | No |
| No-path false-candidate rate | 0.000 | 0.000 | <= 0.25 | Yes |
| Extra routes per case | 0.167 | 0.000 | <= 0.50 | Yes |
| Extra types per generated route | 0.375 | 0.000 | <= 1.00 | Yes |
| Invalid compilations / errors | 0 / 0 | 0 / 0 | 0 / 0 | Yes |

The exact Planner returned only four routes. It retained two already-correct two-hop
chains plus direct purchaser and explicit purchase-versus-holder paths, but abstained
on the two missing implicit chains, the inverse purchase-venue query, and the general
location alternatives. Its precision was perfect only because it suppressed most
candidate discovery.

## Architectural conclusion

Exact hard-path planning and retrieval candidate generation have different operating
points and should not share one decision contract:

- The exact Planner should abstain unless it can establish one safe complete path.
- A candidate generator may expose bounded plausible routes, with scope/time/provenance
  and Store revalidation still enforced downstream.
- Independent vector and Graphiti semantic sources must remain available when either
  structured path component abstains or omits an implicit hop.

Do not promote the Planner-backed profile and do not spend more provider calls tuning
these opened questions. V3 is the best current candidate profile for precision/recall,
but it also failed its two-hop gate and remains experimental. The next benchmark should
measure V3-generated relation candidates as one additive source alongside lexical,
pgvector, and Graphiti semantic retrieval. The answer layer—not a relation label—must
judge whether the returned evidence supports a claim.
