# Fresh matched-pool neighborhood trial: actual QA, not only coverage

## Outcome

Fixed new diagnostic ordinals46–50, five full LongMemEval S histories/2483 raw
messages; same bounded LLM selector, passage policy, Reader and judge in both
arms. Native matched-count widening: **5/5** provisional task correct;
source-neighborhood expansion: **4/5**. Answerable questions:4/4 vs3/4; the
predeclared negative:1/1 each. This does **not** establish a general100% accuracy
rate, a significant advantage, a full LongMemEval result, or an AML score.
No QA default changed; retain source neighborhoods as optional, not promoted.

Both arms use lexical/vector production RRF; the difference is candidate pool
construction, not a no-vector/graph comparison. There are no graph/extraction
calls. Preparation uses only raw ingestion and existing local embeddings.

## Paired results

| Ordinal / case | Candidates per arm | Native correct | Neighborhood correct | Candidate annotations native / neighbor | Full annotated turn texts packed native / neighbor |
|---|---:|---|---|---|---|
|46 /58470ed2|170|yes|yes|1/1 /1/1|0/1 /0/1|
|47 /b3c15d39|168|yes|yes|2/2 /2/2|2/2 /2/2|
|48 /afdc33df|143|yes|no|3/3 /3/3|2/3 /3/3|
|49 /2311e44b_abs|155|yes|yes|negative; excluded|negative; excluded|
|50 /001be529|183|yes|yes|1/1 /1/1|1/1 /1/1|

Totals:819 candidates per arm, seven annotated positive turns in four positive
cases. Both pools and both source selections contain7/7 annotations. Packed
source-turn presence6/7 vs7/7; **full original turn text** retention5/7 vs6/7.
These annotation statistics are not fragment entailment or answer support.
The first case answers correctly from a useful span without retaining the whole
long annotated turn: full-turn retention is deliberately conservative.

Selected original source counts:29 vs39. Packed context bytes:34335 vs36956
(neighborhood7.6% larger). The five original-source selection requests total
918208 vs1181769 canonical bytes (neighborhood28.7% larger). Candidate count
matching does not match bytes, language-model input length, or standalone cost.
No expansion rejections, count/byte cap hits or unvisited anchors were observed.

## Why the extra evidence did not improve QA

Case48 asks for practical kitchen-cleaning advice adapted to prior circumstances.
Its reference rewards using existing utensils/storage and granite/sink concerns.
Both arms retrieve and select all three annotated turns. The neighborhood arm
even retains all three original texts, whereas native packs two complete texts.

The native Reader includes concrete, previously discussed steps for utensils,
faucet/disposal maintenance and granite care, while explicitly attributing old
suggestions to the assistant. Its answer is verbose and initially caveated, but
the unchanged judge accepts the actionable advice. The neighborhood Reader
mostly names related topics and points at IDs, then concludes it cannot give a
supported general answer. The unchanged judge rejects that lack of actual tips.

This is an observed answer-use/selection-context sensitivity, **not an annotated
evidence-recall failure**. It does not prove adding a particular neighbor caused
the refusal: whole candidate pools/order, selected sources and contexts differ;
there is one model sample per request and no counterfactual or repeat experiment.
Both responses contain similar caution, so judge sensitivity remains relevant.
Do not silently relabel or rerun the losing row. Product advice generation can
use retrieved facts without falsely claiming the user already followed advice;
no new Reader rule or prompt change was made in this experiment.

## Accounting and safeguards

| Stage | New calls | Input tokens | Output tokens | Total |
|---|---:|---:|---:|---:|
|source + passage selector|17|541122|687|541809|
|Reader|7|27650|3921|31571|
|task judge|7|4830|368|5198|
|total|31|573602|4976|578578|

Twenty logical selector requests and ten Reader/judge rows finish. Three exact
request cache hits in each stage reduce new calls from the40-call ceiling to31.
Zero failed attempts/retries, complete provider usage31/31, all stage budgets
respected. Cache reuse and fixed native-first order mean paid totals should not
be presented as independent per-arm deployment cost. Provider-side cached-input
usage is distinct from local exact-request cache hits. Token counts are not a
currency invoice; monetary billing was not queried.

Selector calls consume93.6% of new reported tokens. This is now the conspicuous
cost target; the smaller final Reader context does not make the preceding
whole-pool LLM selection cheap. Do not launch another broad paid sweep unchanged.

Evaluation is PostgreSQL server-read-only.1638 source candidates revalidated;
68 final selected-source checks and38 final passage checks; zero source/passage
rejections. Exact-scope/provenance validators and end-of-case full corpus hashes
pass. Ten citation/derivation structural checks pass, no illegal or duplicate
citations; this does not certify semantic support. Original Store data, old
experiments, judge labels and caches remain unchanged. Keys are environment-only.

## Reproducibility and verification

- Protocol/code frozen in98b18f0; actual-source supplement16b5cc1, both pushed
  before paid calls. See the [frozen plan](public-memory-neighborhood-trial-plan-2026-10-18.md).
- Dataset SHA256:
  `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
- Preparation:`data/doppel/neighborhood-trial-46-50-prepare-live-v1.json`, SHA256
  `393b8c67c2e29b19fdb0b6e95dda5658ee8438b9fa1c7df278369124e790ee0b`.
- Evaluation plan fingerprint:
  `3adbf505a4999d21f9e9516f19b014ccca50780e4955f31927d0353c3c85c333`.
- Evaluation:`data/doppel/neighborhood-trial-46-50-evaluate-live-v1.json`, SHA256
  `7f8567e5accad796f0c2978200769937be2a5042d783aa437f827ce218de5e86`.
- Per-row contexts/answers, twenty logical selector request receipts, durable
  stage ledger and caches:`data/doppel/neighborhood-trial-46-50-v1/` (ignored).
- Eleven new offline tests pass, including exact full100-candidate preview/input
  equivalence through a real Store. Full suite:2067 passed,33 skipped,three
  subtests passed in297.31s; only existing optional Graphiti/Pydantic warning.
  Whole-repo Ruff passes; new files format clean; new runner Pyright zero errors.
- No old artifacts overwritten; no database reset or Docker restart; uv.lock
  remains the unrelated pre-existing working-tree modification, not staged.

## Next decision

Keep the two findings separate: opened41–45 demonstrated candidate-level gap
recovery; fresh46–50 shows no extra candidate coverage over same-count native
retrieval, no QA gain, higher source input and one answer-use regression. These
are different cohorts/profiles, not comparable aggregate benchmark scores.

The fifty-history diagnostic manifest is now opened; keep its ten reserved
histories untouched. Freeze an economical candidate-to-answer configuration
before any reserved evaluation. First investigate general, answer-independent
source/span selection cost reductions locally and account for lost complementary
evidence; do not feed gold or hand-picked entities into a shortcut. Once that
configuration is locked, evaluate it on a separately fixed cohort/reserved arm
with no tuning on those outcomes. Leave graph authoring paused and do not change
embedding models at the same time as candidate policies.
