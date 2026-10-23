# Frozen downstream QA check of context capacity, opened50

Follow the zero-model budget curve, not another retrieval/model-selection study.
All50 previously opened diagnostic questions remain in ordinal order. Candidate80,
saved complete top20, whole-item ranked-fit, caps24000/48000/96000 UTF-8 JSON bytes.
No source repair, retrieval/reranking/embedding/graph, new corpus or role filter.
No question-specific exception or change after outcomes. All old files immutable.

## Fixed generation and scoring

Use exactly the previous ReaderV2 instructions/schema, full source objects and
reference dates. Validate every24KB Reader request against its old request hash.
Reader sees question/reference time/attributed context only, never reference
answer, annotation, prior answer/grade or profile name. Reader output2048 tokens.
Task judge sees only question/reference answer/candidate answer, not retrieval
context, budget/profile, prior grade or annotations. Judge output1024 tokens.
Both retain `deepseek-v4-flash`, `json_object`, thinking disabled, temperature0,
same endpoint/timeouts and provider configuration as the bound baseline prepares.
This is provisional local task accuracy, not official LongMemEval/AML scoring.

Keep all original24KB answers/grades, no baseline rescoring. Seed exact-request
reuse for all50 old Reader and judge outputs after schema/hash validation. An
enlarged context identical to24KB reuses that answer; a repeated48/96KB Reader
request reuses its answer. If question/reference/candidate answer are exactly
identical to a prior judge request, reuse that grade rather than introduce another
sample of judging noise. Different answers always have different judge requests.
Conflicting old outputs for one request identity fail closed before new calls.

58 unique new Reader requests maximum; judge58 maximum independently. Each stage
enforces durable reservation-before-send,100000 canonical request bytes/call,
5800000 total bytes, separate identity/caches/usage. Zero automatic retries.
Failures/invalid JSON remain recorded and stop the experiment; no substituted
question, relaxed schema, rebilling or quiet recovery. New run directory/output
required. Usage reports actual observed provider tokens; byte limits are not a
token or exact currency cap. Cached-only replay uses no real key and no network.

## Reporting and decision rule

Report all50 results and paired gains/losses vs24KB,43 positives/7 negatives,
question-type breakdown, structural citation/derivation checks, actual serialized
context bytes and paid usage/reuse counts. Grade correctness is not evidence
support; structural citation legality is not entailment. Preserve gains and
regressions equally. Report missing/failed rows explicitly, not as full50 results.

Budget expansion is a resource tradeoff, not same-budget algorithm improvement.
Opened development, no independent heldout result, no official score or release
gate. No automatic default promotion, even if a larger cap scores better on this
small known cohort. No preference/temporal/domain hardcoding or Reader tuning in
this run. Original37/50 remains its own baseline and is never overwritten.

## Execute

Commit this protocol/runner/tests before the live run, then freeze an exact
zero-call preflight including code/input/config/request hashes and current commit.
Do not change HEAD/config/code while paid execution is active.

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_memory_context_budget_qa --output data/doppel/context-budget-qa-frozen-v1.json
.\.venv\Scripts\python.exe -m benchmarks.public_memory_context_budget_qa --execute --frozen-preflight data/doppel/context-budget-qa-frozen-v1.json --run-dir data/doppel/context-budget-qa-live-v1 --output data/doppel/context-budget-qa-live-v1.json
```

Existing `DEEPSEEK_API_KEY` environment variable is used in-process, not stored.
No Docker or database needed. Exact inputs include pinned prior source, budget
curve, original50 QA, baseline prepare plans, manifest and dataset; original
Reader/judge configs are compared before any provider construction. Only50
diagnostic histories are prepared; reserved histories never enter execution.
After live execution, replay with `--cache-only --cache-parent <live-run-dir>`,
same frozen preflight, new run/output paths. Compare answers/grades/checks/summary,
allow execution/usage fields to differ; assert zero new reservations.
