# Second consecutive history: correct answer, retained temporal-source defect

## Outcome

The fixed second ingestion history completed real graph projection and all five
natural-query/answer/judge stages. Case `3ba21379` asks what vehicle model the owner
is currently working on. Reader identifies the **Ford F-150 pickup truck**, explains
the earlier Mustang project, and qualifies that the latest supplied update is May
26 against the June 1 question reference time. Task judge reports correct; four
citations are legal, source-supported and quote-anchored, with no contradiction.

This is one already-opened diagnostic question, not a blind score or AML result.
Across the first two highest-configuration runs, both answers are reference-correct;
that is **2 opened questions**, not evidence of a general 100% accuracy rate.

| Measurement | Scope 2 result |
| --- | --- |
| Annotated evidence | 2/2 turns and 2/2 sessions retrieved |
| Final context | 20 whole items / 22783 canonical UTF-8 bytes |
| Channels | 8 owner memories + 12 original messages |
| Citations | 4/4 legal, no duplicates; 4 quote observations anchored |
| Local reranking | CUDA:0, 3 batches / 136 pairs, no token truncation |
| Natural graph route | 1 executed route; 1 promoted one-hop `WORKS_ON` path |
| Memory/path rerank status | Both completed |
| Execution V2 | **Degraded: 2 original-source eligibility failures** |
| Store/vector/queried graph snapshots | Unchanged before/after QA and replay |

Reader again answers the English question in Chinese. This remains a language-
following limitation, even though the answer content is correct.

## Actual graph contribution, without an uplift claim

Planner's natural predicate reaches an owner-to-vehicle `WORKS_ON` edge, valid from
May 26, with Episode provenance back to `mem-29332af4b2464baf81854117cc4c64ff`.
The real path scorer runs; evidence-rich assembly and Reader consume that memory.
It is the first packed memory, alongside the original owner statement:

> I have just wrapped up a model and switched to a Ford F-150 pickup truck.

However this memory was **already base rank 1** and independently supported by
lexical/semantic candidates. The graph corroborates and participates in the actual
pipeline; it does not demonstrate additional discovery or a counterfactual gain.
This is one-hop evidence, not proof of multi-hop reasoning quality.

Old same-question baselines: raw-vector-reranked correct; memory-vector-reranked
incorrect; combined-vector-reranked correct. The new result remains comparable
only as an opened diagnostic with a different composition/packing protocol. Do
not attribute the difference from the owner-memory baseline solely to the graph.
All old answers and the previous 50-question aggregate scores remain unchanged.

## Most important finding: observation-time qualification is inconsistent

The new reporting contract intentionally keeps execution health separate from
answer correctness. It detects `source_backing_incomplete` / two source failures.
Read-only source-journal/Store inspection identifies the exact cause:

| Assembled derived record | Observed time | Host query knowledge time | Raw source |
| --- | --- | --- | --- |
| `mem-8a3882ef87fd4708b9fe6ae68b85532e` | June 1, 17:50 UTC | June 1, 05:09 UTC | Owner's sculpting-class statement |
| `mem-be59e5e6d53843e086b4dcbdd114af90` | June 1, 06:06 UTC | June 1, 05:09 UTC | Owner's gardening statement |

These are not missing events, cross-owner sources, authority mismatches or later
confirmations attached to an older record: each derived record's `created_at` and
single evidence observation are themselves **after** the frozen query `now`.
The raw backing gate correctly rejects them; the ordinary derived-memory gate
still admits them when no explicit future validity bound exists. Two ineligible
future observations therefore reach the assembled candidate set.

Neither record was packed into the final 20 items or cited. The actual answer and
its four citations are not based on those future observations. This lack of final
exposure is an outcome of ranking/packing, **not a dependable safety guarantee**.
Record/index snapshot integrity does not prove query-time causal eligibility.
Do not label this run fully clean merely because the answer is correct.

Code-level evidence: `_structural_rejection_reason` currently checks explicit
`valid_from`/`valid_to`, subject/state/authority and requested intervals, but has no
general observation-after-`plan.now` rejection. In contrast, HighConfigRetrieval's
`_raw_eligible` explicitly requires `record.created_at <= now`. A future fix must
align candidate/final revalidation with the host's knowledge cutoff, without
confusing `now` with `as_of`: a fact learned by current `now` may still describe an
earlier valid time. Do not add vehicle/sculpting/gardening or benchmark-ID rules.

An unresolved current/as-of conflict in `<unkeyed>` is also retained as an
unclassified semantic warning. It does not secretly become a green execution
flag. Reader resolves this particular old/new project sequence from the dated
source text; general conflict governance is not established by that answer.

## Graph authoring and accounting

Scope 2 projections: 183/183 current Store-bound records; 131 with rich edges,
52 fallback-only. Rich graph has 260 distinct edges / 261 edge-Episode links and
152 types. Projection completeness is not edge semantic correctness. During
authoring Graphiti logged two target-entity-not-found warnings (`INTERESTED_IN`
and `LOVES`). Their records completed, but those observations remain extraction-
quality concerns rather than silently being counted as flawless relation output.

| This round's scope-2 stage | New successful calls | Reported tokens |
| --- | ---: | ---: |
| Real graph projection | 824 | 3279857 |
| Source-name-only definitions | 7 | 14443 |
| Two natural planner passes | 2 | 23746 |
| Reader | 1 | 6127 |
| Reference-only task judge | 1 | 620 |
| Citation judge | 1 | 8541 |
| Total | **836** | **3333334** |

Zero failed/interrupted calls, retries or missing usage. No exact monetary cost or
hard token cap is claimed. Graph authoring dominates cost; QA's five requests total
39034 tokens. Query retrieval took approximately 80.27 seconds including remote
planning and cold local model setup; not a warm p50/p95 result.

Separate-process cache-only replay uses an empty key and adds zero requests or
attempts, with three downstream cache hits. It reuses the immutable retrieval
checkpoint, not another graph/planner/GPU execution. Plan, retrieval, packing,
answer, task/support grades, deterministic checks, evidence score and execution
classification all match. All snapshots remain unchanged.

## Provenance and verification

Graph batch pre-registered in `155151c`; consecutive query runner committed in
`8b0123d`. Schema budget frozen in `2a1e8e3`; exact natural-query preflight committed
in `4eb29a9` before its five paid calls. No algorithm/prompt/packing tuning between
the two opened natural questions; source-only graph/schema generation never sees
their questions, reference answers or annotated evidence.

| Ignored receipt under `data/doppel/` | File SHA-256 |
| --- | --- |
| `public-memory-consecutive-graph-scope02-live-v1.json` | `6b49b45b088862a6bbd813c81fe86085142ae6faf02418f940e62ea20291c892` |
| `public-memory-consecutive-schema-02-live-v1.json` | `d030ceedbc5ae2baa397349306a43d495a3927f2f971c55ed1a0e28285089a54` |
| `public-memory-consecutive-query-02-live-v1.json` | `c3adb774d855629efc9d5246df1fb0beed5ff2ad79358e1de49d1dd8df5360b6` |
| `public-memory-consecutive-query-02-replay-v1.json` | `39d1aeb8d5f8cf345e15ada4c0857b21c0cda9df2d959642b95052cfa2dfb19a` |

Authoritative Store: 34762 records, unchanged corpus hash
`11aab45f1bdfaebeea23bee822e53e5cdd94aef24f68bb020d90e9eda35e9cc3`;
active vector coverage 34760/34760 current. Graph write invocation verifies all
other diagnostic scopes' nodes/Episodes/edges unchanged. Successful scope-2 data
is retained. Complete graph histories now **2/50**, total 393 projected records;
scope 3's 222-record plan is frozen but not executed, remaining 48 histories are
not graph-ready. No reserved history was run.

Full regression with the new scoped runner: **1429 passed / 33 skipped / 3 subtests
passed**. Ruff repository-wide passes; Pyright on new modules/tests with the real
venv reports zero errors. `uv.lock` is preserved modified and is not staged.

## Next action

Preserve both opened-question runs and the temporal-source failure. Before broader
highest-config scoring, implement and synthetically test the general observation-
time boundary across lexical/vector/graph candidate and final Store checks. Keep
valid-time/as-of semantics orthogonal; include late observations about old facts,
future observations without explicit validity bounds, and future plans learned
before `now`. Any changed implementation needs a new frozen query protocol and
must not be merged into the original consecutive-batch score or overwrite it.

Then confirm the first two cases as development regressions and continue the fixed
third history under the explicitly revised protocol. Its source-only graph target
selection does not change. Do not continue collecting nominally clean scores while
relying on packing to happen to omit ineligible future observations.
