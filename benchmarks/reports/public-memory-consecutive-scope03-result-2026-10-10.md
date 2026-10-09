# Third natural high-config diagnostic: count failure retained

Fixed ingestion ordinal 3 of the opened 50-case development cohort, not a new
independent sample, complete LongMemEval score or AML result. The repaired
observation clock and exact query protocol were frozen in `d47d874`; no algorithm
was tuned between the first-two repaired regressions and this third question.

## Result and attribution

Case `21d02d0d` asks how many March fun runs were missed because of work.
Reference: 2. Reader answers 1, citing March 5; reference-only judge marks it
incorrect. The cited claim is supported, with no contradiction and anchored
quotes. Evidence turn/session coverage is **1/2**, not full recall. Correct
citation support does not make an incomplete answer correct.

Framework `count.status=exact`, `value=2` counts `5k-fun-run.2023-03-05` and
**`ubc-application-submission`**. The number matches gold only by coincidence.
Do not count this as engine success or make Reader blindly echo it. Context
contains one relevant event and an unrelated university application.

Three general causes, verified against authoritative Store without modifying it:

1. **Validity gap, not absent event.** `mem-e4b1229985a245debfaedee4d84ecde0`
   records the March 26 missed run and correct event key but `valid_from=null`.
   The March interval uses its April observation time as fallback and excludes it.
2. **Point episode treated as ongoing.** UBC's explicit January 10 `valid_from`
   with absent `valid_to` becomes an open interval overlapping March. Weak lexical
   similarity also passes; neither qualifies it for the requested event set.
3. **Count evidence-channel gap.** High-config returns immediately for count,
   skipping raw/backing channels and graph paths. Raw March 26 message
   `mem-fc43dc4518fb4f43a41a3354eed753a8` explicitly mentions busy work and missing
   that event; March 5 source `mem-f78e2b70f17d40e88ee631d4e5eadd6b` states the
   work commitment. Both exist before the query clock but cannot reach Reader.

All three old vector/reranked baseline answers were reference-correct here.
These are different earlier protocols, not causal graph ablations, but show
that the needed source evidence was previously discoverable.

## Execution, graph, usage

Execution v2 says completed within contract/exhaustive scope read, with no backend,
source, scope or provenance failures. This contract does **not** certify semantic
count qualification. Count executes zero graph/reranker branches. No graph uplift
or multihop success is claimed. English question still receives Chinese output.

Graph: 222/222 projections, 150 rich / 72 fallback-only, 237 distinct rich edges /
238 per-projection links, 149 types. One missing-target PREFERS diagnostic remains
an extraction-loss observation. Ready graph histories are **3/50**, 615 memories.
First-two repaired answers are correct and this one fails: **2/3 is anecdotal
development evidence**, not a published accuracy. All other graph scopes, Store
and 34760 active vectors remain unchanged.

| Stage | Requests | Tokens |
| --- | ---: | ---: |
| Graph projection | 918 | 3838977 |
| Name-only schema | 7 | 13728 |
| Natural planner | 2 | 23148 |
| Reader | 1 | 1463 |
| Reference-only judge | 1 | 407 |
| Citation judge | 1 | 1341 |
| Total | **930** | **3879064** |

Zero failures/retries/missing usage. Empty-key checkpoint/cache replay matches
plan, retrieval, packing, context, answers, grades, checks, evidence and execution:
three downstream cache hits, no new reservations; not another fresh GPU sample.

Receipts under ignored `data/doppel/` (SHA-256):

- graph-scope03-live-v1: `6d06c111431c0e400ce85376723fc66c00a3f211faf6a7e0ed94555bcafb4efc`;
- schema-03-live-v1: `34e78d94d3d74e5dbeec0f6d116273619d42604f19fe2ea97c206d28d71c74b0`;
- query-03-observation-live-v1: `4608e4dd9c560a39e884437ff42f4e56bf50ae162d163736c233ec666655e4b1`;
- query-03-observation-replay-v1: `230e3f02d676f752efc8bf2b56d28e4fb1690130273837e6c865112d050c3695`.

## Next, before buying more graph coverage

Fix generic episode interval semantics. Separate exact structured-set cardinality
from an unverified free-text predicate; full scan plus similarity is not proof.
Preserve conservative aggregation, but supply raw/backing evidence without
pretending its bounded top-k is exhaustive. Use independent synthetic tests,
then freeze a new regression for this opened failure. Never fill its metadata or
parse benchmark keys to force a pass. Temporal extraction gaps stay visible.
Independent query/observation clocks remain a subsequent protocol task. No old
receipt/denominator is changed; reserved histories, all-500 rollout, latency and
publication claims remain excluded.
