# Paired response-policy diagnostic: gain, regression and judge noise

Frozen implementation `d3667f5`, preregistered plan
`49ff962acc9c137e66cdf8256371fb76e432cc529eaebc8cdbb059ae6c3776c7`.
Live: `data/doppel/public-memory-response-policy-live-v1.json`, SHA-256
`0545aec92c8febd1cc55e6d4ce76714b8f634c9dee0242eae326766119295c33`.
Replay: `data/doppel/public-memory-response-policy-replay-v1.json`, SHA-256
`af8560dcfa87692a9402afe4e7adf7a0f9cf0f641e44d5b3c898c2f922e33cbd`.

Seven opened cases, two context types, two fresh policies: 28 complete rows.
Unchanged Reader V2 versus experimental grounded_advice_v1, with identical data,
schema, generation settings and unchanged reference-only judge within a context.
Source hashes, old S request hashes and the frozen preflight all bind execution.
No retrieval/miner/graph/embedding/GPU/Store work; no changes to core/defaults or
old prompts/caches/answers/scores. Not full/blind/official LongMemEval or AML.
S uses the old raw-vector+reranker contexts, NOT newest highest-config Graphiti.
Oracle has label-selected full sessions and unequal budget; no retrieval uplift.

## Original diagnostic task labels (not revised)

| Case / category | S V2 | S advice | Oracle V2 | Oracle advice |
| --- | --- | --- | --- | --- |
| d52b4f67 / user fact | correct | correct | correct | correct |
| 21d02d0d / multi-session | correct | incorrect* | correct† | incorrect |
| 38146c39 / preference | incorrect | correct‡ | incorrect | correct‡ |
| gpt4_d9af6064 / temporal | correct | correct | correct | correct |
| 3ba21379 / update | correct | correct | correct | correct |
| ceb54acb / earlier assistant | correct | correct | correct | correct |
| 29f2956b_abs / refusal | correct | correct | correct | correct |

Each arm's original judge total: 6/7, ordinary 5/6, refusal 1/1. Across the two
contexts each policy is 12/14. Two contexts per case are correlated, not fourteen
independent questions. No statistical/generalization claim. All 28 citation ID
sets and derivation structures pass legality checks, NOT semantic faithfulness.

* S count **judge inconsistency**, not established behavioral regression: V2 says
two runs but qualifies that only March 5 is explicitly work-related. The candidate
also opens with two and gives the same qualification; its derived result says
`2次错过的趣味跑（3月5日和3月26日）`. The judge accepts V2's conveyed count with a
caveat but rejects the candidate as effectively one. Preserve the original label;
do not silently promote it to correct or declare two genuine count regressions.

† Oracle V2 has mixed reasoning despite an accepted final count: it initially
reports one, then adds the second, and distinguishes work commitments from work
reasons implausibly. A correct task label is not proof of coherent reasoning.

Oracle candidate genuinely concludes one. The source records both March 5 work
commitments and: `I've been pretty busy with work lately and missed a few events,
including a 5K fun run on March 26th.` The candidate itself acknowledges work was
busy but insists this does not mean work commitments, omitting March 26 from the
count. This is over-literal causal qualification, NOT failure to retrieve a date.
No race/work-specific prompt or test correction was added to fix it.

‡ The generic instruction changes preference behavior in both contexts: it cites
remembered sugar experimentation, generates new complementary suggestions and
explicitly distinguishes proposals from recorded advice. V2 refuses because the
specific new request is absent from history. The proposal need not have been
recorded: memory supplies personal premises, not an already-written answer.
This is a downstream response-policy issue, not a demonstrated graph deficiency.

There is also a **plan-to-experience overstatement** in S candidate wording:
it says `you've been working with brown sugar, almond flour and sliced almonds`,
while cited owner items say `I think I'll try using both brown sugar and almond
flour` and `I'm excited to try out this recipe`. These support plans/interest, not
proven completed experience. Other personal premises (turbinado experimentation)
are explicitly recorded. This manual text inspection is separate from untouched
task labels; no independent support judge was run. Do not advertise full grounding.

The one refusal remains a refusal in all four rows; it does not confuse guitar
practice with violin practice. One control is insufficient evidence of broad
hallucination safety. Historical fact/update/assistant questions retain their task
labels. Most English recall questions still get Chinese answers, despite existing
language instructions; the personalized proposals are English. Language compliance
has not been formally graded or fixed by this experiment.

## Usage and replay

- 28 Reader + 28 judge new calls, all successful; zero retries/failed/missing usage.
- Reader: 183602 input, 6701 output, 190303 total tokens.
- Judge: 13539 input, 1266 output, 14805 total tokens.
- Combined: **205108 tokens**, 89369 cache-miss input, 107772 cached input,
  7967 output, zero reasoning tokens. Provider cached tokens are not local request
  cache hits; all 56 requests were new, as preregistered for contemporaneous arms.
- Account balance 5.26 CNY before and at immediate receipt completion; later free
  balance read 5.19 CNY: observed net debit approximately **0.07 CNY**, not an
  exclusive per-run invoice. Retain the immutable immediate-zero observation.
  Settlement lag prevents treating balance polling as a strict spending cap.
- Empty-key replay: rows and plan canonically equal, 28+28 hits, zero new calls.
- Twelve new offline protocol tests; 46 directed tests passing. Whole-repo Ruff
  passing, Pyright new module clean. No full-suite rerun; previous 1559-pass full
  suite belongs to the earlier source-window implementation, not this build.
- `uv.lock` untouched/unstaged; no database/journal/old cache/index modifications.

## Decision / next work

Keep the candidate benchmark-only; **do not switch a default on these labels**.
It fixes one opened preference task in two contexts, but a genuine oracle count
regression, one judge inconsistency and a plan-to-experience overstatement remain.
No gain in aggregate labels and no recommendation generalization demonstrated.

Return next to the already prepared highest-config history 9: reuse its existing
graph/schema rather than author history 10 or start M. Freeze a small natural-query
QA budget and report evidence coverage, answer correctness and source contribution
separately. Broader, unrelated advice/recall controls are needed before promoting
any generic Reader policy; reference-only scoring noise must remain visible.
Keep completed raw-S/oracle results as diagnosis, not pooled highest-config scores.
