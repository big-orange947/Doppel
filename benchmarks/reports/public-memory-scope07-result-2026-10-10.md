# Seventh question: title-less assistant reply misses the raw candidate pool

Source/schema/query were frozen in `4b8a7fd`, `a6636f7`, `9698659`; unchanged
Reader V2, models, source data, clocks and packing. This is an opened source-order
development question, not independent LongMemEval/AML validation. Preserve failure.

Case `e8a79c70` asks how many eggs the assistant previously specified for a classic
French omelette. Task judge marks the refusal incorrect; required reference is
2–3 eggs. Annotated turn coverage **0/1**, session coverage **1/1**. Four citations
are legal, source-anchored checks pass. Citation judge calls refusal supported and
also correct, despite the task failure. That field assesses a different supplied-
context situation and must not override the reference-only task score.

## Verified failure boundary

The original assistant reply exists in the authoritative Store as confirmed raw
`agent_output`, `mem-9aacc19548624b29a55ece647fec6603`, observed
`2023-05-21T01:17:00Z`, before the frozen horizon. Its text starts:

> Ingredients: -2-3 eggs -A pinch of salt -1 tablespoon of unsalted butter

It is turn 1 of the same source session as the raw rank-1 owner question
`mem-1e98f3013cdc48a7a4acbc1a07fa9cd0` (turn 0), which explicitly names the dish.
The reply itself lacks that full title. Other retrieved replies about fillings
and technique name the dish explicitly, but do not provide the quantity.

A separate **zero-provider-call, read-only vector diagnostic** repeats the same
question/profile/state/kind/observation cutoff over the unchanged selected scope,
requesting 500 rather than 80 candidates purely to locate the stored source.
The recipe is vector rank **210**, outside the real run's raw candidate limit 80.
The first 80 contain 79 ingestor records and one other event, so derived-record
crowding is not the main cause. The recipe never reaches the real reranker or
20-item packer. No gold phrase is used to select candidates in the real run; the
known source ID is used only for post-run attribution in this opened diagnostic.
No new graded answer, changed top-k default or score is produced by the probe.

Primary failure: **raw candidate discovery / conversational unit context**,
not missing storage, source authority rejection, horizon clipping, reranker
truncation or packing eviction of this recipe. The Reader reasonably refuses
given the supplied records. Do not patch it to guess a conventional egg count or
promote assistant instructions to owner facts. A stronger embedding, uniformly
larger pool, or verified reply/context linkage is worth a separately frozen test.
Any context-linking feature must be generic, scoped, source/horizon-validated,
role-preserving and tested on unrelated controls, not recipe/egg special cases.

## Execution and usage

Unbounded natural lookup, one exploration and zero exact/promoted graph paths.
20 whole items/17943 UTF-8 bytes, memory/raw/backing candidates 20/20/18; 179 CUDA
pairs, zero input truncation. Zero source failures; Store/vector/selected graph
unchanged. Execution `review_required` for an open `preference.favorite-song`
governance marker; relevance/semantic validity remains unverified. No graph-uplift
claim. Question reference/horizon `2023-05-30T08:29:00Z`, all 483 supplied turns
precede it, latest `2023-05-30T06:09:00Z`. English question/answer here.

| Stage | New calls | Reported tokens |
| --- | ---: | ---: |
| Source graph | 876 | 3612252 |
| Source-name schema | 6 | 13125 |
| Planner | 2 | 22426 |
| Reader | 1 | 5236 |
| Task judge | 1 | 574 |
| Citation judge | 1 | 7169 |
| Total | 887 | 3660782 |

No failed/interrupted attempts, retries or missing usage. Seven complete source
graphs/1415 projections are preparation coverage, not seven successful answers.
Seventh graph's two endpoint warnings stay documented; subsequent telemetry is not
retroactively applied. Eighth source-only authoring proceeds under its own freeze.

Empty-key replay: zero new calls, three downstream cache hits, unchanged plan,
retrieval, Reader/judges, context/packing/evidence. Not fresh planner/GPU execution.

- Live: `data/doppel/public-memory-next-query-scope07-live-v1.json`, SHA-256
  `f4070cc2f37eb160b0db1d1ba0eba12d45536274ae36059b5fbae362e1c39fe1`.
- Replay: `data/doppel/public-memory-next-query-scope07-replay-v1.json`, SHA-256
  `48eadc26c974ba144354bb2a3b2810be296dc44725ee8474e6acf57a8ac98414`.

Validation remains 1523 passed/33 skipped/three subtests; Ruff passes; explicit
local-interpreter Pyright clean for the added telemetry/modified writer. `uv.lock`
stays user-modified/unstaged. No production algorithm changed to improve this score.
