# Fresh five-case comparison: better evidence retention, no QA gain yet

Date:2026-10-18. Selection/algorithm protocol commit:`7a21f4f`; actual-request
supplement:`8d6eb75`, both committed before paid evaluation. All five fixed
ordinals41-45 completed, without replacement, reruns, output repair or changes to
Reader/judge/model/algorithm after outcomes. These questions were not used for
the preceding selection development, but this is public data and does not prove
model-unseen independence or official LongMemEval/AML/release performance.

## Primary paired QA

| Ordinal / category | Local BGE content-only | LLM metadata up-to20 |
| --- | --- | --- |
|41 preference/personalized recommendation|incorrect refusal|incorrect refusal|
|42 predeclared unanswerable|correct abstention|correct abstention|
|43 user fact|correct|correct|
|44 temporal ordering|incorrect refusal|incorrect partial/wrong sequence|
|45 knowledge update|correct|correct|
|All five|**3/5**|**3/5**|
|Four answerable cases only|**2/4**|**2/4**|
|Unanswerable case only|**1/1**|**1/1**|

These are unchanged **provisional DeepSeek task grades**, not official GPT-4o
scoring or an independent judge. No primary label was changed after source audit.
Do not pool these results with the preceding opened-three/two diagnostics or
claim a full500 score. Category sample sizes are too small for stable rates.

## Candidate→selected→packed evidence

Four answerable cases have11 annotated source turns. A post-run read-only source
audit maps frozen candidate memory IDs back to original session/turn positions:
the common80-candidate pools contain **9/11** annotated turns. The negative case
has no positive evidence denominator and is excluded from this calculation.

| Stage | Local BGE | LLM selector |
| --- | ---: | ---: |
|Same initial80 pool, annotation-turn presence|9/11|9/11|
|Selected source20 cap, annotation-turn presence|4/11|9/11|
|Packed **complete original annotated-turn text** retained|**3/11 (27.3%)**|**9/11 (81.8%)**|
|Answerable questions retaining all annotated-turn texts|2/4|3/4|
|Fragment semantic answer-support recall|not measured|not measured|

The complete-turn retention numerator is computed from actual Unicode source
intervals covering the entire original text, not merely an annotated source ID
appearing somewhere in a fragment. All counted annotated turns in these rows are
fully present. This is still **annotation/text retention**, not a proof of semantic
sufficiency, unique factual events, correct reasoning or general retrieval recall;
annotations can omit alternative valid evidence.

| Case | Annotated turns | Pool presence | BGE selected / fully packed | LLM selected / fully packed |
| --- | ---: | ---: | ---: | ---: |
|d6233ab6|2|2|0 /0|2 /2|
|f4f1d8a4|1|1|1 /1|1 /1|
|gpt4_7abb270c|6|4|1 /0|4 /4|
|6a27ffc2|2|2|2 /2|2 /2|

The observed improvement concerns both selection and downstream preservation.
It is not a model-only causal comparison: BGE sees raw text, while the LLM also
sees attribution/time and can select fewer than20. Those profile differences were
declared before evaluation; no additional metadata-only arm was run.

## Context size is lower, not necessarily total cost

| Across all five | BGE | LLM |
| --- | ---: | ---: |
|Packed source-fragment items|74|27|
|Packed JSON UTF-8 bytes|118,299|27,298|
|Mean bytes/question|23,659.8|5,459.6|

Packed bytes decrease **76.9%** in this sample. LLM packed item counts are2,3,1,17,4;
all selected fragments fit the existing24KB budget. BGE packed16,15,15,13,15 items
and lost some later selected fragments to the budget. No source text was silently
shortened. Neither profile exhausted its80-fragment candidate bound.

This does **not** show net provider-token or monetary savings: the LLM selection
itself costs117,635 tokens, whereas BGE ranking is local. Lower downstream context
volume and higher overall selection cost must be reported separately. No stable
p50/p95/idle-GPU or cost-per-correct-answer benchmark is claimed.

## Failure attribution

### Preference: evidence is present, recommendation is still refused

`d6233ab6` asks for a personalized recommendation about attending a high-school
reunion. The LLM profile retains both complete annotated owner statements, about
positive high-school experiences including debate/AP coursework and old friends.
The unchanged Reader recognizes this context but refuses because the items do
not state the owner's current reunion intentions or feelings. BGE had lost both
annotated messages and also refuses.

The LLM row is no longer explained by missing annotated evidence. This points to
the reference Reader's treatment of recommendation/inference versus factual
recall, not a reason to add a reunion keyword rule or more graph authoring.
It remains an incorrect primary answer, not a retroactively successful case.
An agent can choose an appropriate advisory policy while keeping suggestions
distinct from historical facts; that policy is not implemented/tuned in this run.

### Temporal ordering: two annotations are missing before reranking

`gpt4_7abb270c` asks to order six museum visits. The LLM retains all four annotated
turns present in the initial pool, plus other genuine but potentially ambiguous
museum mentions. It gives a partial six-name sequence but substitutes a Modern
Art Gallery for the expected Museum of History and has date/identity caveats.
BGE gives no complete sequence. Both grades remain incorrect.

Post-run original-position audit:

| Missing annotated owner turn | Nearest candidate in same session | Distance |
| --- | --- | ---: |
|(9,6), Contemporary Art lecture|(9,7)|1 turn|
|(19,0), History conservation-lab visit|(19,1)|1 turn|

Both source sessions are represented in the pool, but not those precise owner
turns. Thus session presence alone also must not be called complete evidence
coverage. Another selected turn supplies an alternative Contemporary Art mention,
so two missing annotations do not automatically mean two completely absent facts;
the History visit is a concrete unresolved omission in the produced answer.

After LLM source selection, the nearest retained turn in the first missing
message's session is6 turns away and none remains in the second session. Simply
appending one neighbor **after** selection would not recover these examples.
This is a read-only, post-result diagnostic, not a tested neighbor-expansion gain.

### Other cases

Both profiles correctly identify the stand-mixer gift as coming from the sister,
and latest course progress as30 videos rather than the earlier20. Both correctly
abstain on the predeclared missing poster/university detail, rather than equating
conference attendance at Harvard with a specific poster presentation. These are
one case each, not general factual/update/epistemic-safety success rates.

## Execution and integrity

- Five separate complete S histories,2,517 original messages/251 transport chunks.
  Only a new dedicated schema`raw_select_952e5f3593e0` was created; existing
  schema/graph/cache/journal data were not reset or deleted.
- Preparation:zero LLM; existing local bge-small-zh512 embeddings and BGE-v2-m3
  reranker, CUDA/batch1/8192 cap.10 local operations/601 pairs/0 reported truncated
  pairs, longest1708 tokens. The model was loaded from local files.
- Evaluation:server-enforced read-only Store; exact source/pool/preparation/code
  hashes. Per-case inventories match before/after. Source/passage rejection maps
  are empty for all10 rows. Original role/authority/time/offset/hash checks remain.
- All27 citations across10 responses are legal (BGE10, LLM17), with no duplicate
  or unknown IDs within responses. All structural checks pass. This is not a
  semantic-faithfulness certificate, adversarial isolation test or proof that
  subjective/date inferences are correct.
- No graph authoring/extraction/Planner calls, output repair/retries, benchmark
  keyword rules, old-score changes, default promotion, model change, or access to
  ordinals46-50/reserved histories for evaluation. Key environment-only; unrelated
  user`uv.lock` remains untouched/unstaged.

| Stage | Paid calls | Input tokens | Output tokens | Total |
| --- | ---: | ---: | ---: | ---: |
|Selector|10|117,210|425|117,635|
|Reader, both arms|10|56,080|3,439|59,519|
|Provisional task judge|10|5,532|557|6,089|
|Total|**30**|**178,822**|**4,421**|**183,243**|

All30 attempts succeed with complete provider usage, zero missing usage/retries;
all durable call/byte caps hold. Historical failed selection experiments are not
included in this new-experiment total or erased. No exact currency billing claim.

## Artifacts and verification

Ignored local files:

- Prepare preflight SHA-256
  `02746738637a6c289e3d58235e71b6d988809a004fabf46f0fb7bc3797b13b0b`.
- Prepare live `data/doppel/prospective-selection-41-45-prepare-live-v1.json`, SHA
  `67ae6a8221e2601e6cebd62ba20cbb4fd1e3593b57b1baf5bb9ff0f5c457f59c`.
- Evaluate preflight SHA
  `f2095389ee25d7d2a94412ffb100c9d944a78136689465801cd0ffbd58c0d38a`.
- Evaluate live `data/doppel/prospective-selection-41-45-evaluate-live-v1.json`, SHA
  `51e2b27fd7163076183046f7955f8ea18588a31f14bb68fd1fa716723be17a90`.
- `data/doppel/prospective-selection-41-45-v1`:five preparation receipts with
  candidate snapshots,30-call SQLite ledger/exact-output caches, ten selection
  request receipts, ten packed contexts and ten answer checkpoints.

Full regression:**2031 passed/33 skipped/three subtests** in248.92s. New-protocol/
bounded targeted22 pass, Ruff repository and new-file format checks pass; Pyright
new wrapper has zero errors. One existing Graphiti/Pydantic warning. No full
cache-only pipeline replay, official scoring, repeated quality run or latency
stability test was performed.

## Next decision

Keep bounded selection opt-in: it shows a meaningful small-sample retention/size
gain but **no measured QA gain**. Do not keep regrading these now-opened cases.
Next test a generic bounded **pre-selection** source-neighborhood expansion:
read-only original-message lookup within the same authorized scope/session,
explicit source order/IDs, no cross-conversation merging or guessed chronology,
no summaries or LLM extraction. Fix count/byte limits and validate provenance and
boundary behavior offline before another separately frozen unseen continuation.
Neighbor lookup must use host-provided stable source order; transport turn indices
can reset between chunks and must not silently serve as a global conversation
ordinal. The two observed adjacent misses motivate the mechanism, not production
rules for museums/roles/question IDs or a claim of a corrected score.
