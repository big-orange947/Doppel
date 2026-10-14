# Fresh scope 02: temporal-order question completed in both profiles

The second fixed prospective question (`gpt4_d31cdae3`) completed in both unchanged
profiles. DeepSeek provisional task grades are correct for both; all two annotated
turns and two annotated sessions are covered in both contexts. This is **two of
fifty** questions scored so far, not a fifty-case accuracy, independently blind
evaluation, official LongMemEval, AML or publication acceptance.

The graph process continued normally after the chat interruption. On resumption
we inspected its completed receipt instead of reindexing it or paying again.
All 165 eligible personal memories had current Store-bound projections. Actual
rich-edge snapshot: 186 edges / 119 distinct names. Graph used 689 successful
calls / 2,926,266 tokens; source-only schema used five calls / 10,607 tokens.
No missing usage, provider failures, retries or owned-slot repairs. Two captured
missing-target endpoint warnings (`USES`, `ATTENDED`) remain; projection completion
is not proof that every intended semantic relationship was correctly extracted.

## Paired result

The question compares which occurred earlier: a solo Europe trip or a family
road trip across the American Southwest. Both answers convey the expected family
road trip, using the original owner's relative descriptions of the trips. Original
session dates/reference date are preserved; no query/gold entered graph/schema.
Raw ran first, full second, under separately committed eight-attempt total ceiling.

| Metric | Full high-config | Raw vector + reranker |
| --- | ---: | ---: |
| Provisional task grade | Correct | Correct |
| Annotated turn coverage | 2/2 | 2/2 |
| Annotated session coverage | 2/2 | 2/2 |
| Declared citation IDs legal | Yes, three IDs | Yes, two IDs |
| Provisional support of cited core answer | Supported | Supported |
| Judge quotes anchored / contradiction flagged | Yes / no | Yes / no |
| Context whole items / UTF-8 bytes | 20 / 21,286 | 11 / 22,731 |
| QA attempts / reported tokens | 5 / 33,489 | 3 / 14,179 |

Full used the actual natural planner, vectors and local CUDA scorer plus one graph
exploration search and twenty promoted paths. Explicit graph-path search count
was zero (conditional route not exercised), not falsely reported as one. Memory
and offered-path reranker stages completed. Both profiles found the answer;
**no marginal answer-accuracy uplift from graph is demonstrated on this case**.

## Retained defects and caveats

- Both answers are Chinese despite an English question, as in scope 01. Keep
  language compliance separate from provisional semantic task correctness.
- Raw opens by saying the earlier trip cannot be determined, but later explicitly
  concludes the Southwest trip was earlier. Its `abstained=false` accompanies a
  substantive answer; however the contradictory uncertainty wording is a real
  observed Reader-quality defect, not a retrieval failure. Do not rewrite it.
- Full adds an irrelevant historical-assistant aside about Germany. It labels
  that statement as an assistant's claim rather than an owner fact, but its inline
  memory ID is omitted from structured `cited_memory_ids`. The record **is** in
  supplied context, so this is not a fabricated/nonexistent source ID. Declared-ID
  legality and anchored support of the core answer do not exhaustively verify all
  inline-ID/list consistency or every added claim. This manual, non-independent
  observation does not revise the frozen judge grade or fabricate a new metric.
- Full execution remains `review_required`: zero classified execution failures,
  two unclassified open-conflict warnings in `purchase.laptop` and
  `best-friend.birthday-gift`. Keep the existing governance records/warnings and
  classifier unchanged. Bounded-index coverage notice remains informational.

These are correct provisional task answers, not clean all-dimension acceptances.
No new scorer/Reader tuning, special-case query rules, core/default changes or
live calibration controls were introduced after reading the outputs.

## Reproducibility, integrity and usage

Original live rows replayed with the API key removed. Semantic row content,
answers, contexts, task/citation grades and checks are identical. Six answer/judge
cache hits, zero misses; retrieval is checkpoint replay, not re-retrieval. Original
live profile receipt bytes and durable provider-call inventory remain unchanged:
zero new attempts. Schema/QA did not write Store/vectors/graph. Final selected-scope
source journal, corpus, vectors and graph are unchanged while scope 03 builds in
its separate scope. This is not a repeat-GPU-latency experiment.

Subsequent graph/schema/QA stages for scope 02 total **702 successful calls /
2,984,541 tokens**, excluding its previously ingested source messages. With prior
completed stages, the settled cohort subtotal is 1,786 attempts / 7,569,761 tokens;
ongoing scope 03 graph and first-ten source continuation are not included here.
Do not read ledger historical attempts as new cache-replay attempts or claim
exclusive currency accounting. No reserved histories were used.

Local ignored receipt SHA-256:

- Graph: `1031d867586e79d99a13165b27895a65032bcbca5b9c55f19b436ad65b02ccfc`.
- Schema: `39b8c53cac5341768ee41ccd32760fed2033293a6e050f2c338a89bed12814d6`.
- Paired QA: `700671689c361923b50e5c035d021e74c1ca831ff4ef6933a9bebf6b40faddb3`.
- Empty-key paired replay:
  `99cdfe138a315b7b2155460a361fa06332220bc25f4ebaee29b0b64605608d3a`.

The unchanged six prospective adapters' 43 offline tests pass; repository Ruff
passes. Prior full suite remains 1,840 passed / 33 skipped / three subtests passed,
not falsely described as a new full run. This round changed only stage/report docs;
the user's pre-existing `uv.lock` remains untouched/unstaged. Continue scope 03 and
the fixed first-ten source prefix, then report a larger same-snapshot block.
