# Fourth prospective question: assistant recommendation recalled by both profiles

The fourth fixed question (`7e00a6cb`, assistant-side recall) completed both frozen
profiles and exact empty-key checkpoint replay. Both the provisional reference-only
task judge and the separate citation judge mark both answers correct. Neither
scoring stage is independent verification or the official GPT-4o evaluation.
Four of fifty selected questions are now scored; ten source histories are ready.

## Paired result

The question asks which Amsterdam hostel near the Red Light District the assistant
previously recommended. Both profiles answer **International Budget Hostel**.
The decisive evidence is the same original assistant message, not a derived owner
fact: `role=assistant`, `actor=agent`, `authority=agent_output` remain explicit.
Raw ranks it first; full packs it second after a derived owner travel plan.

Both answers correctly attribute the recommendation to the historical assistant,
and distinguish it from personal hostel experience. The extra experience disclaimer
is not necessary to answer the question, but is supported by another supplied
assistant message. Both answers are in English for this English question; this
single result does not resolve earlier language drift.

| Metric | Full high-config | Raw vector + reranker |
| --- | ---: | ---: |
| Primary provisional task grade | Correct | Correct |
| Citation judge's separate correctness | Correct | Correct |
| Annotated source turn / session covered | 1/1 / 1/1 | 1/1 / 1/1 |
| Declared citations | Three, legal | Two, legal |
| Citation support / quotes anchored | Supported / yes | Supported / yes |
| Context whole items / canonical UTF-8 bytes | 20 / 17,376 | 20 / 20,614 |
| Provider attempts | 5 | 3 |
| Reported tokens | 33,830 | 13,686 |
| Model-stage failures / missing usage | 0 / 0 | 0 / 0 |

All eight QA attempts succeeded: **47,516 tokens**. Empty-key checkpoint replay
uses six Reader/judge cache hits, no new provider attempts, unchanged ledger rows,
identical semantic answers/grades and untouched immutable live receipts. It does
not repeat retrieval/Planner and is not an independent replication.

## Full execution and attribution

The full profile actually ran one graph path search and one graph exploration,
promoted twenty paths and completed both memory/path reranking on CUDA. Execution
is `completed_within_contract`: zero failures/unclassified warnings, bounded
index candidates, returned-source provenance resolved. Aggregation not requested.
This is not an exhaustive-scope/answer-quality/publication certificate.

The critical hostel evidence is in the raw-dialogue channel; raw-only also finds
and answers it. Graph participation therefore **does not demonstrate marginal
accuracy uplift** in this question. The positive result is that the combined
pipeline retains usable assistant-side evidence without relabeling it owner truth.
No graph ablation or semantic-necessity claim is inferred from participation.

## Source and graph accounting

The first ten histories are complete: 499 source chunks / 5,016 original messages,
1,954 derived records including inactive, thirty governance markers and 7,494
provenance checks with zero failures. Cumulative source ledger is 500 attempts,
499 successes and one preserved failure; 2,460,363 known tokens / one missing usage.
Source completeness alone is not semantic truth or answer accuracy.

The fourth graph completed 162 records after the explicitly approved recovery:
36 additional projections / 139 successful recovery calls / 620,581 tokens,
zero incomplete-slot repairs. Original 529 attempts remain unchanged.
Graph cumulative 668 attempts, 667 successes + one failure, 2,824,469 known tokens,
one missing usage. Six schema calls add 12,649 tokens and preserve all 128 names.
Actual snapshot: 172 distinct rich edges; 174 per-episode rich-edge associations
are not 174 unique edges. No observed allowlisted endpoint warnings; unobserved
warning classes and semantic completeness are not certified.

Selected Store/vector/source-journal, other fresh graph scopes and final scoped
graph all remain unchanged across their corresponding checks. Both failed
source/graph receipts remain. Unknown usage is not zero and exact billing is not
known. Latest provider balance observation is 53.63 CNY, not exclusive cost.

## Prospective checkpoint and next step

| Fixed question type | Full provisional task | Raw provisional task |
| --- | --- | --- |
| 01 user fact | Correct | Correct |
| 02 temporal reasoning | Correct | Correct |
| 03 knowledge update | Correct | Incorrect* |
| 04 assistant recommendation | Correct | Correct |

*The citation judge separately calls the same third raw answer correct. Preserve
both scores; the only task-score difference is judge-sensitive, not established
graph/retrieval uplift. First-four counts are **4/4 vs 3/4**, not reliable population
accuracy; no unanswerable question in this new cohort has been scored yet.

Continue unchanged fixed ordinals 05 (multi-session), 06 (preference), 07
(unanswerable), then through ten. Their sources are already prepared; project all
eligible scoped graph records, freeze source-name schema and paired query plans,
then score/replay. Do not retune from these four answers or claim full-500/AML/
independent blind/publication performance. User postponed idle-GPU latency rounds.

## Bound artifacts and verification

- Graph completion receipt:
  `b6f245388f5f1e1b1b92ed03043e6dee8aa2cec1b042abec12880e347bd86c28`.
- Schema receipt:
  `6d2351b68a2b0cda155fb66d9fe6cdfc3a67482659c0741752fe9b5d0b93202c`.
- Live paired query receipt:
  `8c4d5b63f77136e8c1ab55c2bd48b1d89e9a21563a7607f528a7b1cfd0f4df88`.
- Exact empty-key replay receipt:
  `e3d0f83053666b3921dae85d7b7886534eb5aff59e318eac71e38188e69efbc8`.

Full suite **1,852 passed / 33 skipped / three subtests passed**; Ruff repository
check and new-file formatting pass. Only operational recovery code/tests/docs
changed. Original frozen core, adapters, prompts and models stay unchanged;
`uv.lock` remains the user's original unstaged change.
