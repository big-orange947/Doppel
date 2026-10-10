# DeepSeek Flash regrade completed: labels unchanged, limitations retained

Preregistered implementation commit `20ab2cf`; plan
`287c698ad98c0659696605a1dbe62ff46b7977c53a6106a65f39fb9072fb13c4`.
Live artifact `data/doppel/public-memory-deepseek-prompt-regrade-live-v1.json`,
SHA-256 `34c740e09375797905016d3723d682ac14b6479b09d457c249eeb67240b5dfce`.
Key-removed child-process replay:
`data/doppel/public-memory-deepseek-prompt-regrade-replay-no-key-v1.json`, SHA-256
`545b663c66c5393b781174b0ebdda3df78a1fb93ce8c82a588534cb57602c2d0`.

## Result

All 28 unchanged answers graded successfully, no failed/interrupted attempts,
no truncation or ambiguous yes/no completions, no retries. Every returned model
name was `deepseek-flash`, requested through legacy `deepseek-v4-flash`.
Pinned official **prompts** were reused, but the **official GPT-4o scorer was not
run**. Reader and judge are the same model family. Not an independent benchmark,
official LongMemEval metric, highest-config retrieval score or AML result.

| Context / existing policy | Ordinary | Refusal | All | Old-label changes |
| --- | --- | --- | --- | --- |
| S raw-vector+reranker / reader_v2 | 5/6 | 1/1 | 6/7 | 0 |
| S raw-vector+reranker / grounded_advice_v1 | 5/6 | 1/1 | 6/7 | 0 |
| Full evidence sessions / reader_v2 | 5/6 | 1/1 | 6/7 | 0 |
| Full evidence sessions / grounded_advice_v1 | 5/6 | 1/1 | 6/7 | 0 |

These are **seven opened questions with four correlated arms**, not 28 independent
questions. No new answers, retrieval, graph, embeddings, ingestion, Store writes
or core/default changes. No unopened/reserved cases. The previous answer report,
old labels, official-endpoint preflight and existing graph assets remain intact.

## Interpretation by case

Facts (`d52b4f67`), temporal (`gpt4_d9af6064`), update (`3ba21379`), historical
assistant output (`ceb54acb`) and refusal (`29f2956b_abs`) keep yes in all arms.
One refusal control is insufficient to demonstrate general safety.

Preference (`38146c39`): both old reader_v2 answers remain no; both generic
new-advice answers remain yes. This agrees with the prior diagnosis that this
opened task asks for a new personalized proposal, not a previously recorded
proposal. It is a response-policy result, not evidence that more graph extraction
would fix it. No statistical/generalization claim is supported by one question.

Count (`21d02d0d`): reader_v2 remains yes in both contexts, new-advice remains no
in both. Do **not** collapse these four outputs into two demonstrated regressions:

- S V2 opens with two, then qualifies that only one date is explicitly work-related.
  S advice also opens with two and a similar qualification; its derived output
  additionally emphasizes only one explicitly work-attributed event. The new
  binary judge preserves the old distinction but gives **no rationale**. This
  does not resolve whether the distinction is rubric ambiguity or label noise.
- Full-session advice explicitly concludes one against reference two; the known
  over-literal work-cause qualification remains a genuine answer-level problem.
- Full-session V2 conveys two but has internally confused qualifications. A yes
  task label is not evidence of coherent reasoning or full faithfulness.

The S advice answer's previously inspected plan-to-experience overstatement
remains unchanged. This judge sees question/reference/answer, **not source
citations or context**, so its yes cannot validate that overstatement. Likewise,
English-question/Chinese-answer drift and citation grounding were not graded here.
No prior label has been silently repaired, promoted or replaced.

Changing from the old meaning-only prompt to the pinned category-specific rubric
changed zero labels on this cohort. That is observed agreement, **not proof of
judge correctness** or independent replication. Keep the manual caveats visible.

## Accounting and replay

- 28 new scoring HTTP attempts, all successful, zero local-cache hits live.
- 7,270 input + 28 output = **7,298 reported tokens**; all 28 usage receipts
  complete. Of input: 7,014 cache-miss and 256 provider-cache-hit tokens.
- Thinking explicitly disabled. Provider did not separately report reasoning
  tokens in these receipts; do not infer a measured reasoning-token counter.
- Immediate balance observation: 5.13 → 5.13 CNY, displayed delta 0.00. This is
  **not free-call evidence or an exclusive invoice**; rounding/settlement timing
  can hide a small charge. Attempt and byte budget respected; no hard currency cap.
- Second process with `DEEPSEEK_API_KEY` removed: 28 local-cache hits, zero misses,
  no additional ledger reservations or network calls. Plans, rows and summaries
  exactly match live; execution/cache metadata and file hashes appropriately differ.
- 14 new offline tests plus 49 unchanged official-harness tests: **63 passed**.
  Whole-repo Ruff, new-file formatting and Pyright pass. Full suite was not rerun
  in this addition; prior 1,627-pass full suite belongs to the preceding build.
- `uv.lock` remains unstaged. Reports/cache/export data stay in ignored directories;
  no credentials persisted. No Docker/GPU needed or touched.

## Next decision

Continue low-cost DeepSeek diagnostics; do not block development on GPT-4o.
Preserve official grading as a later optional verification step. Stop repeatedly
rejudging these same seven answers as if that created independent evidence.

Next prepare generic Reader-policy controls for planned vs completed experience,
new advice vs recalled history, directly inferable premises vs unsupported guesses,
and language consistency. Freeze unrelated synthetic controls first; only then run
a separately frozen paired Reader comparison on the opened cases. Keep the old
answers/labels unchanged. No race-, recipe-, entity- or dataset-specific patches.

Lazy/eager cost-quality comparison remains later competition-only work; no new
S graph backfill is authorized by this regrading step and no default is switched.
