# Uniform logical50-question baseline:37/50 (74%)

## What is complete

All50 fixed diagnostic LongMemEval S histories now have answers under one logical
affordable configuration: raw-only production BM25/vector RRF60 candidate80,
local BGE-reranker-v2-m3 top20, whole-message ranked-fit24000 UTF-8 JSON bytes,
unchanged Reader v2 and provisional DeepSeek task judge. Original30 result22/30
is unchanged; fixed complement01–10/41–50 scores15/20. Aggregate **37/50 (74%)**.

There are43 answerable questions:30/43 (69.8%). Seven unanswerable variants all
abstain correctly:7/7. Negatives are not mixed into positive ability percentages.
No question replaced, old grade revised or best historical arm substituted.

This is **opened, stratified development data**, not independent/model-unseen
validation, official LongMemEval500, AML, release acceptance or highest-config
Doppel. No full temporal Planner, extracted-memory/Graphiti path, persona/style
or LLM-selector configuration is being measured. Do not interpret74% as the
framework's performance ceiling, or historical37 different successes as a new
independent sample. Ten reserved histories remain closed.

## Positive-only abilities

| Task | Correct / questions | Provisional accuracy |
|---|---:|---:|
|knowledge update|7/7|100%|
|user fact|7/8|87.5%|
|historical assistant information|6/7|85.7%|
|temporal reasoning|4/7|57.1%|
|multi-session synthesis/count/inference|4/7|57.1%|
|personalized preference/advice|2/7|28.6%|
|all answerable|30/43|69.8%|
|unanswerable variants, separate|7/7|100%|
|all questions|37/50|74%|

Only7–8 items per positive type: no reliable population accuracy or leaderboard
comparison follows. The negative7/7 is not a privacy/security certificate and
must not disguise lower positive task success.

## Evidence delivery over the same50

Across43 positive questions,76 annotated raw turns:

| Stage | Hits / annotated turns | Coverage |
|---|---:|---:|
|candidate window80|72/76|94.7%|
|returned top20 after local reranking|66/76|86.8%|
|final24KB whole-message context|60/76|78.9%|
|questions retaining every annotated turn after packing|36/43|83.7%|

This replaces neither the older30-question41/42@20 result nor its26/27 vs10/15
packing distribution; the expanded denominator exposes harder delivery failures.
Annotation recall is not precision, fragment entailment or QA accuracy. Case05
answers correctly despite missing one annotated turn using an alternate original
vegan-class statement. Cases20/37 also succeed without complete annotation
coverage. Source annotations are useful diagnostics, not exhaustive proof of
what can/cannot be answered.

Candidate omissions include two labelled museum turns in44, the granite owner
statement in48, and one cooking-class turn in05. Case41's two preference turns
are in candidate80 but neither reaches top20. Case44 then loses more turns in
ranking/packing. The wedding-count case40 also loses owner attendance evidence
across source ordering and byte packing. More sources are not automatically a
fix for the observed candidate-to-context losses.

## All failures retained

| Ordinal | Task | Full annotation set in final context? | Observed limitation |
|---|---|---|---|
|02|temporal|yes|refuses approximate order between a trip years ago and last summer|
|06|personalized advice|yes|requires an old buying checklist instead of offering new guidance|
|13|personalized advice|yes|requires prior explicit publication recommendations instead of using interests|
|16|temporal|yes|uses earlier consideration as a later decision date|
|19|multi-session|yes|excludes church food drive; primary2 vs reference3, conditional-answer sensitivity|
|25|assistant recall|yes|rejects Jamaican qualifier for generally Caribbean mango-salsa dish|
|33|multi-session|yes|refuses to connect target/actual marathon times and derive12 minutes|
|34|personalized advice|yes|requires an old recommendation for this precise gathering|
|36|user fact|yes|refuses contextual Target/coupon link expected by reference|
|40|multi-session|no|no labelled wedding-attendance turn survives context|
|41|personalized advice|no|preference turns dropped by source ranking|
|44|temporal|no|multi-stage museum evidence omission; partial assistant mentions not full sequence|
|48|personalized advice|no|granite owner evidence missing, plus advice refusal|

Nine of thirteen failures retain every annotated turn. Direct question/answer/
original-text inspection supports answer-task use, intention-vs-decision and
cross-record inference conservatism as important issues; not every such refusal
is necessarily unreasonable. Cases19/25/36 have interpretation/qualifier ambiguity
against the reference. Keep grades unchanged and caveats visible, not an excuse
to relax plan/fact, actor/subject or source authorization boundaries.

The new02 answer also drifts to Chinese for an English question. Primary task
accuracy does not independently grade language compliance. Cited IDs and declared
derivation references are legal in50/50 outputs, but semantic support/entailment
was not independently certified. No post-hoc judge-control campaign or Reader
prompt tuning was performed. Prior [thirty-question source inspections](public-memory-uniform-qa-result-2026-10-18.md)
remain applicable and unchanged.

## Completion execution and actual cost

First10 sources coexist with derived memories in their old schema. An evaluation
RawOnlyStore SQL filter restricts extractor=ingestor before lexical IDF and vector
LIMIT; full authoritative inventories remain separately hash-checked. Derived
EVENT records cannot consume raw candidate80. Other schemas are already raw-only.
This aligns the logical channel, not the physical schemas/ANN corpus layout.
No DB/view creation or mutation; scopes/roles are not remapped or filtered by task.

For41–45, reuse saved original80 pools; for46–50 reuse the first80 *preserved
original anchors* from neighborhood receipts, not a wider nativeN prefix. BGE
identity matches prior30 exactly. Local preparation:20 rerank operations/1600
pairs, zero token truncation, longest4107 under8192; at most10 query embeddings.
Every authorized pool has80 candidates and every source ranking returns20.
All per-row source rejection maps empty, and full-corpus snapshots unchanged.

New20 QA uses40 successful calls/160347 tokens:

| Scope / stage | Calls | Input tokens | Output tokens | Total |
|---|---:|---:|---:|---:|
|new20 Reader|20|144290|4761|149051|
|new20 judge|20|10344|952|11296|
|all50 Reader|50|360522|10795|371317|
|all50 judge|50|24746|2397|27143|
|all50 total|100|385268|13192|398460|

Complete provider usage100/100, zero failed/interrupted attempts, retries or
output repair; all per-stage attempt/byte caps respected. All50 QA averages
7969.2 reported tokens/question including scoring, excluding sunk ingestion,
embedding/local reranking and all historical graph/debug experiment spend.
These are not the entire project's accumulated bill, from-zero deployment cost
or a currency invoice. Earlier failed/expensive runs remain preserved, not erased
or reassigned to this budget. No stable idle-GPU p50/p95 measurement is claimed.

## Artifact and implementation bindings

- Code/protocol35c5b5a and actual-request supplement28ed092 pushed before paid
  calls. See [frozen completion plan](public-memory-uniform-completion-plan-2026-10-18.md).
- Completion preparation SHA256:
  `bc85ac1307dc83c738ddf00246319354b07eac8ba746c51bbbce1275c1b3f499`.
- Completion answer-plan fingerprint:
  `a4644f165d1241e97b58f804a14b30c4aad74655564b9d28cf48057ae4a3a224`.
- `data/doppel/uniform-qa-completion-answers-live-v1.json`, SHA256
  `1bb8a5c23cf4a888eb0f87ccd0a3e343c1c97c0a92de4818caeb5ee38f407c1e`.
- **Combined** `data/doppel/uniform-qa-fifty-summary-v1.json`, SHA256
  `a5ecbc7c038a072eb69e73d5024fd53f3ec92800a5aec8c1bbeedd95c7ad8408`.
- `data/doppel/uniform-qa-completion-v1/`: source pools, contexts,20 answers,
  per-stage cache/durable ledger; ignored and not committed. Original30 artifacts
  stay unchanged. Keys environment-only; never included in source/reports.
- Key-free separate-process **aggregate-only** replay produces byte-identical
  `uniform-qa-fifty-summary-replay-v1.json` with the same combined SHA256 and zero
  provider calls. This rechecks summary bindings, not retrieval/Reader/judge or
  independent correctness; no end-to-end QA replay is claimed.
-11 new offline tests pass: fixed complement, pre-cap raw SQL predicate,
  mixed-source attribution/fake-provider gold separation, aggregate model/profile/
  duplicate/missing guards. Full2089 passed/33 skipped/three subtests passed in
  248.30s, existing optional Graphiti/Pydantic warning only. Ruff/format pass;
  new runner Pyright zero errors. User uv.lock modification left unstaged.

## Decision

There is now a reproducible affordable development baseline, not evidence that
the framework is excellent end-to-end. Fact/update recall looks promising on
these few cases; personalized advice is weak and temporal/multi-session inference
and budgeted source delivery need work. Do not promote another graph source or
unbounded whole-pool LLM selector based only on this score.

Keep the50 result frozen. Next separate general evidence-delivery improvements
(missing candidate/source/span selection) from reference Reader task behavior
(new suggestions vs historical facts, approximate time, defensible inference).
Any new suggestion must be labelled and must not become an owner fact or completed
plan. Those answer policies belong to the reference/application layer, not an
implicit core memory gate. Test new configurations separately without question,
entity or category-specific rules; only use reserved histories after configuration
is fixed. Do not change embedding, retrieval and Reader simultaneously or tune
to these13 reference labels. Keep Graphiti authoring paused.
