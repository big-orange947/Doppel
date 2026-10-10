# Grounded Reader V2 control result: candidate rejected before paired QA

Frozen implementation `53c3ad0`, plan
`bf24641a28246c4c80ddaf7047e308e9448ce1b7dfa3743b972cfdedcf826cd1`.
Live report: `data/doppel/grounded-reader-v2-controls-live-v1.json`, SHA-256
`b4454044c324281ca3da4898a92166c8ff76fd558d8326cbe60e4a38ed49f183`.
Manual review: `data/doppel/grounded-reader-v2-controls-review-v1.json`, SHA-256
`25d9660bd231037dc2e51985ade5206cbf09de7bcdb56a79c8e838516acef127`.
Key-removed replay: `data/doppel/grounded-reader-v2-controls-replay-v1.json`, SHA-256
`0d385bc3b9a2d794c1209fa18f6e2466565a204354f510bfdeb4e7c2e025b306`.

## Gate and scope

18/18 control Reader outputs completed and passed structural checks. Semantic
review against the unchanged nine rubrics gives baseline **8/9**, candidate **7/9**.
The candidate must pass all nine: **gate false**. The paired-phase preflight was
explicitly checked and rejected before Reader/judge/DB calls or paired artifacts.
No LongMemEval answers were regenerated, no new task scores or retrieval scores,
and no default or core algorithm changed. Do not call this a successful fix.

This is manual inspection by Codex, **not independent human/model validation**.
All 18 decisions bind the live report's canonical hash and exact source/answer
quotations; the tool validates complete identities and quote anchoring, not the
semantic truth of the decisions. No rubric, instruction or expected result was
changed after the responses. Controls are synthetic development cases, not blind
validation, official LongMemEval or AML scores.

| Control / frozen content rubric | Baseline advice V1 | Candidate advice V2 |
| --- | --- | --- |
| 01 elapsed planned date is not completed collection | pass | pass |
| 02 generate new preparation advice without inventing prior course experience | pass | pass |
| 03 use explicit completion date, not planned date | pass | pass |
| 04 infer two disrupted sessions from linked outage descriptions | pass | pass |
| 05 do not infer causation from unrelated co-occurrence | pass | pass* |
| 06 subtract 7 from 28, cite input and record derivation | pass | pass |
| 07 preserve owner/assistant evidence authority | pass | pass |
| 08 correctly attribute earlier assistant advice, answer in Chinese | **fail** | **fail** |
| 09 answer an English question in English despite a Chinese source | pass | **fail** |

Rows 01–07's frozen rubrics concern content; their pass does not certify global
language/abstention compliance. Separate issues are reported below rather than
retroactively rewriting those rubrics or converting failures into passes.

## Actual defects and unchanged working behavior

### Speaker inversion (both policies)

Control 08 source is assistant-role, agent_output: `I suggested trying rowing on a
stationary machine.` Owner asks what the assistant previously suggested to them.
Both answers instead say `你上次建议我尝试划船机` — **you suggested to me**, reversing
the speaker/recipient. The exercise value and citation ID are correct, but source
role and first/second person are not preserved. Structural legality misses this.

### Language drift (candidate regression included)

Control 09 asks `Which colour of notebook do I prefer?` with owner source
`我更喜欢蓝色封面的笔记本。`. Baseline says `You prefer blue-covered notebooks` with a
source-language parenthesis. Candidate says `你更喜欢蓝色封面的笔记本。`, violating the
English-answer rubric. This is a regression, not a tokenization or retrieval error.

In separate manual language inspection, baseline answers questions 01–05 and 07
in Chinese despite English questions; candidate also does this in 09. Baseline
question-language consistency is **3/9**, candidate **2/9** (08's language is right
but speaker direction is wrong). These counts are manual, not an automatic language
classifier or independent benchmark. Repeating the language instruction in a longer
system prompt did not solve this observed behavior. Request inputs were checked:
the question strings are unchanged; the transport appends JSON schema instructions
but does not insert a Chinese-language rule. Cause beyond this has not been proven.

### Abstention consistency (candidate)

*Control 05 candidate says `无法确定你错过的音乐课是否由公交中断导致` and explains no
causal link, but sets `abstained=false`. It does not supply the requested causal
result. Baseline sets true. Record this separate semantic flag inconsistency; the
content rubric only requires not inventing causation, so its content pass remains.

Both policies correctly treat the elapsed collection plan as an unproven action,
use later explicit collection evidence, support direct inference and arithmetic,
and avoid turning an assistant assertion into an owner submission fact. Candidate
02 explicitly presents its preparation steps as new advice, not past behavior.
There is **no demonstrated uplift** over the baseline on these content controls;
this cannot establish that the opened preference answer's overstatement is fixed.

## Accounting and verification

- 18 new Reader calls, all successful; 0 judge calls, retries, interrupted or
  structurally invalid outputs. All usage receipts complete.
- 27,129 input + 2,205 output = **29,334 tokens**; input comprises 5,369 provider
  cache-miss and 21,760 provider cache-hit tokens; 0 reported reasoning tokens.
- Immediate balance 5.10 → 5.10 CNY, not proof of free calls or an exclusive invoice.
  The earlier account observation belongs to another time/run; no attribution to
  this run is made from it. No hard currency cap claimed; attempt cap respected.
- Second child process with key removed: 18 local hits, 0 misses/new reservations,
  identical rows and plan. Provider cache hits live are distinct from local replay.
- **1,658 passed, 33 skipped, 3 subtests passed** in full regression; one existing
  Graphiti/Pydantic deprecation warning. 17 new tests; 52 directed tests. Whole-repo
  Ruff, new-file formatting and Pyright pass.
- `uv.lock` remains unstaged. No old answers/scores/cache/database/journal/index
  changes. No GPU or Docker work. API keys remain environment-only.

## Next development direction

Do not promote candidate V2 or spend the gated 28 Reader + 28 judge allowance.
Preserve the failed result and controls unchanged. Before another paid comparison,
prepare a **generic explicit output contract** for the reference Reader: host-owned
answer language and a clearly stated current respondent/audience/historical-source
speaker frame. An earlier assistant is not automatically the current assistant;
where identity is unavailable, report attribution explicitly rather than inventing
identity or copying the question's pronouns into an answer.

This belongs to the opt-in reference Reader/evaluation integration, not an expansion
of Doppel into an agent context manager or an automatic core default. No domain
keywords, dataset IDs, forced expected answers, role-string post-editing or output
translation masquerading as a successful original answer. Freeze new input-contract
changes and budgets separately; keep baseline/candidate inputs equal, then test the
same unchanged controls. Inspect abstention text separately from structural checks.

The failed language/speaker controls do not demonstrate a retrieval deficiency;
the correct source was supplied. Lazy/eager graph comparison remains later,
competition-only work and is not triggered by this control run.
