# Fifty-question diagnostic: completed answers and corrected task scoring

All fifty selected questions now have six retrieval profiles and three completed
Reader/primary-Judge profiles. The reference-only regrading also completes all
150 rows. This is a public diagnostic using local BGE vectors/reranking and
DeepSeek v4 flash, with shared sessions and one no-answer question. It is not full
LongMemEval, independent blind verification, production Planner/Graphiti or AML.

## Task accuracy: use these provisional labels

| Profile | Correct / scored | Task accuracy | Unscored | Mean logical Reader input tokens |
| --- | ---: | ---: | ---: | ---: |
| raw_vector_reranked | 35/50 | 70.0% | 0 | 5,550.5 |
| memory_vector_reranked | 28/50 | 56.0% | 0 | 3,113.6 |
| combined_vector_reranked | 33/50 | 66.0% | 0 | 4,935.4 |

These are same-model reference-only task judgments, not independently verified
truth. All six frozen scoring controls pass, checking exact answers, answerable
refusals, qualified arithmetic, unanswerable refusals, wrong arithmetic and
contradictory answers. Those controls verify the identified boundary only.
Reference-only grading does not assess citation support or language compliance.

Logical token means map each row's immutable Reader request to the provider usage
for that request. Duplicate rows share one physical call; these means describe
context sizes and must not be summed as actual billing. Context byte caps were
equal, token consumption was not equal. Owner-memory uses about 43.9% fewer input
tokens than raw. Outside the nine assistant-history questions, raw and owner-
memory both score 28/41, while combined scores 26/41. This is a useful compression
observation, not proof of equivalence or non-inferiority.

| Question type | Questions | Raw | Owner-memory | Combined |
| --- | ---: | ---: | ---: | ---: |
| knowledge-update | 9 | 8/9 | 7/9 | 8/9 |
| multi-session | 8 | 6/8 | 6/8 | 5/8 |
| single-session-assistant | 9 | 7/9 | 0/9 | 7/9 |
| single-session-preference | 8 | 2/8 | 2/8 | 1/8 |
| single-session-user | 8 | 6/8 | 6/8 | 6/8 |
| temporal-reasoning | 8 | 6/8 | 7/8 | 6/8 |

The single no-answer question is correct in all three profiles. This cannot
establish reliable refusal behavior. Assistant-history recall requires assistant
sources: the owner-memory profile is intentionally owner-only. Preference tasks
often ask for new personalized advice; a Reader restricted to supplied records
frequently reports facts or refuses instead of supplying the requested advice.
That behavior limits this reference Reader's task coverage.

## Why the earlier accuracy figures were inflated

The initial combined correctness/support Judge scored 45 raw, 43 owner-memory and
44 combined answers correct before its support-quote exclusions. Its reported
anchored rates were 44/49, 43/50 and 43/49. Those figures must not be used as task
accuracy. Inspection of the nine assistant-history owner-memory answers finds
eight explicit pure refusals incorrectly accepted because the supplied context
does not contain the reference answer. The ninth refusal was marked incorrect,
showing inconsistent treatment of the same task boundary.

The frozen [reference-only plan](public-memory-expansion-50-task-accuracy-plan-2026-10-09.md)
withholds context, profile names, old judgments and self-reported abstention flags.
It compares the original answer text to question/reference, preserving qualified
derivations that actually convey the requested result. Its new labels change 36
old `correct=true` labels to false: ten raw, fifteen owner-memory, eleven combined.
No old false label changes to true. All original answers and grades remain intact.
The regrading is still provisional; label differences alone do not prove all
36 changes are independently correct.

The two old unanchored support observations remain: `06878be2` raw and combined.
The primary Judge joined noncontiguous source excerpts with ellipses as if they
were a literal quote. Correctness and support have separate denominators: these
two support observations stay unscored even though their answer texts receive
reference-only task judgments.

## Evidence coverage and concrete failure observations

The [retrieval report](public-memory-expansion-50-retrieval-result-2026-10-09.md)
records packed annotated-turn macro coverage of 92.18% raw reranked, 79.25%
owner-memory reranked and 93.20% combined reranked, over 49 annotated questions.
Source coverage is considerably higher than task accuracy. It measures cited
source positions, not preservation of the answer in a summary or successful
reasoning over the selected text.

- `bf659f65`, album/EP count: all annotated turns are in every 80-candidate pool.
  Raw/combined packed contexts contain none of them and contain eight assistant
  recommendation/review items instead. Owner-memory packs two of three annotated
  turns. This locates a real loss between candidates and final context; traces
  here do not distinguish every reranking loss from prefix-byte packing loss.
- `3ba21379`, current model project: the owner-memory Reader sees Ford F-150 and
  Mustang summaries both marked current and cannot select the latest project.
  Raw-backed profiles recover the explicit completed-project/transition context.
  Full source citation coverage alone does not show that the summary retained
  that transition. This motivates testing source backing and temporal continuity.
- `2b8f3739`, market income: all three needed source turns reach the combined
  context. The Reader lists 120, 225 and 150 but states a total of 465 instead of
  495. This particular failure is in answer arithmetic, not candidate discovery.
- `gpt4_d9af6064` and `gpt4_4cd9eba1`: all annotated turns reach the combined
  context. Answers introduce acquisition/setup ambiguity or calendar objections.
  The second example also exposes a weekday/date ambiguity relative to the
  benchmark's intended answer. Do not resolve such issues by case-specific rules.
- Spot inspection finds Chinese answers to English questions despite the frozen
  language instruction. All 150 citation/derivation structures are legal, but
  that structural check does not verify language, arithmetic, abstention semantics
  or task completion. Self-reported abstention counts are observations only.

The combined profile has higher packed source coverage but lower task accuracy
than raw. Automatic mixing has no demonstrated answer advantage in this sample.
The evidence supports testing general ranking/source preservation, with separate
Reader limitations, rather than treating a better coverage number as completion.

## Execution, accounting and reproduction

- Initial QA: 145 Reader + 145 primary-Judge calls = 290 successful new calls,
  1,632,720 reported tokens; zero failures and zero missing usage.
- Reference-only stage: six controls + 142 distinct row requests = 148 successful
  new calls, 79,754 reported tokens; zero failures and zero missing usage.
- Total new paid calls in these answer/scoring stages: 438; reported tokens:
  1,712,474. This is reported usage, not an exact billing calculation.
- Both stages replay without API keys: zero new calls; all 150 outputs, checks,
  request identities and summaries match their corresponding live results.
- Reader outputs were never regenerated for regrading. Retrieval, source records,
  indices, old caches/journals and reserved histories were not changed.
- Focused verification: 64 tests pass across comparison, expansion, fifty-row
  harness and reference-only scoring; Ruff passes and both new modules have zero
  Pyright errors. Full-suite rerun is not claimed. Existing `uv.lock` remains
  unstaged and unchanged by this work.

| Artifact | SHA-256 |
| --- | --- |
| `longmemeval-expansion-50-quality-v1.json` | `89c1e888f278b71bd4df87446604db8a2bc5ee7e65647af03dadc235c67189aa` |
| `longmemeval-expansion-50-quality-replay-v1.json` | `19525c719b4d51abf99194f6b381d128704005780f1c4758f6464fa29c85ce2b` |
| `longmemeval-expansion-50-task-accuracy-v1.json` | `b5877d529ae4b0b3cf6015e9843fd1f73bbbb00a2909267a36f9eca1d663b0bc` |
| `longmemeval-expansion-50-task-accuracy-replay-v1.json` | `8f86556353cb42807fc5d124b8621f9ba6a3e74574d4a2d918e8f3d27769aa18` |

All JSON artifacts live in the ignored `data/doppel` directory. QA executes under
`a7f138e`; reference-only regrading executes under `eb60177`. Both source reports
list only the pre-existing `uv.lock` as a dirty tracked file.

## Next work

Keep this fifty-question result as an opened diagnostic baseline. Prioritize
generic candidate-to-context traces and source-aware ranking/packing so real
owner actions are retained alongside useful derived summaries. Examine temporal
transition preservation in extracted memories. Evaluate the reference Reader's
personalized-advice/task behavior separately from memory retrieval. Freeze each
change before checking unopened groups and before integrating full production
Planner/Graphiti comparisons. Competition-model evaluation and complete 500-case
coverage remain future stages; these scores do not grant publication readiness.
