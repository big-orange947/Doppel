# V10 atomicity controls: revision improvement, episode enrichment still fails

Implementation frozen at `e45b202`, starting HEAD `f9d7ee0`.
[Preregistered plan](analyzer-atomicity-controls-plan-2026-10-13.md).
**16 analyzer calls, zero failures/retries, no Reader/Judge or Store/index writes.**
Codex non-independent frozen-rubric passes: **V9 6/8, V10 7/8** on the new controls.
This is not the earlier V8/V9 fixture: its V9 **7/8 failed gate remains unchanged**.
Neither old nor new gate authorizes default promotion or an old task-cohort rerun.

## What changed and what did not

The [prospective property-atomic contract](../../docs/memory-atomicity.md) separates
independently updatable properties, merges equivalent property assertions and permits
enrichment only for a supported same-occurrence episode. Negation or disagreement
with an agent does not itself establish a withdrawal of the subject's prior claim.
V10 adds these generic instructions, sharing the existing schema/parser/diagnostics/
source-authority gates. V8 stays the default, and V8/V9 instruction bytes remain
unchanged. V10 is opt-in, not a release version or a hard semantic validator.

The paired inputs/schema/provider settings are identical. Alternating profile order,
fresh durable ledger/cache/receipts, no task question/gold/rubric/profile in the model
input. No original omission case or old task cohort, retrieval, embedding, reranker,
graph, GPU, Docker, persistent governance or hosting work. No old result/cache rewrite.

## New frozen rubric outcomes

| Control | V9 | V10 | Actual result |
| --- | --- | --- | --- |
| Independent bicycle color/tyre properties | pass | pass | Two assertions, distinct property slots and own sources |
| Duplicate dishwasher brand | pass | pass | One assertion with both source IDs |
| Unmarked different commute modes | pass | pass | Two assertions in same slot, no invented correction/newest-wins |
| Standalone negative library-card statement | pass | pass | Assertion with sole source, no invented prior claim |
| Explicit laptop-age correction | pass | pass | Old assertion intact, new correction has its own evidence only |
| Agent purchase claim denied by owner | fail | pass | Same owner fact/source; V9 marks retraction, V10 assertion |
| Same picnic, additional participant detail | fail | fail | Two episode drafts, not one fully enriched occurrence |
| Two distinct gallery visits | pass | pass | Separate historical episodes, dates and event keys |

The improvement is **one revision-kind correction**, not broader fact recall, a
retrieval gain, independent accuracy or a claim the previous missing assertion is
fixed. V9 correctly handles the standalone negative control but not agent-context
denial; this does not establish that all ordinary negatives fail in V9 or pass in V10.

In control 06, both outputs say “The owner has never bought a telescope.” Both bind
only owner message `a06-y`, with `human_self` authority. V9 metadata has
`revision_kind=retraction`; V10 has `assertion`. The supplied prior positive statement
is from the agent, not an earlier owner claim. V10 removes that unsupported owner
revision without weakening actor/source gates or converting the agent assertion into
an owner fact. No actual consolidation/state transition is applied.

### Remaining episode failure is not demonstrated information loss

Both arms output these two separate claims for control 07:

- “On February 1, 2026, the owner had a picnic at the riverbank.”
- “Nia joined the owner at the February 1, 2026 riverbank picnic.”

Both use `event_key=riverbank-picnic-2026-02-01`. V9 binds source `a07-x` to the first
and `a07-y` to the second. V10 binds both sources to the first but still omits Nia
from that claim, and retains the separate Nia claim with `a07-y`. Adding citations
is not equivalent to incorporating their details. Location/participant remain
available, but the frozen requirement of one fully enriched episode is not met.
Same event key alone does not prove occurrence identity, and two drafts do not by
themselves prove a double count in an event-key-aware consumer. Neither is measured
here. Do not force a prompt retry or rewrite this expectation to make 8/8.

### Caveats outside the narrow controls

- Both telescope denials have `temporal_status=timeless`. “Never bought” describes
  history available at observation, not a promise about all future time. The narrow
  revision/authority pass does not validate this temporal interpretation.
- Bicycle property types differ (`fact` in V9, `state` in V10), while laptop age
  differs the other way (`state` in V9, `fact` in V10). Type consistency/lifecycle
  implications are not independently validated by content/slot rubrics.
- Episode date content is retained. V9 supplies midnight UTC for the picnic but
  no effective bounds for gallery visits; V10 does the reverse. Sources provide
  calendar dates, no timezone/hour. Sparse bounds and timestamp precision remain
  open; this is not a successful exact as-of/timezone test.
- Prompt changes have no explicit revision-target relation or semantic verifier.
  Correct markers in these cases cannot authorize unattended persistent correction.

All 26 proposals are schema-valid (13 per arm), zero low-confidence/duplicate/
quarantined drafts. Output authority is owner/human_self with owner-only sources.
No rejected live unsafe candidate means this run does not itself exercise quarantine;
existing offline tests continue to exercise that shared boundary.

## Calls, tokens and empty-key replay

| Profile | Calls | Input tokens | Output tokens | Total |
| --- | ---: | ---: | ---: | ---: |
| V9 | 8 | 10,168 | 1,262 | 11,430 |
| V10 | 8 | 12,176 | 1,281 | 13,457 |
| Total | 16 | 22,344 | 2,543 | 24,887 |

Usage is bound to exact plan request SHA through the read-only ledger query, all
16 calls have complete usage, zero missing usage/retries/failures. V10 adds 19.75%
input tokens and 17.73% total tokens on these small controls; output length varies.
Provider reports 17,280 cached input and 5,064 cache-miss input tokens, reasoning 0.
Requested alias `deepseek-v4-flash`; all actual receipts report `deepseek-flash`,
finish `stop`. No pinned-snapshot claim.

Observed balance CNY 4.66 before/after, not exclusive billing attribution or a claim
of free calls. No exact token-price/invoice cap. Cache-only replay in a separate
PowerShell process removes the key, makes **zero new calls**, gets 16 hits/0 misses,
and reproduces all rows/proposals/checkpoints and the frozen plan exactly. Ledger
still contains historical 16 calls; those are not 16 new replay calls.

## Evidence bindings and validation

Local ignored artifacts retain source/proposal/manual-review provenance. Sixteen
manual decisions have 26 exact output anchors, 15 unique source quote anchors, 29
source bindings and 104 authority/subject/revision/source-list checks against actual
outputs. These checks validate anchoring, not the semantic judgments independently.

- Preflight SHA `93fa0b8d7c7b98dffd896468038f2433487b30c77bd200e426b98c5b03ad092f`.
- Plan fingerprint `80b8dc101fae9cf058271c366352ee10fee8fb87fbdfc3000da781940d03ec7f`.
- Live `data/doppel/analyzer-atomicity-live-v1.json` SHA
  `3932b5c5b052f675321c2693d3fe478f1581cad1acb7c1e912a486dbb456a415`.
- Key-removed replay SHA
  `987f59881742e907f6821b58c4c056dd986347fdd90bd0920346806720171437`.
- Manual review file SHA
  `c39b063ebc94469cc3cabc8408557ac6d7c2909fb7a354f9e8a0eb773c317179`.
- Canonical review fingerprint
  `c18971da3596fe8c6cc9a4bc246a7ed292540f73a0c657ee98fa9bfd7707a309`.

Focused tests **15 passed**, five new tests; full regression **1772 passed, 33 skipped,
3 subtests passed** in 203.66s. Ruff full repository passes; selected intelligence
and both control runners Pyright reports zero errors. Existing Graphiti/Pydantic
deprecation warning remains. `uv.lock` is an untouched pre-existing user change.

## Next decision, not another prompt loop

Keep V10 opt-in and both failed gates visible. Before more paid task runs, perform
a zero-model event-level audit: inspect whether existing event-key grouping and
advisory consolidation preserve all detail/source claims or choose a canonical
sentence that loses details, and whether counts use occurrence identity rather
than proposal count. Any subsequent read-only grouping must retain per-detail
provenance and mark model-inferred identity as advisory, not prove it by key equality.
Separately address source-qualified effective time and revision-target semantics.
No V11 prompt retry, default switch or old-cohort follow-up is authorized by this run.
