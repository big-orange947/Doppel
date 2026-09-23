# Candidate path generation V2: opened heldout/adversarial regression

Date: 2026-09-23

Status: complete development gate failed on recall; width and validity improved

This 12-case opened regression evaluated the generic V2 minimal/connected-path prompt
on heldout and adversarial partitions from the already-opened V1 corpus. The selection
contains one-hop, two-hop, and no-path controls, so every development-gate category was
applicable. It is not unseen evidence and did not execute Neo4j.

## Reproducibility

- Implementation commit: `9d3ecb5`
- Local result: `data/doppel/candidate-path-generation-v2-heldout-adversarial.json`
- Result SHA-256:
  `7667e1603c395d60ea5a77c0583b8d32942a72e97e2cd2820f2fd4f6433b4533`
- Dataset SHA-256:
  `6e961c9bc6ee2b4e96baf31a0814bfd9b9cbd8975a58db2aeb6b6e1f20f3058f`
- 12 provider calls, zero cache hits, zero errors.
- Usage: 23,204 input, 426 output, and 23,630 total tokens; 7,680 input tokens
  were provider-reported cached input.

## Result

| Metric | V1 same 12 cases | V2 | Gate | V2 pass |
| --- | ---: | ---: | ---: | :---: |
| Required-route recall | 0.556 (5/9) | 0.667 (6/9) | >= 0.80 | No |
| One-hop recall | 0.600 (3/5) | 0.800 (4/5) | >= 0.80 | Yes |
| Two-hop recall | 0.500 (2/4) | 0.500 (2/4) | >= 0.75 | No |
| No-path false-candidate rate | 0.000 (0/4) | 0.250 (1/4) | <= 0.25 | Yes |
| Extra routes per case | 1.333 (16/12) | 0.333 (4/12) | <= 0.50 | Yes |
| Extra types per generated route | 0.952 (20/21) | 0.778 (7/9) | <= 1.00 | Yes |
| Invalid compilations | 3 | 0 | 0 | Yes |
| Provider/validation errors | 0 | 0 | 0 | Yes |

The complete gate failed only required-route and two-hop recall. V2 substantially
reduced width and eliminated structurally invalid output, but did not solve implicit
predicate inventory or endpoint-role reasoning.

## Failure anatomy

- The borrower-anchored ownership question collapsed the required loan-plus-ownership
  traversal into one `LOANED_TO` atom and bound the anchor as the source.
- The adoption-origin-to-owner question emitted only `ADOPTED_FROM`, omitting the
  ownership hop.
- A purchase-venue inverse query selected the right type but bound the venue anchor as
  the source, reversing traversal.
- An unspecified relationship control emitted a low-confidence bundle of location,
  storage, and custody types. This is the only no-path false candidate.

V2 correctly repaired the former disconnected-topology cases, the ambiguous general
location case (both required alternatives were covered by one atom), and the explicit
purchase-versus-holder contrast. All direct precise one-hop cases remained minimal.

## Decision

Do not tune more one-pass examples against this opened corpus. The remaining failures
match the established V6 relation-atom bottleneck: a single model pass omits implicit
predicates or binds the anchor to the wrong definition endpoint. Doppel's existing V7
experiment showed that a second non-authoritative review pass improved two-hop exactness
from 0.5625 to 0.75 on a larger opened corpus. The next candidate experiment should use
the same architectural move: review one V2 observation against the original question
and definitions, then run unchanged host validation and compilation. It must not gain
scope, graph execution, memory IDs, or answer authority.
