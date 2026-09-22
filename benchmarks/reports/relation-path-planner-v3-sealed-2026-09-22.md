# Relation-path Planner v3 sealed evaluation

Date: 2026-09-22. This is the first and only opening of the draft v1
`heldout + adversarial` partitions for Planner v3. The prompt, schema, runner, and
quality thresholds were committed before provider execution. The result failed its
pre-registered gate and must not be rerun or described as held out after tuning.

## Identity

- Source commit: `eb2d206dc64e0343de7615b41b1f8d6922a2a522`
- Dataset: `doppel-relation-path-planner-zh-v1`, `1.0.0-draft.1`
- Dataset fingerprint: `2b0a4be8ccd3cf4b756f2d12898966c1085ea67b5e3ca3c76875b8a997724eb4`
- Selection: 12 heldout + 9 adversarial cases
- Selection fingerprint: `6d724376af8e5a8e34b8bba121fbc95aa7e03244fa411b06b3b4c995548d33a4`
- Planner: `doppel.reference-personal-memory-relation-path-planner-v3`
- Planner version: `3.87d56b20d5d08386`
- Provider: DeepSeek `deepseek-v4-flash`, provider version `1.9f0fdc839837f31b`
- Provider mode: `json_object`, thinking disabled, temperature 0, 1,024 output-token cap
- Report SHA-256: `ece7cd805540488cb7e07b194b19037776e7da75dfd81433b8674c722198d886`
- Runner SHA-256: `d569969745a26227bfa9e1e38122fa585b2456f231e02c5c0fcc2f643c61a5aa`
- Scorer SHA-256: `9518b5a66c0513e004101c1034eefd592d2caaaf32d75de34b160311c4fff55a`
- The only tracked dirty path reported during execution was the pre-existing `uv.lock`.

The draft dataset remains `frozen=false` and `publication_ready=false`. This report is
an immutable development result, not a publication-quality benchmark claim.

## Budget and completeness

- Selected cases: 21
- Provider calls: 21 / 21 maximum
- Cache hits/misses: 0 / 21
- Provider errors: 0
- Planner validation errors: 1
- Not-run cases: 0
- Input/output/total tokens: 80,055 / 3,124 / 83,179
- Budget respected: yes
- External graph execution: disabled

## Pre-registered gate

| Metric | Threshold | Result | Passed |
|---|---:|---:|---:|
| Exact path accuracy | >= 0.85 | 0.952381 | yes |
| Path recall | >= 0.85 | 1.000000 | yes |
| Relation-type accuracy | >= 0.90 | 1.000000 | yes |
| Direction accuracy | >= 0.90 | 1.000000 | yes |
| No-path accuracy | 1.00 | 0.833333 | **no** |
| False paths | 0 | 0 | yes |
| Forbidden relation-type hits | 0 | 0 | yes |
| Complete valid evaluation | required | 1 validation error | **no** |

**Overall gate: failed.** The failure reasons recorded by the runner were
`provider evaluation was incomplete` and `no_path_accuracy below threshold`.
The thresholds and failure interpretation are not changed after observing the result.

## Partition and category results

| Slice | Cases | Exact path | Path recall | Type | Direction | No-path | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| Heldout | 12 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 0 |
| Adversarial | 9 | 0.888889 | 1.000000 | 1.000000 | 1.000000 | 0.666667 | 1 |
| One hop | 8 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 0 |
| Two hop | 7 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 0 |
| No path | 6 | 0.833333 | 1.000000 | 1.000000 | 1.000000 | 0.833333 | 1 |

All 15 answerable one/two-hop questions selected the exact expected relation types and
directions. All 11 nearby-relation cases, all three inbound traversals, and both
ambiguous-relation cases had zero forbidden selections. No valid draft produced a
false executable path.

Entity-mention exactness was 0.761905 and remains diagnostic, not a gate. Several
failures are equivalent surface references such as a demonstrative noun phrase versus
its head noun; the draft gold does not yet model accepted reference alternatives.

## Sole failed case

The adversarial `over_bound` case explicitly requests a three-relation traversal. Its
gold outcome is no executable path because V3 permits at most two hops. The provider
instead returned the semantically correct three steps with positive path confidence:

```text
HELD_BY/outbound -> EMPLOYED_BY/outbound -> LOCATED_AT/outbound
```

`PersonalMemoryRelationPathDraftV3` rejected this because `path_steps.maxItems=2`.
The scorer therefore recorded `ValidationError`, not a correct no-path decision.
This is simultaneously:

- a successful host safety boundary: no over-bound graph query became executable;
- a Planner reliability failure: the model did not express the required abstention;
- not a provider, Graphiti, relation-type, direction, scope, or provenance failure.

It would be post-hoc score manipulation to count the validation error as a correct
abstention in this sealed report. A future protocol may represent `over_bound` as an
explicit structured no-path/fallback outcome and evaluate it on a new dataset version.

## Decision

Planner v3 does **not** receive default query-engine execution authority because the
pre-registered sealed gate failed. The current result does support further opt-in
development: its valid one/two-hop generalization is strong, and every unsafe
over-bound output was blocked locally. The next protocol version should focus on an
explicit bounded-path decision/fallback outcome, retain host validation, and use a new
dev/sealed corpus. This sealed-v1 partition must not be reused as unseen evidence.
