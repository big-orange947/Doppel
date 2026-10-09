# Ambiguity metadata repair and next-history QA binding

The first three opened highest-config questions retain their old receipts and
scores. The supplied-history clock contrast is also preserved. This change has
no new paid answer score and must not be presented as a quality improvement.

## General product issue

`_detect_ambiguity` previously grouped all matching current/as-of assertions by
scope, subject, memory type and topic, including empty topic strings. Two different
facts with no topic identity were therefore reported as an unresolved conflict
in `<unkeyed>`. Lack of a predicate/slot key is not evidence of incompatibility.
Different wording in a named slot likewise does not establish contradiction.

The repair preserves every eligible hit. Topic-less groups warn that conflict
status is unassessed, without inventing a shared slot or setting `ambiguous` from
that alone. Multiple distinct statements in a named slot still flag ambiguous
evidence, with semantic compatibility explicitly unassessed. Independent open
governance conflict markers remain surfaced and make the query ambiguous. No
LLM-based semantic resolution, newest-wins choice or topic-specific rules added.

Independent synthetic current/as-of tests cover absent, same and different keys,
duplicate wording and retention of candidates; existing explicit governance
conflict/correction tests remain. The reporting contract deliberately continues
to mark both new warnings `review_required`: no warning whitelist was changed
to raise the pass rate. Old results are not retroactively repaired.

## Source-authorized expansion

The natural-query runner's new V3 identity admits a scope only when exactly one
target exists in a recognized frozen source graph envelope. The old 2/3 graph
batch remains 2/3-only; the additive next-history envelope must bind target =
predecessor +1. Unknown, duplicate, incomplete, arbitrary or mismatched targets
are rejected. Existing manifest/scope/projection/snapshot checks still apply.

This does not bypass graph readiness or query a selected partial graph. Fourth
history QA must wait for all 219 graph projections, a source-name-only schema
and a new committed preflight. Its source-order selection was frozen before
graph calls. Old V1/V2 query plans/caches cannot be reused under a changed source
hash: preserve them and create new protocol identities instead.

Validation: 1501 passed, 33 skipped, 3 subtests; one existing Graphiti deprecation
warning retained. Ruff checks and changed test/runner formatting pass. No new
paid answer evaluation was performed for this repair; fourth source authoring
uses the already frozen writer and is independent of the changed query code.
