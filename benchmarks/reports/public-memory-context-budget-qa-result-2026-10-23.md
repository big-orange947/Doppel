# Larger context improves annotation delivery, not net task accuracy here

All50 opened diagnostic cases completed at each fixed cap:150 logical rows.
Protocol/runner/test commit **14e3103**, pushed before freezing requests or making
new paid calls. Exact frozen plan fingerprint:
3ed39be15b2191cfc468e0620ccf2e9ac341c45985f827dd5a93013e35daba8c.
No question replacement, automatic retry, policy/model change, retrieval,
embedding/reranking, graph, database operation or source write. Original24KB
answers/grades are reused exactly, not regenerated or overwritten.

## Main paired result

Same candidate80/ordered top20, whole-source ranked-fit, unchanged ReaderV2 and
provisional DeepSeek task judge.24/48/96KB mean24000/48000/96000 UTF-8 JSON bytes.
Only the byte cap changes. These are already-opened development questions,
**not independent/official LongMemEval500, AML or full structured-Doppel results**.

| Cap | Correct / all50 | Answerable | Unanswerable | Paired gains / losses vs24KB | Mean actual context bytes |
|---|---:|---:|---:|---:|---:|
|24KB baseline|37/50 (74%)|30/43|7/7|0 / 0|23532.8|
|48KB|36/50 (72%)|29/43|7/7|1 / 2|40423.7|
|96KB|37/50 (74%)|30/43|7/7|1 / 1|41775.8|

All150 rows pass the unchanged structural citation/derivation checker. This
checks IDs/schema/declared inputs, **not semantic support, arithmetic, speaker
understanding, language compliance or epistemic safety**. No new support/safety
score is inferred. Neither enlarged cap has demonstrated net accuracy benefit
under the frozen task labels. One-case changes are not a statistical finding.

Positive-only type results (exclude all7 negative questions from these rows):

| Type |24KB|48KB|96KB|
|---|---:|---:|---:|
|knowledge update|7/7|7/7|7/7|
|owner facts|7/8|7/8|7/8|
|historical assistant|6/7|6/7|6/7|
|temporal reasoning|4/7|4/7|4/7|
|multi-session|4/7|4/7|4/7|
|preference / personalized advice|2/7|1/7|2/7|

The artifact's `by_type` includes negatives inside their public source categories;
for example temporal6/9 includes2 negative cases. The table above explicitly
filters `abstention_label=false`; it does not silently compare6/9 with4/7.

## Paired changes and important ambiguity

- **16, temporal gain at48/96KB:** the baseline computes0 days by choosing an
  earlier pedal-related statement. Enlarged contexts yield4 days using the later
  upgrade decision, matching the reference. The two enlarged requests are
  identical and share one answer/grade. This gain does not increase the aggregate
  temporal score because37 moves the other way under the frozen judge.
- **20, advice loss at48KB only:** all arms mention chain/cassette maintenance.
  The48KB answer leads with insufficient information to explain Sunday rides;
  the96KB answer adds the Garmin plan and cautiously supplies a possible cause.
  The provisional judge accepts24/96 but rejects48. The factual overlap and
  differently worded qualifications make this a reader/criterion-sensitive
  difference, not proof that48KB has intrinsically worse retrieval.
- **37, temporal loss at48/96KB:** both old and new answers actually identify
  the latest recorded dated trip as **train**, then qualify that no later trip
  records establish the state at the question date. The old answer leads with
  train and is accepted; the new answer leads with inability to determine and is
  rejected, despite explicitly giving the latest recorded train trip. This is
  **judge/answer-commitment ambiguity**, not a clean demonstrated loss of the
  answer evidence. Keep the frozen score; do not call it incontrovertible
  degradation, quietly relabel it or rerun judges until the desired label appears.
- **40 and44 remain incorrect:** extra wedding/museum evidence is delivered,
  but the Reader still fails to provide the reference count or full ordering.
  At96KB,40 lists at least4 weddings while the reference expects3, and refuses
  a definite count; the sources/events need correct temporal/event scoping, not
  just a longer list.44 still lacks the full six-museum sequence in top20.

These are text-based diagnostics, not independent human regrades. In particular,
the sensitivity at37 means no robust one-point ranking between caps is claimed.
English-question/Chinese-answer drift also remains visible (e.g.16/37); passing
structural checks must not be presented as solving language compliance.

The preceding zero-model curve had annotation delivery60/64/66 of76. Increased
delivery alone does not imply increased answer accuracy: some annotation-gain
questions were already correct, some remain incomplete, and the Reader may
decline an answer despite recognizing the right record. Historical37/50 remains
an immutable baseline, not a score to replace with a post-selected variant.

## Actual paid work, reuse and replay

- Reader58 new requests, judge56 new requests: **114 new calls**, all successful,
  zero retries/invalid outputs/missing usage. Both stages within58-call and byte
  limits. No new pipeline ingestion or model downloads.
-150 logical Reader rows:56 reference seeded baseline outputs,58 first new
  provider results,36 repeat new requests.150 logical judge rows:58 seeded
  baseline outputs,56 first new results,36 repeats. Reuse uses exact request
  hashes, never answer similarity or a favorable prior grade.
- Reader714124 input /12378 output /726502 total tokens.
- Judge27549 input /2601 output /30150 total tokens.
- Combined **741673 input /14979 output /756652 total**. Reported cached input
  461824, cache-miss input279849, reasoning0. This is observed provider usage,
  not an exact currency invoice, monetary cap or zero-cost claim for cached input.
- Canonical new-request bytes: Reader2825285, judge126123. These include
  instructions/schema/input; context-only bytes in the table are a different
  quantity. No fake byte-to-token conversion.

After live completion, clear the process key and run an independent cache-only
process against read-only parent caches, with the same frozen preflight and new
run directory. Reader58 and judge56 parent-cache hits, **0 new reservations**,
0 provider calls. All150 answers/grades/checks/identity/context digests and every
summary field match. Execution/cache/usage fields legitimately differ.

All7 pinned inputs and every runner/dependency code hash revalidate after both
runs. All50 baseline answers and grades match the original JSON values exactly.
No credentials or arbitrary provider-error text is written to reports/caches.

## Decision and next work

Do not promote48/96KB or candidate160 on these data. Retain current runtime
defaults; this is a resource comparison, not an algorithm improvement. It does
not establish that large contexts are generally harmful, or that24KB is globally
optimal. No additional judge-control/calibration loop or eager graph build is
needed to report this negative experiment honestly.

Stop spending on capacity variants for now. Remaining retrieval loss at80 is
4 annotations outside candidates and6 more outside top20. The next retrieval
experiment should target **generic multi-source evidence selection/order**, use
the existing frozen candidate receipts/sources, preserve owner/assistant/time
attribution, and retain a fixed budget plus downstream QA check. Do not repeat
failed metadata/MMR/LLM-selector arms as though untested; do not add question,
entity, role-quota or temporal-answer hardcoding. Reader/model-judge commitment
ambiguity remains a separate limit and must not be disguised as retrieval loss.

## Artifacts and verification

Ignored local files:

- Frozen preflight `data/doppel/context-budget-qa-frozen-v1.json`, SHA-256:
  9a88b8fb03bd2429a40f29ae3fb87bbd760f3d31aa13944f0f5292e8b0b341c8.
- Live `data/doppel/context-budget-qa-live-v1.json`, SHA-256:
  8f0a0f98e4af557508d7d2c443fc05427e756a09c4ff5632d2d2c98ae8c01453.
- Replay `data/doppel/context-budget-qa-replay-v1.json`, SHA-256:
  b7b551a9e8cb635f4440ae11381e74bbb84ac8a2f02038e24f20cdd3a70c9052.
- Live/replay directories retain immutable attempts,150 row checkpoints each,
  independent durable ledgers and provider caches (replay parents read-only).

8 new offline tests cover exact reuse, baseline immutability/conflict rejection,
request/gold/profile separation, paid usage, no-retry failure, new-output guards,
cache-only miss/no billing, independent replay and paired gains/losses.
Full suite **2287 passed,33 skipped,3 subtests**,233.48s; one existing optional
Graphiti/Pydantic deprecation warning. Ruff and touched-file formatting pass;
new runner Pyright0 errors/warnings. Existing uv.lock unchanged/unstaged.
