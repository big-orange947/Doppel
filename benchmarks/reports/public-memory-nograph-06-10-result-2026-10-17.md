# Non-graph follow-up complete: five questions, ten rows, thirty calls

The new, separately frozen non-graph experiment completed fixed source ordinals
06–10. Both profiles score **4/5** with the unchanged provisional task judge.
Both cover all six labelled source turns and all six labelled sessions across
the four answerable questions; the unanswerable question has no evidence-recall
denominator and both correctly abstain. No graph connection, authoring, relation
schema, source extraction, LLM Planner, Store/vector writes or model retries.

This does not complete ten full-high-config pairs. Earlier cases 01–05 remain a
different graph-prepared protocol; scope-06 graph remains paused at 103 complete /
one started entry, and graph 07 was never started. Preserve all old receipts,
calls/failures/missing usage and code. No whole-cohort or release gate is granted.

## Per-question outcome

| Ordinal / public type | Raw vector + reranker | BM25 + vector + owner memory/raw + reranker |
| --- | --- | --- |
| 06 preference / guitar-shopping advice | Incorrect: over-abstained | Incorrect: over-abstained |
| 07 unanswerable / uncle's birthday baking | Correct abstention | Correct abstention |
| 08 user fact / Japan trip duration | Correct | Correct |
| 09 temporal / days between two events | Correct | Correct |
| 10 knowledge update / colleague's current company | Correct | Correct |

Raw reports a two-week Japan trip, six days between the two dated events, and the
colleague's newer owner-stated employer. It explicitly distinguishes a historical
assistant spreadsheet entry from the owner's own employment statement. The mixed
profile also finds the relevant claims, with derived and original evidence
properly labelled. Its final answer in case10 is Chinese for an English question;
the other nine answers are English. Language drift is not fixed or scored away.

## Retrieval vs answer-policy failure in case06

Both packed contexts contain the labelled owner statement about upgrading a
Fender Stratocaster to a Gibson Les Paul. Both Readers cite that exact statement,
but refuse to provide shopping advice because no historical buying checklist is
stored. This fails the task's personalized-advice objective despite successful
retrieval. The mixed answer also unnecessarily questions the music-store visit
because it cannot confirm it from history, even though the current question says
the user is visiting. That is an answer-policy/current-input handling limitation,
not a demonstrated missing-memory or missing-graph problem.

The separate citation judge calls both refusals correct/supported because their
descriptions of the retrieved items are faithful. That is **not** task success:
it rewards an evidence-faithful refusal which fails the user's requested task.
Keep primary task grades false; do not rewrite them to obtain 5/5. This is a
known task-vs-faithfulness evaluation mismatch, not new evidence that the task
judge should be discarded. No paid judge recalibration or Reader tuning follows
these results. A future answer-task experiment would need a new frozen identity.

Case07 correctly distinguishes a niece's recorded lemon-blueberry cake from the
uncle mentioned in the question, and does not assert that the user baked that cake
for the uncle. Its correct abstention is one case, not a privacy/safety certificate.
Case09 is one successful date-difference question, not comprehensive temporal
planning or exact-count validation.

## Metrics and accounting

| Metric | Raw baseline | Mixed non-graph |
| --- | ---: | ---: |
| Primary task correctness | 4/5 | 4/5 |
| Answerable labelled turns / sessions found | 6/6 / 6/6 | 6/6 / 6/6 |
| Unanswerable correct abstention | 1/1 | 1/1 |
| Declared citation legality / quote anchoring | 5/5 / 5/5 | 5/5 / 5/5 |
| Provisional citation support | 5/5 | 5/5 |
| Model attempts, all successful | 15 | 15 |
| Reported tokens, complete usage | 65,163 | 69,861 |

**30 calls / 135,024 tokens total**, no failures/interrupted/missing usage. Existing
source extraction and local embedding costs are sunk and excluded here; this is
the marginal follow-up cost, not the cost of a fresh corpus from zero.

The mixed profile uses existing production BM25 and RRF, not a whole-question
substring query. Instrumented BM25 candidate counts for 06–10 are 690, 514, 548,
690, 479 before the fixed fused top80 selection and local reranking. Broad positive
IDF matches are not calibrated relevance probabilities. There is no evidence of
a score advantage for BM25/mixed memory on these five questions. This comparison
changes both lexical fusion and allowed channels; it cannot isolate a causal
BM25, derived-memory or fusion gain.

All five original source/Store/current-vector snapshots stay unchanged. The
algorithm is a bounded full-scope reference BM25 scan, not a persistent full-text
index or a production-scale latency claim. Dates/effective bounds remain in
evidence for Reader reasoning; this arm has no temporal planner or exact-count
certificate and must not be presented as feature-equivalent to full high-config.

Exact replay in a separate process with the key removed completed ten rows:
**30 cache hits / zero misses / zero new attempts**; durable attempt inventory
stays at30, original live row receipts remain unchanged and semantic rows match.
It does not rerun retrieval, establish independent correctness, or turn the
provisional DeepSeek judgments into official GPT-4o/AML results.

## Artifacts, code and next step

- Frozen preflight: `833b2e3c2e40b5431cfc04c157aa0ba6a27af888483712dfd841ba7aa88afe95`.
- Live result: `1608c8018c23b2db2ebb709b48140c1dd5370dd629104ffbff6d126d7fbce8a5`.
- Empty-key replay: `a135c52a5fb69d756c0499f81eef3e9b90ed6e04c7de2ab903f4f997694f0103`.
- Run: `data/doppel/public-memory-nograph-06-10-v1/`.

New evaluation-only adapter reuses existing retrieval/answer/authority/source
guards; no core API/default/prompt/model edits. Full suite **1,869 passed / 33
skipped / three subtests passed**, including17 new adapter tests; Ruff repository
and file formatting pass. `uv.lock` remains the user's original unstaged change.

Retain Graphiti as optional/experimental and stop full-corpus authoring as the
default evaluation prerequisite. Next prefer a bounded larger non-graph retrieval
assessment with predeclared budget and separate evidence/task metrics, not more
graph preparation or a new judge-calibration loop. Any future personalization
Reader work belongs to the evaluation/application layer and must not introduce
scenario-specific retrieval rules. Do not combine these five answers with earlier
high-config results into a supposed ten-question full-high-config score.
