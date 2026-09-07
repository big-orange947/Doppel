# Query intent and temporal semantics v12

Date: 2026-09-07. This is a protocol and benchmark-gold correction, not a
retrieval-score claim.

## Mutable state versus enduring facts

The v11 correction was directionally right but its first post-run interpretation
overgeneralized `lookup`: absence of an explicit word such as “now” does not make
every question timeless. A passport location, item custodian, active loan, current
employer, or ongoing care relationship can change. The unqualified question normally
asks for the state valid now, so it needs `current` and the corresponding temporal
gate. Using `lookup` would admit obsolete locations or custodians.

`lookup` is reserved for enduring attribution, provenance, identity, or comparable
facts: who recommended or purchased an item, where it was purchased, which authority
issued a document, birthplace, or adoption origin. Grammatical past tense and the fact
that an establishing action completed do not alone make these queries `history`.

`history` remains for superseded/ended states, explicitly historical occurrences, and
past intervals. This distinction is conceptual and applies across domains; neither
the runtime nor the benchmark contains query-ID branches or phrase-to-answer rules.

## Points and intervals

An exact day is eligible for `as_of`. A calendar month/year without a day is an
interval and must use `time_from`/`time_to`; it cannot be replaced by an arbitrary
midpoint or month-end instant. “Before”, “after”, and “during” retain their range
shape. The “after August 10” query records both inclusive-day and next-day lower-bound
interpretations, while still rejecting a single invented point.

Dataset v1.4 applies these rules across all 65 relation queries. Scoring v3 measures
point presence/date and interval presence/boundaries separately. The dataset remains
draft and post-hoc; a fresh held-out set is still required for publication claims.

## Untrusted provider output

Providers implementing only JSON-object mode may add fields outside the requested
schema. Reference Planner v12 projects only declared draft fields before validation;
unknown fields are inert and logged only by count. Scope, memory IDs, Store actions,
and authorization never become model-controlled. An output containing no recognized
field is rejected, and invalid recognized values—such as `as_of` without a timestamp—
still fail strict validation.
