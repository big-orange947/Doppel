# Thirty-question uniform affordable baseline:22/30, not a mixed50 score

## Result and population

All fixed ordinals11–40 now have final answers under the same frozen saved
BM25/vector/BGE top20 + whole-message24KB ranked-fit + Reader v2 + DeepSeek task
judge. **22/30 correct (73.3%)**; positives18/26 (69.2%); negatives4/4. Finish
previously-unanswered27 first:20/27; then opened32/37/40:2/3. No failed requests,
retries, questions replaced, labels changed, or model/policy tuning after results.

This is an opened development diagnostic, not independent validation, official
LongMemEval/AML, or Doppel's highest configuration. It measures retrieval-to-answer
composition, not a standalone framework-wide score. All50 distinct histories in
the parent now have at least one scored answer across different experiments;
only these30 have this exact uniform baseline. The other20 need the same baseline
before a current uniform50-item aggregate exists. Ten reserved histories remain
untouched. Do not add each prior experiment's best arm to these30.

## Ability breakdown

Positive-only types below deliberately exclude the4 predeclared unanswerable
variants, unlike the raw report's original-category facet which retains them.
Category counts are too small to establish reliable population performance.

| Positive task type | Correct / total | Accuracy |
|---|---:|---:|
|knowledge update|4/4|100%|
|historical assistant information|4/5|80%|
|user fact|3/4|75%|
|temporal reasoning|3/4|75%|
|personalized preference/advice|2/4|50%|
|multi-session synthesis/count/inference|2/5|40%|
|all positive|18/26|69.2%|
|unanswerable variants, separate|4/4|100%|

There are26 positive questions/42 annotated turns. Frozen source diagnostics
have42/42 in candidate80,41/42 in returned20, and36/42 in24KB packed contexts;
23/26 questions retain all annotated turns after packing. Those are historical
development evidence measurements, not answer accuracy or current LLM selection
performance. The first20 and next10 packed coverage remains26/27 and10/15,
respectively; aggregate coverage hides this distribution shift.

## Every row, no best-of selection

| Ordinal | Case | Provisional task grade | Negative |
|---|---|---|---|
|11|4c36ccef|correct|no|
|12|00ca467f|correct|no|
|13|75832dbd|incorrect|no|
|14|gpt4_c27434e8_abs|correct|yes|
|15|29f2956b|correct|no|
|16|gpt4_e414231e|incorrect|no|
|17|945e3d21|correct|no|
|18|b759caee|correct|no|
|19|5a7937c8|incorrect|no|
|20|1d4e3b97|correct|no|
|21|6456829e_abs|correct|yes|
|22|c14c00dd|correct|no|
|23|gpt4_f49edff3|correct|no|
|24|26bdc477|correct|no|
|25|778164c6|incorrect|no|
|26|4f54b7c9|correct|no|
|27|8a2466db|correct|no|
|28|gpt4_70e84552_abs|correct|yes|
|29|a82c026e|correct|no|
|30|gpt4_b5700ca0|correct|no|
|31|89941a93|correct|no|
|32|e9327a54|correct|no|
|33|a346bb18|incorrect|no|
|34|d24813b1|incorrect|no|
|35|edced276_abs|correct|yes|
|36|51a45a95|incorrect|no|
|37|gpt4_ec93e27f|correct|no|
|38|2133c1b5|correct|no|
|39|8752c811|correct|no|
|40|gpt4_2f8be40d|incorrect|no|

## Failure observations from actual source text

Seven of eight failed rows retain all their annotated turns. That is not an
entailment certificate, but prevents attributing every failure to missed retrieval.
Direct comparison of the saved question, answer, reference and cited originals:

-13,34: individualized advice request is treated as recalling a past explicit
  recommendation for this precise occasion. Relevant user interests/previous
  baking success are present. Reader refuses instead of using them as context
  for a new clearly-labelled suggestion. This is answer-task use, not a measured
  absence of preference evidence.
-16: original March15 text says the user is *thinking* of upgrading pedals;
  March19 text says they decided *today*. Mountain-bike repair is March15. Reader
  uses the earlier consideration as the decision and answers0 instead of4 days.
  Both dated owner records are present: intention/decision semantics, not missing
  timestamps or a need for another graph, explains this observed failure.
-19: Reader excludes a church food drive from faith-related activities, answers2
  primarily, and mentions3 conditionally. Reference expects3; primary judge keeps
  it incorrect. Category boundary and qualified-answer grading are sensitive;
  no secondary adjudication or corrected label is claimed.
-25: the expected mango-salsa snapper dish appears in the supplied old assistant
  list. Reader rejects the question's Jamaican qualifier because it was described
  as generally Caribbean, whereas the explicitly Jamaican first-choice dish was
  escovitch. This is qualifier/premise handling versus the reference, not a
  missing dish name. The answer's factual caution may be defensible; do not relax
  framework safety or relabel the task grade merely for this example.
-33: target4h10 and completed marathon4h22 both appear. Reader refuses to connect
  them without an explicit event identity, rather than deriving12 minutes. This
  is cross-record inference conservatism; it does not license arbitrary event
  merging or mandate a benchmark-specific counting rule.
-36: coupon redemption and frequent Target/Cartwheel shopping occur in the same
  session. Reader refuses the implicit store link and reference expects Target.
  Contextual inference/premise ambiguity is visible; it is not proof of a broken
  vector search or justification to infer all nearby claims are one fact.
-40: none of three annotated wedding-attendance turns survives the whole-message
  context; Reader only sees unrelated/assistant advice and refuses. This is a
  genuine evidence-window/packing limitation; separately frozen prior passage/
  selection diagnostics exist but are not substituted for this baseline row.

Conversely,20 and37 answer correctly while missing some/all labelled turns in
packed context. Alternative original evidence exists; annotations do not exhaust
all sufficient sources. Optimizing only annotation ID coverage is insufficient.
The observations above are developer inspection, not independent semantic audit.
Keep all original answers/grades and represent uncertainty instead of launching
another judge-calibration or opened-example prompt-tuning loop.

## Actual cost and integrity

| Stage | Calls | Input tokens | Output tokens | Total |
|---|---:|---:|---:|---:|
|Reader|30|216232|6034|222266|
|task judge|30|14402|1445|15847|
|total|60|230634|7479|238113|

Complete usage60/60, zero failed/interrupted attempts, zero retries/output repair;
within all frozen call/byte budgets. About7937 reported tokens per question,
including scoring, **excluding sunk original ingestion/embedding/local reranking**.
No cache-only replay or independent judge verification ran. This is not a currency
invoice, standalone from-zero cost, or a matched cost ablation against the previous
five-question/two-arm selector experiment. No provider-side price assumptions.

Preparation used no paid calls or model/retrieval rerun. Reproduced all30 saved
contexts exactly (707690 bytes total; Reader requests856416 bytes,max29104).
Existing14986 raw records in the two source schemas stay unchanged; each scope's
full inventory and original runtime mapping checked before/after preparation and
QA. Server-read-only Store; no ingestion/index/graph writes, DB reset, Docker
restart, source truncation or invented fact. All30 citation/derivation structural
checks pass; legal citations are not independently proven support/entailment.

## Reproducibility and next step

Code/protocol freeze30c1bb4 and actual request supplementb69aa6a were pushed
before provider execution. See the [frozen plan](public-memory-uniform-qa-plan-2026-10-18.md).

- Preparation:`data/doppel/uniform-qa-11-40-prepare-live-v1.json`, SHA256
  `53a08c85dbe8fd49885d8b8e6a6bdc7c23850cc7b4a56a6f44789079e23b8b51`.
- Answer plan fingerprint:
  `7a4c9d8a3fb68981af0dfd8be4af47ce65ff1b76a91337cc83f9b85714563056`.
- Answers:`data/doppel/uniform-qa-11-40-answers-live-v1.json`, SHA256
  `2b2fa5d1df24f61bdc15149d0421d211a031b6001b5b34d676e1abc8b0d2541e`.
- Per-row context/answer receipts, stage caches and durable ledger:
  `data/doppel/uniform-qa-11-40-v1/` (ignored). No keys written in source/reports.
- Eleven new offline tests pass, including real Store/fake-provider end-to-end
  and Reader/gold separation. Ruff repository and new format checks pass; new
  runner Pyright zero errors. Full suite2078 passed,33 skipped,three subtests
  passed in302.32s; one existing optional Graphiti/Pydantic deprecation warning.
- Only the user's pre-existing uv.lock modification remains unrelated/unstaged.

Keep this baseline frozen and extend the same configuration to the remaining20
histories before reporting a uniform50-item score. Do not replace this result with
the earlier rough80% mixed-version accounting or recent5/5. Afterwards evaluate
generally better evidence delivery and clearly distinguished answer-task behavior
as separate new configurations, without question/entity/role quotas or relaxing
plan/fact, actor/subject, authorization or provenance boundaries. Reserved histories
stay closed until a final configuration is fixed. Graph authoring remains paused.
