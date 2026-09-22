# Relation-path Planner V7 opened V2 regression v1

Date: 2026-09-23. V2 was opened by the earlier V5 sealed run. This V7 result is
regression evidence only and is not eligible as unseen evidence.

## Identity and budget

- Source commit: `86be56e3a46939e44f3b6c52e065fc1d8e803fa2`
- Planner: `doppel.reference-personal-memory-relation-path-planner-v7`
- Protocol: `v7_two_pass_atom_review_host_compilation`
- Provider model parameter: `deepseek-v4-flash`, non-thinking. DeepSeek currently
  routes that legacy identifier to its V4.1 Flash service.
- Provider calls: 96 / 96 (two per case)
- Doppel cache hits/misses: 0 / 96
- Input/output/total tokens: 350,012 / 19,211 / 369,223
- Complete valid cases: 48 / 48
- Provider/planner errors: 0 / 0
- Report SHA-256: `51819613f5b3b68c8842ce4abe6a91d8f59bab0eda72c2f869ce532a62e5a391`

## Result versus V6

| Metric | V6 | V7 | Delta |
|---|---:|---:|---:|
| Exact path | 0.833333 | 0.875000 | +0.041667 |
| Decision | 0.854167 | 0.958333 | +0.104166 |
| Reason | 0.854167 | 0.958333 | +0.104166 |
| Relation type | 0.687500 | 0.833333 | +0.145833 |
| Direction | 0.708333 | 0.916667 | +0.208334 |
| Path recall | 0.781250 | 0.937500 | +0.156250 |
| Two-hop exact | 0.562500 | 0.750000 | +0.187500 |
| No-path accuracy | 1.000000 | 1.000000 | 0 |
| Forbidden type hits | 0 | 2 | +2 |

The registered opened-regression gate failed only because exact-path accuracy was below
0.90. That compact statement is not sufficient for promotion: two forbidden nearby
types and four inexact executed paths remain material retrieval-quality failures.

## What the review pass fixed

V7 recovered three V6 failures without query-specific rules:

- the item borrowed by Han Mei, followed by its owner;
- the item held by reception, followed by its storage cabinet;
- another item sharing the camping stove's storage container.

The review pass materially improved answerable-path recall, relation direction, and
execute/abstain decisions while preserving all 16 no-path controls and producing no
provider or validation errors.

## Remaining failures

Six of 48 paths were not exact:

- `v2-h08`: selected `STORED_IN` instead of `LOCATED_AT` for a general location query;
- `v2-h16`: classified an explicit container relation as `nonrelation`, regressing a
  V6 success;
- `v2-t08`: selected repair venue `REPAIRED_AT` instead of repair actor
  `REPAIRED_BY`;
- `v2-t09`: selected `STORED_IN` instead of `LOCATED_AT` for the second hop;
- `v2-t10`: emitted exact atoms whose references did not connect the fixed anchor to
  the answer, so trusted host compilation safely abstained as ambiguous;
- `v2-t16`: emitted only the custody hop and omitted the location-to-person hop.

Two cases were wrong abstentions. Four cases executed a non-gold or incomplete hard
path. The report's `wrong_execute_count=0` has a narrower meaning: no case whose gold
decision was abstention was executed. It does **not** mean that every executed path was
semantically exact. For this run, the inexact-executed-path count is four, including
two explicit forbidden-type hits.

## Decision

V7 is a real improvement but remains experimental and receives no query-engine
execution authority. Do not tune another prompt against opened V2. The next controlled
experiment should keep the dataset, schema, two-pass protocol, host compiler, and gates
unchanged while replacing only the Planner model with a stronger model. That separates
the architectural ceiling from the current Flash model's type-selection ceiling.

If a stronger model still misses the gate or retains forbidden types, the next design
should distinguish exact hard paths from retrieval-only candidate paths and evaluate
the latter end to end with vector plus graph evidence recall. It should not add
query-specific host heuristics or silently treat neighboring relation types as exact.
