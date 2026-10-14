# Fresh scope 03: first provisional score difference, not graph uplift

The third fixed prospective question (`b6019101`) completed both frozen profiles
and exact empty-key checkpoint replay. Primary reference-only task grades: full
correct / raw incorrect. The separate citation/support judge calls the **same raw
answer correct**, so the one-row task-score difference has explicit grading
sensitivity. Preserve both outputs/labels; do not retune the rubric or rewrite
answers. Only **three of fifty** selected questions are scored.

## Source, graph and schema

All 205 eligible personal memories have current Store-bound Graphiti projections.
The actual scoped snapshot has 229 rich edges and 155 relation names. Graph used
856 successful attempts / 3,575,175 tokens; source-name-only schema used seven
attempts / 15,726 tokens. Zero failed/interrupted attempts or missing usage,
no retries or owned-slot repairs. One missing-target `IS_FAN_OF` extraction
warning remains: completed projections do not certify complete semantic extraction.
Source/Store/vector and other fresh-cohort graph snapshots remained unchanged.

## Paired question

The question asks the number of MCU films watched in the last three months. Gold
is five. Both packed contexts contain and cite the **same** relevant original
owner statements: May 20 reports four; May 29 reports five. Full additionally
contains a derived five-film memory whose source is that same newer statement,
not a second independent witness. Both cover all two annotated turns/sessions.

| Metric | Full high-config | Raw vector + reranker |
| --- | ---: | ---: |
| Primary provisional task grade | Correct | Incorrect |
| Citation judge's separate correctness field | Correct | Correct |
| Annotated turns / sessions covered | 2/2 / 2/2 | 2/2 / 2/2 |
| Declared citation legality | Valid, three IDs | Valid, two IDs |
| Provisional support / quotes anchored | Supported / yes | Supported / yes |
| Context whole items / UTF-8 bytes | 20 / 17,884 | 20 / 19,880 |
| QA attempts / tokens | 5 / 39,231 | 3 / 13,814 |
| Graph path / exploration searches | 0 / 0 | Not configured |

Full chooses five as the newest self-report while also preserving four as an
alternative. Raw reports both counts and the newer five but refuses to adopt a
single definitive number. The primary judge rejects that commitment; the citation
judge accepts its disclosure of the expected value. This is not a retrieval miss
and does not establish a calibrated answer-accuracy advantage.

**This question did not use graph search.** The natural planner selected the
count branch. Full read the entire bounded scope, but returned aggregation status
`indeterminate`: relevance-qualified records do not prove an exact predicate/
episode count. No graph path or exploration ran; memory reranker was `not_run`,
path reranker `not_applicable` on the count branch. Separate raw-dialogue ordering
still uses the local CUDA scorer. Complete graph preparation was an eligibility
gate, not evidence that graph retrieval contributed to this answer.

Execution assessment is `completed_within_contract`, zero execution failures or
unclassified warnings, with an information notice against claiming exact counts
from relevance. That assesses execution, not arithmetic/semantic truth or release
acceptance. The Reader was not supplied a falsely certified count of five.

## Retained answer/temporal defects

- Full says the newer statement "explicitly corrected" the quantity. The cited
  newer original statement does not explicitly retract/correct the older one;
  greater quantity and later observation alone are insufficient proof of revision.
  This overstates source evidence, even though the main answer matches the gold.
- "Last three months" is a rolling interval anchored to each observation date.
  Four on May 20 and five on May 29 are not necessarily incompatible assertions
  over the same interval. Neither reader supplied episode dates to prove the
  exact June 17 question-time interval. They call it a conflict; the gold's latest
  self-report convention and epistemic interval precision are different issues.
- Raw's final refusal and `abstained=false` create interpretation ambiguity. It
  does supply both values, so the existing partial-answer policy does not make
  the flag automatically invalid. Retain the wording rather than invent a rule.
- Full is Chinese for an English question; raw follows English. Across three
  questions, five of six answers drifted to Chinese. Language compliance is
  distinct from provisional task correctness.
- Both provisional support grades are supported and quotes anchored, but these
  do not certify every narrative inference: the unsupported explicit-revision
  claim above is a non-independent manual observation, not silently regraded data.

No core/default/Reader/judge/config/sampling changes were made based on these
observations. Do not infer graph benefit from the full-profile label or duplicate
raw/derived citations. Do not sell provisional correctness as epistemic safety.

## Replay, accounting and integrity

The key-removed replay gives identical semantic rows, answers, contexts and all
grades/checks: six answer/judge cache hits, zero misses and zero new attempts.
Retrieval was checkpointed, not re-executed; original live profile receipts and
durable provider-call inventory remain unchanged. Final selected source journal,
Store, vectors and graph are unchanged while later source scopes ingest.

Subsequent scope 03 graph/schema/QA usage: **871 successful attempts / 3,644,946
tokens**, excluding its prior source ingestion. Settled first-three scope stages
including 149 source attempts: **2,657 attempts / 11,213,707 tokens**. The ongoing
350-attempt first-ten source block is not included until its receipt settles.
No retries, missing usage or reserved-history execution in these settled stages.

Local ignored receipt SHA-256:

- Graph: `89b5e5b393f1ce7c9695a57da0989262cfd27bc6ff037bb58fd2872b651f0d63`.
- Schema: `735f040523af8fd1152c926f85449215697818f661c9e12a9f82670eac74564d`.
- Paired QA: `2cded79122b4d68b8dd8f4ab3e941754753d03dc9239dba2fa003ee02fdbd5e9`.
- Empty-key paired replay:
  `195ddd3d90b69696f881318af76d28158df3da700e89ac09d67ba3f5478d28ad`.

## Three-question checkpoint, not a leaderboard

Fixed primary task grades: full **3/3**, raw **2/3**; all annotated turns/sessions
covered in both, all declared citations legal and judge quotes anchored. Full
execution: two `review_required` / one `completed_within_contract`. Primary vs
citation-judge task-correctness disagreement: one raw row. Zero independent or
official adjudications. No no-answer question has yet run, so no abstention-rate
quality conclusion. The selected fifty denominator remains fifty; 47 unscored
questions are not failures or successes and must not disappear from reporting.

Continue the original fixed order and unchanged protocol to the first ten pairs.
Keep all above observations and prior opened-vector-only results separate. The
offline adapter tests/Ruff remain clean; this round changes report plans/docs only,
not core code or the user's pre-existing `uv.lock`.
