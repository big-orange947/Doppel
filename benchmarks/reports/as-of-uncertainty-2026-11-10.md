# As-of uncertainty repair, 2026-11-10

This fixes the runtime reporting gap found in the first live analyzer result. It
does not alter the analyzer prompt, infer dates, rewrite stored facts or provide a
new quality score. No LLM/embedding calls or Store writes were used for the live
record replay.

## Change

Authorized active undated claims remain candidates for point-in-time queries,
including historical/unknown claims previously dropped for missing validity.
`candidate_evidence.as_of_match` distinguishes known validity, timeless metadata,
uncertainty and queries without an as-of coordinate. Undated current claims no
longer get `valid_at_as_of`; uncertain membership cannot produce an exact count.

Known disjoint intervals, subject/scope/authority restrictions, observation cutoff,
planned≠actual and inactive-without-validity gates remain. Ordering weights and
current/prior/unbounded filters are unchanged. A one-sided known interval retains
the existing open-bound contract. Invalid supplied endpoints are uncertain, not
silently treated as proven open bounds.

## Read-only replay of real stored claims

Schema: `doppel_workflow_reference_v1`. Caller observation clock: 2026-11-03.
The query uses explicit structured planner fields and lexical Store retrieval;
this is not a natural-language planner or graph/vector benchmark.

| View | Before | After |
|---|---|---|
| current | Dark preference only | Same record, unchanged |
| prior | Light preference only | Same record, unchanged |
| as_of Nov 1 noon UTC | Dark only, no warning | Both records, both uncertain, warning |

Both original validity intervals remain null. No claim is rewritten to become
valid on November 1. The possible retroactive meaning of the correction remains
for the host/answer model to consider using evidence. This does not assert that
either preference is the unique correct answer at that date.

New local artifact: `data/doppel/reference-workflow-v1-query-diagnostic-v2.json`.
SHA-256: `2f84f514b5e453e9f5ea87b770edc55d4eed4c8e8b4f57c06e09d84e3ff163da`.
The original report, diagnostic, journal, Store rows and paid-call ledger are retained.

## Regression coverage and compatibility

23 focused cases cover V1/V2 planning, current/historical/unknown/custom labels,
known/open bounds, timeless facts, invalid dates, exact counts, semantic time hints,
old model inputs and unchanged scope/authority/lifecycle/observation guards.
The first full run had 2512 passed and one failure in the explicit public-model
field inventory. That inventory was updated only to append the reviewed defaulted
`as_of_match` field. Existing conflict-warning assertions now separately check the
new temporal warning without relaxing conflict expectations.

Final full regression, including the public field inventory and all 23 new cases:
2515 passed, 33 skipped, three subtests passed (267 seconds). Full-repository Ruff
and query-module Pyright pass. One existing Graphiti/Pydantic deprecation warning
remains. No paid calls, Store writes or data/index rebuilds were needed this round.

See [as-of API semantics](../../docs/as-of-uncertainty.md). Strict consumers must
accept the new field. Old report/cache contents must not be reinterpreted as if
they had performed these checks. This does not promise complete candidate coverage
from bounded indexes or change existing interval-occurrence uncertainty semantics.
