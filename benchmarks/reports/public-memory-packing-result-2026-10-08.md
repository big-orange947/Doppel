# Rank-fit packing diagnostic: valid paired experiment, no coverage gain

## Result

The plan/code frozen in `797c735` ran locally with the API key removed from the
child process. All **sixty rows** completed: ten questions, three channels, two
packing policies. The thirty baseline rows reproduced the previous run exactly
after removing only experiment trace fields. Every original packed item remains
unchanged in the experimental context. Both checks passed, all source inputs
remain unchanged, and the command exited zero.

**There is no increase in annotated-turn provenance coverage.** The candidate
fills more of the same byte budget on five of thirty channel/query contexts,
adding ten items in total. This is a capacity-utilization result, not evidence
of better QA or a reason to promote the candidate to a production default.

## All six profiles

| Channel | Policy | Packed annotated-turn coverage | All annotated turns packed | Mean items |
| --- | --- | ---: | ---: | ---: |
| Raw | Prefix | 95% | 9/10 | 16.0 |
| Raw | Ranked fit | 95% | 9/10 | 16.5 |
| Memory | Prefix | 80% | 8/10 | 20.0 |
| Memory | Ranked fit | 80% | 8/10 | 20.0 |
| Combined | Prefix | 100% | 10/10 | 18.0 |
| Combined | Ranked fit | 100% | 10/10 | 18.5 |

Both use one identical candidate pool/ranking per channel/query, cap80 candidates,
cap20 final items and cap24,000 serialized UTF-8 bytes. No whole-item text is
truncated or rewritten, no raw evidence is expanded from the source journal, and
no actor/authority rule is changed. The experimental packer simply continues past
items that cannot fit. Rank traces retain every skipped/selected position.

No profile is removed for performing poorly. Memory's unchanged results are
expected because it already packs twenty compact items. Increasing this final
cap was not part of the experiment and was not done after seeing the result.

## Changed contexts

| Case | Channel | Added items | Before bytes | After bytes | Coverage change |
| --- | --- | ---: | ---: | ---: | ---: |
| `0e5e2d1a` | Raw | 2 | 22,835 | 23,963 | 100% → 100% |
| `0e5e2d1a` | Combined | 2 | 22,835 | 23,981 | 100% → 100% |
| `86f00804` | Raw | 2 | 20,300 | 23,797 | 100% → 100% |
| `gpt4_2f91af09` | Combined | 3 | 21,806 | 23,889 | 100% → 100% |
| `7a8d0b71` | Raw | 1 | 23,490 | 23,987 | 100% → 100% |

The other twenty-five contexts are identical to baseline. The raw plant-acquisition
case remains at 50% annotated-turn coverage. Thus this policy does not resolve the
identified raw coverage loss. Added unannotated items might help a Reader or
introduce distractions; neither is measured here. Original assistant-channel
losses in derived memories and original Judge errors are unchanged.

## Source/engineering checks and usage

Store revalidation checks by arm:

| Channel | Prefix | Ranked fit |
| --- | ---: | ---: |
| Raw | 160 | 165 |
| Memory | 414 | 414 |
| Combined | 207 | 213 |

All **1,573** checks complete without a stopping failure; corpus snapshot hashes
match before/after. Maximum experimental context size is 23,987 bytes. These
checks establish scope/source/state consistency, not semantic truth. Local
reranking executes thirty calls / 2,400 pairs on CUDA, with zero truncated pairs.
No Reader, Judge, extractor, Graphiti or production natural Planner executes.
**Paid/provider calls = 0, provider tokens = 0**. No Store/index repair or record
writes; the existing Store initializer may execute idempotent schema DDL.
Docker was already healthy, and no auto-launch, restart or volume operation ran.

Full tests: **1,316 passed / 33 skipped / 3 subtests**, one existing Graphiti
Pydantic warning. Targeted tests:55 passed. Whole-repository Ruff, changed-file
formatting and scoped Pyright (zero errors/warnings) pass. Twenty-two additional
test cases cover caps/overflow, exact-prefix preservation, paired experiment
integrity and existing scope/index/revocation checks on the experimental path.
These are not model-intelligence tests. User-owned `uv.lock` remains untouched.

## Binding and limitations

Ignored local result `data/doppel/longmemeval-packing-live-v1.json`, SHA-256:
`fc6e367bb0b5df0aaec95949393372a7d9d0dc6e98ba3ca46e139140fa1fed3b`.
Plan fingerprint:
`96086b1c4fe180e0a3207c84d5dbfc71eb841edcaa1e05c64c00e5750fd27cb7`.
Preflight SHA-256:
`aef2800fc372fd19560dd2beb32c8f0880fcdd81203cf51f0a44f906d179fd8c`.
Input preservation verifies the dataset, manifest, completed ingestion journal,
ingestion plan and parent report hashes. The former live report hash remains
`6d2bb1f48ed03830c21706afbb8b80d580dfb8ec913e7d00ad903f321e975932`.
The comparison reproduces the original retrieval rows, not a new key-free replay
of the complete earlier ingestion/Reader pipeline.

Public opened development, N10, not independent blind/full LongMemEval/AML. The
same local Chinese embedding/English corpus confound and small exact vector
ordering remain. Provenance coverage does not prove answer-bearing detail is
retained in a summary, or that more bytes means a better answer.

## Decision and next measurement

Keep the candidate experimental and retain the unchanged baseline/default. Do
not raise caps, change models, replace cases or add subject-specific rules to
turn the null result into a gain. Do not repair the earlier same-model scores.

A bounded next Reader comparison can reuse the twenty-five identical request
contexts from the frozen cache and spend at most five new calls on the changed
contexts, using exactly the same Reader and generation settings. Keep all thirty
logical rows rather than score only changed/high-performing cases. It needs a
fresh plan/cache/budget binding before execution. Evaluate reference-answer
delivery separately from context-justified refusal, with semantic judgments
explicitly provisional; never silently count an answerable refusal as QA success.
This later experiment has not run and no answer-score improvement is claimed.
