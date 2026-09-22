# Relation-path Planner V7 Pro non-thinking opened V2 regression v1

Date: 2026-09-23. This is an opened-regression, single-variable model comparison.
It is not eligible as unseen evidence.

## Identity and budget

- Source commit: `a1a2ea837cbf37e04e9e4af9ab5f69cd00d98165`
- Planner: `doppel.reference-personal-memory-relation-path-planner-v7`
- Protocol: `v7_two_pass_atom_review_host_compilation`
- Provider model parameter: `deepseek-v4-pro`
- Thinking: disabled
- Provider calls: 96 / 96
- Doppel cache hits/misses: 0 / 96
- Input/output/total tokens: 349,894 / 24,787 / 374,681
- Complete valid cases: 48 / 48
- Provider/planner errors: 0 / 0
- Report SHA-256: `6d29beaaaba905300d25720055ec21b54884f9e06d90681e4627fd7a1305669d`

## Result versus Flash

| Metric | Flash non-thinking | Pro non-thinking | Delta |
|---|---:|---:|---:|
| Exact path | 0.875000 | 0.708333 | -0.166667 |
| Decision | 0.958333 | 0.770833 | -0.187500 |
| Reason | 0.958333 | 0.770833 | -0.187500 |
| Relation type | 0.833333 | 0.604167 | -0.229166 |
| Direction | 0.916667 | 0.666667 | -0.250000 |
| Path recall | 0.937500 | 0.750000 | -0.187500 |
| One-hop exact | 0.875000 | 0.875000 | 0 |
| Two-hop exact | 0.750000 | 0.437500 | -0.312500 |
| No-path accuracy | 1.000000 | 0.812500 | -0.187500 |
| Forbidden type hits | 2 | 3 | +1 |
| Wrong execute | 0 | 3 | +3 |

All configured gates failed except over-bound handling. The run was operationally
complete, so this is a model-behavior result rather than a provider, budget, cache, or
validation failure.

## Failure pattern

Pro recovered the Flash failure for the explicit blue storage-container query. It
regressed six previously exact answerable cases, mostly by emitting atom graphs that
did not use the fixed `anchor` and `answer` references and were therefore rejected by
trusted host compilation. These included a direct purchaser query and five two-hop
chains involving custody, employment, repair, loan, storage, or care.

More importantly, Pro executed three requests that should have been rejected:

- software developer was forced into `ISSUED_BY`;
- music composer was forced into `RECOMMENDED_BY`;
- an agent reminder to renew a licence was treated as an executed `RENEWED_ON` fact.

The second pass preserved these wrong outputs rather than repairing them. Pro
non-thinking therefore has weaker instruction following for this governed ontology and
reference protocol than the currently routed Flash model. A larger model name is not
evidence of better structured Planner behavior.

## Decision

Do not use Pro non-thinking for this Planner and do not change prompts against opened
V2. One final controlled comparison may enable Pro thinking mode while leaving the
dataset, schema, protocol, compiler, and gates unchanged. A larger output allowance is
required so reasoning does not crowd out the final JSON object.

If Pro thinking does not materially exceed Flash while preserving zero wrong execution
and zero forbidden types, stop model/prompt iteration. Move to a design that separates
exact hard paths from retrieval-only candidate paths and measures end-to-end evidence
recall with vector plus graph candidates.
