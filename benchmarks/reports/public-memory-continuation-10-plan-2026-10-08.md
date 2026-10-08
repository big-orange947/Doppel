# Same-ten-history continuation: finish ingestion, then measure three channels

Freeze this plan and code before paid execution. Start from successful unchanged-
request recovery, not a selected high-performing subset. No new Judge calibration,
case-specific rule, prompt tuning, case replacement or default retrieval change.

## Source, preservation and recovery performance

Same ten selected public histories, original complete source order and generation
settings as the stopped expansion. The previous failures/costs remain in lineage.
Parent report `data/doppel/longmemeval-recovery-observe-live-v1.json`, SHA-256
`872d7e3142a49b50799056c22f4d3597404a5234bf7fa1ff7af4a25244d0c9e9`.
Parent journal SHA-256:
`ec089f324d8a311dfb65c9fa6a784355b2f57c08c2e12e367771b7374b2d6692`.

233 completed source chunks, **249 remaining**. Clone the closed journal to a fresh
child namespace, retain old caches read-only and bind their inventories. Use the
existing dedicated PG Store/index, no schema/volume reset or unrelated data writes.
Validate all completed requests against exact journal payload/scope/completion and
authoritative raw records, including missing/corrupted-source detection. Reconcile
the entire index once per completed scope, rather than once per chunk. This is an
additive recovery method; ordinary single-request replay remains unchanged. Fail
before new model calls if prefix source/index validation fails. Do not skip a
pending chunk or a hole in the prefix. No weakening of subject/authority gates.

The response with 32 quarantined contact-subject drafts remains quarantined. Do
not change its policy before measurement; raw evidence is retained. Semantic
correctness of those drafts has not been adjudicated.

## Frozen execution and measurements

| Stage | Lifetime new-attempt cap |
| --- | ---: |
| Remaining extraction | 249 |
| Reader v2 | 30 |
| Auxiliary judgments | 30 |
| New total | **309** |

Original+recovery cost baseline is 234 calls / 1,218,411 reported tokens. Retain all
of it; cumulative maximum including this plan is 543 attempts. No automatic retry,
model substitution, increased completion cap or altered prompt. Unknown usage is
not zero. The extraction config stays DeepSeek v4 flash/json_object/temperature0/
thinking disabled/max_tokens8192. Reader2048 and Judge3072 settings are unchanged.
Each failed Reader/Judge row is retained and may leave a question unscored; no paid
repair/resampling. Ingestion failure stops all downstream stages.

Once **all 482 chunks and provenance/index checks** complete, immediately execute
the ten questions x three profiles: raw_vector_reranked, memory_vector_reranked,
combined_vector_reranked. Same local BGE-small-zh512, bge-reranker-v2-m3/CUDA8192/
batch1, candidate80, final20 and shared serialized-context24k-byte cap. Same Reader
v2 and auxiliary judgment prompt/schema; no taxonomy-control gate. Keep annotated
candidate/top5/packed evidence coverage distinct from answer quality. Publish
provisional same-model correctness with denominators, unscored rows and quote-
anchoring validity, not as independently verified truth. No performance-based
selection, no semantic repair, no guessed scores for failed rows. No Graphiti or
production natural Planner is run by this composition diagnostic. Public small-
sample development, not full LongMemEval, independent blind, latency or AML scores.

If completed, perform a separate key-free cache-only replay and compare the retained
retrieval contexts/answers/judgments/summary. Do not rerun paid calls to chase scores.
An attempted namespace can only resume as cache-only, not expand its paid budget.

## Binding and command

Plan fingerprint:
`ecb9ec825f609c3607fe76855521db5ceb00d5b93e1eb92052f3ac072ffe96ef`.
Preflight `data/doppel/longmemeval-continuation-10-preflight-v1.json`, SHA-256
`2db66bf07e5e67ed29275e4acdcce0a1d0d917575e873936878a976dcc00eea0`.
Run directory `data/doppel/public-memory-continuation-10-v1`.

```powershell
& D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_continuation `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-10-manifest-v1.json `
  --parent-report data/doppel/longmemeval-recovery-observe-live-v1.json `
  --parent-report-sha256 872d7e3142a49b50799056c22f4d3597404a5234bf7fa1ff7af4a25244d0c9e9 `
  --parent-dir data/doppel/public-memory-recovery-observe-v1/ingestion `
  --parent-cache-dir data/doppel/public-memory-expansion-10-v1/ingestion/provider-cache `
  --parent-cache-dir data/doppel/public-memory-recovery-observe-v1/ingestion/provider-cache `
  --run-dir data/doppel/public-memory-continuation-10-v1 `
  --output data/doppel/longmemeval-continuation-10-live-v1.json `
  --reranker-model-path D:/project/.doppel-eval-models/bge-reranker-v2-m3 `
  --embedding-cache-dir C:/Users/freeze/AppData/Local/Temp/fastembed_cache --live
```

Key stays in the environment, never in commands/reports. If Docker is unavailable,
ask the owner to open it manually, never auto-launch/reset it. Old artifacts and
user-owned `uv.lock` remain untouched. Offline tests cover parent/config/prefix
binding, once-per-scope reconciliation, missing source detection, separate attempt
caps, no downstream execution after ingestion failure and honest aggregate usage.
