# Locked reserved10: 9/10 provisional task correct, no retuning

All10 original `reserved-not-run` histories completed under the previously selected
single fusion profile. Runner/protocol/tests af8bb5a committed and pushed before
first preflight. A startup-only Windows path normalization fix84dd82c was committed
before any ingestion, retrieval or inference. The initial preflights failed while
looking up a slash-separated code key in a backslash-keyed Windows receipt; no
schema/model/paid work occurred then. No ranking, prompt, source cohort or policy
change followed reserved model outcomes. No case replacement or retry.

## Primary QA result

| Group | Correct | Denominator | Rate |
|---|---:|---:|---:|
|All reserved questions|9|10|90.0%|
|Answerable only|8|9|88.9%|
|Predeclared negative|1|1|100%|

This is a small reserved-from-this-development-cycle validation, not proof of
general90% accuracy, independently audited/model-unseen blindness, official
LongMemEval500, AML scoring/compliance or publication readiness. One case changes
the total by10 percentage points. Public benchmark/model training exposure and
the provisional same-provider Reader/judge remain limitations. Do not pool these
results with the previously opened50 or call40/50→9/10 a causal improvement.

Positive-only types and per-case outcomes:

| Ordinal | Case ID | Type | Primary grade |
|---|---|---|---|
|1|a3045048|temporal reasoning|correct|
|2|4b24c848|knowledge update|correct|
|3|65240037|historical assistant|correct|
|4|a96c20ee|multi-session|correct|
|5|35a27287|preference/advice|incorrect|
|6|ba358f49_abs|predeclared negative|correct refusal|
|7|7527f7e2|owner fact|correct|
|8|gpt4_1d4ab0c9|temporal reasoning|correct|
|9|e493bb7c|knowledge update|correct|
|10|6222b6eb|historical assistant|correct|

Thus temporal2/2, knowledge update2/2, historical assistant2/2, multi-session1/1,
owner fact1/1, preference/advice0/1, negative1/1. These one/two-case cells are
diagnostic descriptions, not stable category estimates. Case6 retains its public
multi-session category but is excluded from the positive multi-session1/1 row.

All10 citation-ID/declared-derivation structural checks pass. This does not verify
entailment, arithmetic, actor interpretation, language, calibrated abstention or
factual safety. No support/safety/complete-event-count score is inferred.

## Fixed pipeline, full histories, no graph authoring

- Exactly5048 original raw messages/506 transport chunks, ten disjoint case scopes.
  Original text, roles, observed times/session order and question reference times
  preserved and matched against the original frozen payload/group fingerprints.
- Dedicated new namespace `longmemeval-reserved10-final-fusion-v1`, PostgreSQL
  schema **`reserved_final_c8ad8b7dba13`**. No old schema/data reset or deletion.
- Same declared local symmetric BGE-small-zh/fastembed0.8.0/512/cache profile;
  same frozen BGE-reranker-v2-m3 artifact/runtime6.0.1, CUDA batch1/max8192.
- Same BM25/vector equal-RRF60 candidate80, full BGE order fused with retrieval
  order by equal RRF60, final20, ranked-fit24000 UTF-8 JSON bytes. No metadata/
  role/length/date quotas, planner special cases or source expansion.
- Same ReaderV2/task judge, DeepSeek-v4-flash/json_object/thinking disabled/
  temperature0,2048/1024 output caps. No reserved-outcome model or prompt change.

Preparation:10 local BGE calls/800 pairs, `cuda:0`,0 truncated pairs, longest2682
tokens; no LLM extraction/analyzer, Graphiti or paid calls.800 candidate-source
checks and200 final Store checks, no rejections. Full original corpus/vector
fingerprints validate before/after every query. All5048 vectors match current
source scope/version/fingerprint. Complete80 candidate objects and neural/fusion
orders are retained; top20/context source objects remain unchanged originals.
All contexts fit24KB; total actual serialized contexts234321 bytes.

After ordering/packing, annotation delivery is **15/16 (93.8%)** at both top20 and
packed stages across9 positives. Eight of9 positives retain all annotations.
This is original-turn annotation coverage, not semantic sufficiency or QA score.

## The one failure: personalization still has two distinct limits

Case5 asks for interesting cultural events nearby this weekend; the reference
expects advice shaped by Spanish/French practice and cultural/language-learning
interests. The context contains language exchange, a cultural festival and
previous assistant suggestions for finding events, but no concrete dated local
weekend listings. The Reader refuses specific recommendations and summarizes
those historical clues/platforms instead. The frozen task judge marks it wrong.

Only2/3 annotated original turns are delivered. A post-run immutable source-event
mapping verifies positions(40,2)/(40,12) in candidate80/top20/context, while
**(40,4) is already absent from candidate80**, not dropped by fusion or byte cap.
All other annotations are retained, so candidate/top20/packed coverage is15/16.
This audit happens after execution and is not a new retrieval experiment.

There is both an upstream evidence gap and an answer-policy mismatch. Existing
context already supplies useful language/cultural clues, but neither causal
blame nor the counterfactual success from one missing turn is established.
Refusing to invent current event listings is not itself unsafe; a personal Agent
can combine remembered preferences with fresh event search, clearly separating
new recommendations from stored facts. This run did not add such Agent behavior
to the memory framework, relabel the failed answer or tune on reserved data.

## Paid usage, immutable replay and source checks

- Reader10 calls,73309 input/2331 output/**75640 total tokens**.
- Judge10 calls,4948 input/425 output/**5373 total tokens**.
- Total **20 calls,78257 input/2756 output/81013 total tokens**, cached input11392,
  cache-miss66865, reasoning0. Complete usage20/20, no failure/retry/repair;
  separate10/10 attempt caps and byte budgets respected. No unreported extension
  of the earlier opened50 recovery budget. Tokens are not an exact money invoice.
- Answers reopen only this new schema with server-read-only transactions. Current
  corpus and every supplied original source object validate before generation,
  and the complete corpus matches again after each answer.
- A separate process with the real key removed replays against read-only success
  caches: Reader10/judge10 hits, **0 new reservations/provider calls**. All10
  outputs/grades/checks/identities/context digests and summary match exactly.
- All five pinned input files, runtime code hashes, preflight binding and per-case
  context/answer checkpoints revalidate. Old schemas/reports/caches remain intact.
  Source/schema retained for reproduction, no destructive cleanup.

## Reproduction artifacts and checks

Frozen/live code HEAD84dd82c; no code/HEAD changes between context preparation,
paid QA and replay. Local ignored artifacts under `data/doppel/`:

| File | SHA-256 |
|---|---|
|reserved10-prepare-frozen-v1.json|1cb5b63354ac4333b3c6321c9fccd8609a5b693da2bff31b200c573c7dd4142e|
|reserved10-prepare-live-v1.json|2e84b1b6bcfcb25dda325860de81936dd8d71c7a2baec19de16c9d642f377ec8|
|reserved10-answers-frozen-v1.json|f2e71dad39ddf51d34dfd772d8a5afc9955c10d9ea91452b6ef541cf0a7d323f|
|reserved10-answers-live-v1.json|10b85c2aa6c4f9bbe1ec2fdf0c7a11cd76a738c57c1bb120971ad2655672ba98|
|reserved10-replay-v1.json|adedcf0f801491bf3c4d3dd8a31f9f5055cdbafbc910491393b72dde7315b45d|

Preparation fingerprint66d9a996c39e85bb9c45c78cbac7972315b34e96ccc393e2d16597b3a1da9a14;
answer fingerprintb9488360a039a877350e32efa95a4c88ddc2d9cae8468019f17c054146ad5031.
Run directories retain attempts,10 contexts,10 answers, provider caches and
durable call ledgers; no credentials persisted. Existing schema/run paths are
refused, never overwritten. The Windows key fix changed startup path lookup only,
before any model outcomes; both slash styles and ambiguous keys now have tests.

Full suite collected before that path fix: **2338 passed,33 skipped,3 subtests**,
347.98s, one existing optional Graphiti/Pydantic warning. After the fix, all17
targeted reserved-runner tests pass (13 original+4 path checks), Ruff/format and
runner Pyright pass0 errors/warnings, plus the complete live/replay pipeline above.
Do not misreport this as a new full2342-test run. Concurrent testing/embedding
means these durations are not production search p50/p95 or idle-GPU latency.
Preexisting uv.lock1025 additions/1025 deletions remains untouched/unstaged.

## Decision: stop quality tuning, move to integration acceptance

Retain the locked fusion evaluation configuration; do not tune k/top-k/Reader/
embedding on these now-opened ten or replace the one failed case. Opened50 remains
40/50 under fusion (baseline37/50), reserved10 is separately9/10. No combined
independent60-question score. This is encouraging limited transfer evidence,
not proof of a universal best configuration.

Next work is an explicit service preset/option for this frozen fusion policy,
with matching configuration identity, followed by real Add→Search/attribution/
scope/idempotence/restart acceptance. The existing service has not automatically
adopted the new optional ranker, and this result is not a public deployment.
Leave full eager graph authoring and new ranking experiments paused. Product
structured memory/Graphiti capabilities were not removed; this run validates the
selected economical raw-history profile, not every Doppel subsystem.
