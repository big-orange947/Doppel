# Final opened50 selection: fusion40/50 vs BGE37/50

All100 logical rows complete: same50 opened questions, BGE and fixed equal RRF60
fusion at80 candidates/top20/24000 UTF-8 JSON bytes. Original BGE answers/grades
remain immutable. Protocol/runner/tests2047aa9 committed and pushed before live
calls. One user-approved recovery supplement b3d88b7 was frozen/pushed before
recovery calls; model/prompts/requests/decision never changed.

## Primary result and predeclared decision

| Profile | Correct /50 | Answerable /43 | Unanswerable /7 | Structurally valid |
|---|---:|---:|---:|---:|
|BGE baseline|37 (74%)|30 (69.8%)|7|50/50|
|fixed RRF60 fusion|40 (80%)|33 (76.7%)|7|50/50|

Paired **4 gains/1 loss, net+3/50**. The frozen engineering rule requires net+3,
no negative-case decline and no structural-check decline. It therefore selects
**fusion for the next reserved-data evaluation**, with no change to k/weights,
source/item/byte limits, embedding, BGE, Reader or provisional task judge.
This threshold is not a significance test, and the gain is not an independently
verified general80% memory accuracy. No automatic package/service-default change.

Positive-only breakdown (exclude negative cases, including those inside public
temporal/multi-session categories):

| Type | BGE | Fusion |
|---|---:|---:|
|knowledge update|7/7|6/7|
|owner facts|7/8|7/8|
|historical assistant|6/7|7/7|
|temporal reasoning|4/7|5/7|
|multi-session|4/7|6/7|
|preference / personalized advice|2/7|2/7|

Gains:16 temporal (4-day interval),19 multi-session (3 faith-activity days),25
historical assistant (fruit-based snapper recommendation),33 multi-session
(12-minute difference). Loss:38 knowledge update (living duration). No other
question changes primary correctness. Do not hide the knowledge-update regression
or call preference/advice solved. No new question-type or entity rules were added.

At38 both answers actually cite the same conflicting one-month/three-month
statements. BGE gives the latest reported three months with a conflict caveat;
fusion reports the conflict but declines to choose a definite duration. It also
sets `abstained=false` despite declining a definite duration, and answers an
English question in Chinese. This points to Reader commitment/flag/language
limits, not absence of the two duration facts or a proved retrieval failure.
Keep the frozen false grade; no regrading/prompt loop to erase the regression.

Structural checks validate citation IDs/schema/declared derivation inputs, not
arithmetic, semantic support, language compliance, answer commitment or safety.
The judge is the same provisional DeepSeek model, not official GPT-4o scoring or
independent human adjudication. These are all previously opened development
questions, not a new100-question set, official LongMemEval500, AML or release gate.
Candidate evidence retention is still68/76 top20 and62/76 packed, measured in
the preceding local run; it must not be confused with the40/50 task score.

## Failure and one explicitly authorized recovery

Original run stops at3/fusion Reader after HTTP200/stop but invalid content JSON:
Reader3 attempts (2 succeeded/1 failed), judge2 succeeded. No automatic retry,
repair or substituted case. Original failed report/checkpoints/ledger remain.
The user then explicitly authorizes one bounded recovery, Reader cumulative51
instead of50, judge cumulative50 unchanged. New identity subtracts original
reservations, so recovery caps48 Reader/48 judge. Shared Reader/judge dependency
hashes, requests/config and selection rule stay identical. The changed runner
code only implements the recovery orchestration; no failed response is relabelled.

Recovery completes with48 Reader/47 judge new successes,2 parent-cache hits in
each stage, no second failure/retry. Across both identities:

- **Reader51 attempts:50 succeeded/1 failed**; judge49 succeeded, below50 cap.
- **100 total attempts**, including the paid invalid-JSON response. No budget
  refund/reset or exclusion of failed-response usage.
- Reader375359 input /11590 output /386949 total tokens.
- Judge24491 input /2331 output /26822 total tokens.
- Combined **399850 input /13921 output /413771 total tokens**, reported cached
  input77696/cache-miss322154, complete usage for100/100 attempts. These are
  observed tokens, not an exact currency invoice or hard token/currency cap.

Cache-only replay in a new process with the real key removed reads the recovery
and original success caches as read-only parents. Reader50/judge49 hits,
**0 new reservations/calls**. All100 answer/grade/check/identity/context rows and
the complete summary/selection are identical. Baseline50 answers/grades match
the original JSON values exactly. All input/code hashes and recovery checkpoints
revalidate; original failure SHA remains unchanged. No DB/retrieval/GPU/embedding/
graph/source writes in this QA step.

## Selection lock and next stage

Stop ranking/weight/context tuning on these opened50. The selected evaluation
profile is now BM25/vector RRF60→BGE plus equal rank fusion60→top20→whole-item
ranked-fit24KB→unchanged ReaderV2/task judge. Product/runtime defaults remain
unchanged until separate integration validation.

The next stage is the original manifest's10 `reserved-not-run` histories under
this one locked profile, not another candidate comparison. Only case IDs/counts/
strata were inspected while recording the plan; no reserved RuntimeCase/history,
retrieval, answer or grade has been prepared/executed in this round. See the
[reserved10 pre-registration](public-memory-reserved10-final-plan-2026-10-23.md).
Reserved results must remain separate from opened50 and cannot trigger tuning.

## Artifacts and tests

Ignored local artifacts, SHA-256:

- Original preflight `rank-fusion-qa-frozen-v1.json`:
  864474da9ed37c8688155571ac956dfc8f0f161c6d428673d48c44f8d3d467ed.
- Original failed `rank-fusion-qa-live-v1.json`:
  bf7abffe0e9b79c2522568c5d31c5d1b584059c07fda078046d4061c7d380aeb.
- Recovery preflight `rank-fusion-qa-recovery-frozen-v1.json`:
  69a9498d3ec021abd65bb868f3a19708d304ac59afb776cc4daf6ee49ebb0b61.
- Recovery result `rank-fusion-qa-recovery-v1.json`:
  24a8bf0c56d421d969c91c0d5eaaa85278e7e48a874d45fbc2ba8cbadd420991.
- Cache replay `rank-fusion-qa-replay-v1.json`:
  ca9df5882fd335b0e159e0e83d2690fcf7d3b4c2f9a68cd1f198c8bd00fb898c.

All under `data/doppel/`; associated run directories preserve immutable attempt,
row, provider-cache and SQLite-ledger records. Recovery fingerprint:
562e2d451117a6ff84127378dc54b753a4e81e900cc47c9555f589bd65eb6863.

11 new offline tests cover exact baseline/gold separation/replay, no-retry stop,
fixed selection threshold/guards and cumulative recovery accounting. During
initial test development a factory patched in the wrong module led to2 requests
with synthetic invalid credentials (HTTP401, no real key). Corrected before
live execution; an automatic fake-provider injection guard now prevents this.
Those unauthenticated test requests are not successful evaluation/model calls or
real-account paid usage, and are not hidden in the live ledger totals above.

Final post-recovery-code full suite **2325 passed,33 skipped,3 subtests**,255.61s;
one existing optional Graphiti/Pydantic deprecation warning. Ruff/format pass,
runner Pyright0 errors/warnings. uv.lock remains the preexisting unstaged change.
