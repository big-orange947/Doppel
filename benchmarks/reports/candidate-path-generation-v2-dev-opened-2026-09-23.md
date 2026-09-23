# Candidate path generation V2: opened dev regression

Date: 2026-09-23

Status: dev profile clean; not a sealed or complete-gate result

This run evaluated the generic minimal/connected-path protocol revision on the six
already-opened dev cases. It is useful regression evidence only: all cases and their
prior V1 behavior were known before V2 was evaluated. It did not query Neo4j.

## Reproducibility

- Implementation commit used by the provider run: `cf88c13`
- Dataset SHA-256:
  `6e961c9bc6ee2b4e96baf31a0814bfd9b9cbd8975a58db2aeb6b6e1f20f3058f`
- Provider result: `data/doppel/candidate-path-generation-v2-dev.json`
- Provider-result SHA-256:
  `8d01f059f2ea5b6ff6b6699e667ad770c722c74af9810a0b8640afa6c2612a7e`
- Cache-only re-score: `data/doppel/candidate-path-generation-v2-dev-rescored.json`
- Re-score SHA-256:
  `64c3464636c59ca42fd7149377387d73caa3fe1151a8337164af9e3902f3b6a3`
- Six provider calls, zero cache hits during the provider run, zero errors.
- Usage: 11,611 input tokens, 228 output tokens, 11,839 total tokens; 3,200 input
  tokens were provider-reported cached input.

## Result

| Dev metric | V1 first run | V2 opened regression |
| --- | ---: | ---: |
| Required-route recall | 1.000 (6/6) | 1.000 (6/6) |
| Generated routes | 12 | 6 |
| Extra routes | 6 | 0 |
| Extra relation types | 7 | 0 |
| Invalid compilations | 0 | 0 |

Every V2 case produced exactly one connected one-hop topology containing exactly the
required relation type. In particular, the earlier over-expansion from care to
holding/ownership/location and from temporary custody to loan/storage disappeared.
The provider output contained no benchmark entity mapping; the change came from the
generic requirement to produce the smallest question-justified connected path.

The original runner printed `quality_gate.passed=true` for this subset because empty
two-hop and no-path categories used neutral metric values. A subsequent cache-only
re-score corrected the reporting contract: a selection without one-hop, two-hop, and
no-path coverage is marked `coverage_matrix_complete=false`. The six measured dev
metrics above are unchanged. This report does not claim that V2 passed the complete
quality gate.

## Next test

Run the opened heldout and adversarial partitions together. That 12-case selection
contains one-hop, two-hop, and no-path controls, so it can exercise the complete gate.
If the generic protocol improves direction and chain completeness without reintroducing
noise, create a new unseen frozen corpus before making any product-default decision or
starting the live Neo4j model-generated-path ablation.
