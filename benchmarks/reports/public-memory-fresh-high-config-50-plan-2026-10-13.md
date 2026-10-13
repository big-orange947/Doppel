# Prospective 50-question highest-config assessment: frozen selection and protocol

Starting core snapshot `446bf09`. This resumes broader evaluation rather than
requiring every development control to pass. No candidate analyzer is promoted,
no old task cohort is rerun, no original answer/score/cache is rewritten.

## New samples, source/gold boundary

Pinned original LongMemEval-S source SHA-256:
`d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
Exclude all development **and reserved** history groups in the three prior manifests
(79 groups), plus the separately opened oracle diagnostic (one additional group).
Keep those old reserved groups untouched. Select 50 new complete-history groups
and reserve ten more, seeded hash order / round-robin public strata, seed 20261013.

Sampling copies only IDs, public type, dates and original role/text histories.
Original question, reference answer, annotated sessions and `has_answer` values are
not copied to the sampler or ingestion runtime. The public `_abs` ID marker defines
a separate no-answer stratum; this is disclosed type sampling, not hidden gold use.
The dataset byte hash binds the entire file but does not inform selection semantics.
Questions are loaded only for later frozen query execution; gold/turn annotations
remain scoring-only. Exact source histories/order/timestamps are retained.

| Stratum | Selected |
| --- | ---: |
| Single-session user | 8 |
| Temporal reasoning | 7 |
| Knowledge update | 7 |
| Assistant history | 7 |
| Multi-session | 7 |
| Preference | 7 |
| Public no-answer IDs | 7 |
| Total | 50 |

This is prospective on previously unused questions, **not independently blind**:
the benchmark is public and some filler sessions repeat across different histories.
Balanced sampling oversamples rare categories relative to the 500-case population.
Do not present the sample's overall accuracy as the full-dataset or AML score.
Report selected-case, 43 ordinary-case, seven no-answer and per-stratum rates.
Selection recipe/IDs/exclusions are committed in the separate metadata-only JSON.

The selected 50 histories contain **25,002 transport messages / 2,479 chunks**.
Each case has its own scope in `longmemeval-fresh-high-config-20261013-v1`.
The ingestion schema is `public_memory_3055ab766570`; never reset old data to reuse it.
No old memory/graph corpus is relabeled as this new corpus. Exact source-aware cache
hits are allowed and reported; arbitrary copied graph edges or summaries are not.

## Freeze two profiles, not a tuning matrix

1. `full_high_config`: production `HighConfigRetrieval`, natural V7 two-pass path
   Planner, lexical/pgvector/Graphiti relation/path discovery, evidence-rich V8
   assembly, CUDA BGE reranking, raw dialogue and source backing. Dependencies must
   be ready; zero relevant path hits is valid, missing dependencies are not a
   successful downgraded full profile. Query source/subject/authority/time checks
   stay enabled. Explicit semantic/relation fallback switches are false.
2. `raw_vector_reranked`: original role-attributed history vectors + the same local
   scorer, unchanged Reader and task/citation judges. No Planner or memory/graph
   authoring in its own query path. It can share source ingestion with the full arm.

Use existing local `fastembed:BAAI/bge-small-zh-v1.5`, 512 dimensions, plus
`bge-reranker-v2-m3`, CUDA, 8192 tokenizer cap / batch size 1. This freezes the
current complete high-config composition, not a claim the local embedding is
theoretically the strongest possible model. No model-selection experiment here.

Persistent source analysis remains default Reference V8, confidence .75, actor/
subject evidence matching and quarantine; deterministic consolidation V5. V9/V10
stay opt-in and their failed development gates remain intact. Graph authoring uses
all eligible source memories in each completed selected scope, never question/gold-
targeted records or fixture edges. Schema authoring receives type names only.

The query/Reader context is fixed at 20 whole items / 24,000 UTF-8 bytes. Full arm
uses existing cyclic memory/raw/backing packing; raw arm uses source-ranked whole
items. Same caps are not guaranteed equal token counts; report actual usage.
Preserve source roles, observations and effective bounds. Use S's original question
date with `provided-history-v1` observation horizon; 70 supplied sessions lie after
their question reference across this selection. This is full supplied-history
evaluation, not causal replay or oracle replacement of S clocks. Naive source times
use the declared UTC calendar assumption, not verified geographic timezone.

## Calls, stage gates and first bounded source execution

Freeze maximum ingestion calls at **2,479**, one per planned chunk; no automatic
retry. Output cap 8192. Raw storage/local embeddings are not paid LLM calls.
Graph and type-schema call counts are **not yet known**: bind actual eligible-record
and relation-type inventories, requests and exact ceilings before paid graph authoring.
This selection preflight does not authorize an unlimited graph job or certify QA
readiness. Do not hide graph costs inside a cheap query-only estimate.

QA ceilings over all 50 cases: full arm 250 calls (100 Planner, 50 Reader, 50 task
judge, 50 citation judge), baseline 150, total **400**. These are attempt ceilings,
not predicted physical calls/token prices; cache hits can reduce actual requests.
Requested alias `deepseek-v4-flash`, JSON object, temperature 0, thinking disabled.
No pinned-snapshot claim. DeepSeek task scoring is reference-only and provisional,
not the official GPT-4o scorer; it must not excuse an answerable refusal merely
because retrieved evidence is missing. Citation support is separate from correctness.

First source stage is an explicit supplement: **first frozen history `15745da0`,
49 chunks / 474 original messages**, at most 49 attempts, graph/QA calls zero.
It binds the immutable cohort/core/configuration, source-only ingestion plan and
new adapter source hash before any calls. Added stage plumbing does not change a
pinned algorithm/prompt or selection. Use one fresh durable continuation budget,
with initial journal required absent. A repeated live invocation cannot advance
past this prefix accidentally; replay is explicitly cache-only / zero new chunks.
Authenticate/check balance before execution; retain all failures and usage, no
automatic retry or missing-call accounting as success. Observed balance change is
not an exact invoice or exclusive attribution. Report source progress separately
from completed answers. New graph budgets will be separately committed.

Run remaining stages in fixed case order, alternating profile order, report ten-
question blocks under the same snapshot. Include all 50 selected cases in the
end-to-end denominator; separately report completed/scored-only rates and missing
usage. Preserve failed rows, unscored judgments and incomplete index stages. No
outcome-based prompt/core/packing/schema repair in the middle of this cohort.
A necessary operational fix requires a disclosed supplement, preserved failure and
new bindings; it cannot retroactively change answers. No GPU latency campaign.

## Zero-call readiness and bindings

Local named PG/Neo4j containers healthy; read-only inspection finds **new schema
absent, new-scope Episodes/edges both zero**. That is expected unmaterialized data,
not a successful completed graph. pgvector extension 0.8.6; CUDA available,
PyTorch 2.7.1+cu128 / CUDA runtime 12.8. All local reranker artifact hashes match
the previous high-config model; no model inference/latency sample or DB write.

- Manifest SHA `661f72949426cde42855bdfa69ea23dcc3062bd6e636f80fea44731e9b651ab5`.
- Manifest fingerprint `e57c3157a2e885579d328bdcd262dc10869dfde9d63a98ce69d42d543382731d`.
- Cohort plan SHA `084df32e770d2e6231ec7d9e501d37685539a54630eaf1114331fd16551c19e7`.
- Cohort plan fingerprint `cda3fbe324af2f63c60453faa87d4b66db0f68b1b9b77386bc4b09fbf27a5e5a`.
- Resource-audit SHA `57f6ed3c4435c81e13d639058d3bf6f81e61ed9f4408b7abe278fdf432e83fed`.
- Stage01 preflight SHA `c7ddad1425e9283ac4a43cf328e163401fb18a8621cd14284c7fe399935912f2`.
- Stage01 fingerprint `3a596d75037377b46f97b548e22765afb759d2b3089b9f21cc4fb3f334073c0e`.

Local complete artifacts stay under ignored `data/doppel/`; the committed selection
and this plan expose only metadata and hashes, no credentials/source question text.
Fifteen new offline tests verify label-invariant sampling, source equivalence,
prior/reserved/opened exclusions, profile/call limits, snapshot gates, cache-only
key removal and prevention of accidental repeated advancement. Core algorithms
are not edited in this preparation. `uv.lock` remains untouched/unstaged.
