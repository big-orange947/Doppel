# Count evidence repair: retrieval improves, answer still fails

Development replay of the same opened third question, frozen in `8f1a4ef` before
five paid calls. Original failed receipt and data remain unchanged; this is not
an independent success, full LongMemEval score or AML result.

## Product behavior, not a score workaround

The unrelated January application no longer overlaps the March interval: episodes
without an explicit end are point occurrences, while ongoing states and explicit
durations keep their distinct semantics. Framework aggregation is now indeterminate,
with one structurally/relevance-qualified candidate and no exact numeric value.
A complete scan plus similarity is not treated as exact predicate membership.
The source record with missing event-time metadata remains unchanged.

Independent raw/backing evidence supplies both original March 5 and March 26
statements. Annotated turns and sessions improve from **1/2 to 2/2**. Fixed packing
contains 20 items / 14069 UTF-8 bytes, with actor/authority and provenance retained.
No graph top-k is used as cardinality; graph branches remain unexecuted on count.

Reader nevertheless calls the two dates an unresolved conflict, reports at least
one event, and fails the reference-only task judge again. Its own citations include
both required raw statements. The new failure is **Reader event-identity/conflict
reasoning**, not absence of the annotated evidence. Citation judge reports the
quoted event claims supported/no contradiction but separately says the conflict
framing is unnecessary and the final count wrong. Do not call the whole answer
faithful merely because individual quotations are anchored. Chinese language drift
also remains. More graph authoring cannot fix a Reader misreading evidence already
present in its context.

The old lexical quality dataset remains untouched and now honestly exposes one
count error under its prior exact-count expectation. Synthetic tests separately
verify complete structured-set cardinality, point/state/duration distinctions,
empty/nonempty unverified predicates, raw recovery when validity is missing,
source backing that does not change counts, and cross-scope rejection.

## Usage and reproducibility

| Stage | Requests | Reported tokens |
| --- | ---: | ---: |
| Planner | 2 | 23108 |
| Reader | 1 | 4386 |
| Reference-only judge | 1 | 571 |
| Citation judge | 1 | 6210 |
| Total | **5** | **34275** |

No failed requests, retries or missing usage; no new extraction, schema or graph
authoring. Store corpus, selected graph and all vector manifests remain unchanged.
Empty-key checkpoint/cache replay matches plan, retrieval, packing/context,
answer, grades, evidence and execution with three downstream cache hits and no
new requests. Original failure is retained, not overwritten or silently regraded.

Full regression: **1450 passed / 33 skipped / 3 subtests passed**, repository Ruff
check passes. `uv.lock` is still user-owned and unstaged. The first full run caught
the old benchmark's zero-count-error test assumption; the updated test expects
the real one-error report without editing the dataset/gold or hiding gate failure.

Next prioritize the host-controlled separation of question reference and knowledge
horizon, preserving strict defaults and old plan shapes. Reader changes, if tested,
need a new isolated protocol and unrelated event/duplicate/correction controls;
do not inject the failed question's answer into prompts or another judge.
