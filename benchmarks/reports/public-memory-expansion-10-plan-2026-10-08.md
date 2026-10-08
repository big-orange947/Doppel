# Ten new public histories: fixed three-channel composition diagnostic

Starting commit `772d14d`. Freeze implementation, tests and this plan before paid
execution. No new Judge calibration arm, prompt revision, answer-specific rule,
replacement question, truncated history or core-default change after results.

## Selection and source

Use the existing 500-case LongMemEval-S cleaned snapshot, SHA-256
`d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
Seed **20261008**, ten diagnostic groups plus three reserved-not-run groups.
Exclude all six exact history groups in the old pilot manifest, including its
reserved groups and any alternative question sharing an excluded exact history.
Choose one case per complete-history group, seeded by ID/history hashes; use
public question-type strata in seeded round-robin order. Gold answers, annotated
evidence, query wording and observed quality do not choose groups or representatives.
Type metadata is sampling-only and does not reach ingestion or Reader requests.

| New diagnostic case | Public stratum | Complete Add chunks | Raw turns |
| --- | --- | ---: | ---: |
| gpt4_2312f94c | temporal-reasoning | 45 | 467 |
| 07741c45 | knowledge-update | 49 | 527 |
| 3a704032 | multi-session | 48 | 479 |
| 0e5e2d1a | single-session-assistant | 46 | 450 |
| 86f00804 | single-session-user | 46 | 503 |
| 1a1907b4 | single-session-preference | 49 | 532 |
| gpt4_5dcc0aab | temporal-reasoning | 50 | 547 |
| 59524333 | knowledge-update | 48 | 528 |
| gpt4_2f91af09 | multi-session | 55 | 515 |
| 7a8d0b71 | single-session-assistant | 46 | 489 |

Total **482 chunks / 5,037 raw turns**. No abstention-marked case was drawn: do not
claim a no-answer/abstention capability result. All ten retain their full supplied
histories, original role attribution, session dates/order and question calendar
reference. Use the existing full-haystack, not arrival-cutoff, temporal protocol.
One session-content overlap exists among the thirteen selected groups; exact-history
exclusion does not prove independent histories. This is new-to-this-run public
development data, **not** an independently blind sample, full benchmark or AML score.

Manifest: `data/doppel/longmemeval-expansion-10-manifest-v1.json`, SHA-256
`a238e4b647987ef3867d034a497136ecfa25ea36bdc774f11f84796ce6ac1d3a`;
fingerprint `42ac16acbed218be9a622741ea14e3e16311f1bd45c9c08eb9ea5c4a58ddf1ae`.
This selection is unchanged after structural preflight. No performance was inspected.

## Pipeline, fixed limits and failure gates

Compose production Miner, evidence gates, writer, deterministic trusted-partition
consolidator and index maintenance through `DurableTextualIngestor`. Retain both
historical roles as raw data. Derived owner facts must satisfy subject/source/authority
gates; assistant recommendations can be retrieved as attributed raw context, not
promoted to owner facts. Quarantine invalid-evidence drafts individually and retain
diagnostics/rejection counts; schema/provider failures still stop ingestion.

Use a new PostgreSQL schema and journal/cache namespace. Existing diagnostic-container
credentials are read only in-process; no printed/stored DSN/password. Never reset a
database or volume. Schema: `public_memory_8704aac0e8a2`. No new Graphiti writes.

Compare **raw_vector_reranked / memory_vector_reranked / combined_vector_reranked**:
local BGE-small-zh-v1.5, 512 dimensions; same local bge-reranker-v2-m3 on CUDA,
8,192-token pair cap, batch size 1. Fixed candidate cap 80, final items 20,
serialized-context cap 24,000 UTF-8 bytes; combined gets one shared cap, not two.
Do not silently replace failed CUDA/reranking with another configuration.
Byte budgets are matched, Reader input token counts are not claimed matched.

Read-only comparison consumes actual indexed records with Store/scope/provenance
revalidation. Candidate ordering is exhaustive existing pgvector ordering filtered
by channel before its cap. **Production natural Planner/query-engine and Graphiti
paths are not executed**; this is an extraction-to-answer composition diagnostic,
not all production retrieval features, large-scale latency or the AML host API.
English raw histories versus Chinese-local embeddings remain a declared confound.

Before live, correct the harness's lifecycle inventory check: count inactive records
as archived inventory, not eligible memory/governance claims; require their vector
entries absent, and compare confirmed query candidates to confirmed Store records.
Active index fingerprints remain required; stale inactive entries still fail.
This aligns checks with existing core lifecycle/index maintenance, not a core change
or a relaxed retrieval safety gate.

| Model stage | Lifetime new-attempt cap | Completion token cap |
| --- | ---: | ---: |
| extraction | 482 | 8,192 |
| Reader v2, ten questions x three profiles | 30 | 2,048 |
| auxiliary primary judgments | 30 | 3,072 |
| Total | **542** | per-request only |

All stages use the already tested DeepSeek v4 flash Chat-Completions provider,
json_object, temperature 0, thinking disabled, timeout 120 seconds. No retries,
mid-run model changes, paid repair or resampling. Identical requests deduplicate;
unknown usage is not zero. Durable attempt caps are not a hard total-token or exact
billing guarantee. Full ingestion and provenance/index validation are prerequisites
for retrieval and answering: partial histories never receive a finished QA score.

## Measurement and reliability boundaries

Retain per-query candidate/top-5/packed annotation provenance coverage. Derived
citations do not prove summaries retained the answer; report this distinction.
Reader v2 gets only question, reference time and its packed items, never gold,
profile name, old answer or audit result. Keep its derivation/source legality checks
structural, not semantic grading.

The new auxiliary judge reports answer correctness, citation support and contradiction,
with rationale and normalized per-record quote anchors. It does not classify
commitment or require a taxonomy-control pass. Primary counts are **provisional
same-model diagnostic labels**, not reliable ground truth; the failed v2/v2.1 gates
remain failed and their arms untouched. Unanchored/missing-required observations
are unscored and reported with denominators. Contradictory judge fields are exposed,
never silently recategorized. All answers and judgments remain available for review.

After completion, replay in a key-free process with cache-only models, retaining
Store/index checks and existing cache/ledger identities. Compare answers, judgments
and provisional summaries, and report zero new calls. The answer-stage attempted
namespace may not be rebilled; failed extraction chunks are not automatically retried.
Stop on any failure, report its actual stage, preserve artifacts, do not swap cases.

## Freeze provenance and execution

Frozen executable plan fingerprint:
`0ae31fe478f99db46bed770caf2b8e2cdc751220895c76a1ef2bbb07971869b7`.
Ignored final preflight artifact
`data/doppel/longmemeval-expansion-10-preflight-frozen-v1.json`, SHA-256
`78c849db2feb1222af885e234fddd8b805c2d97182eaf83b638f2c637e3df1eb`.
Earlier draft preflight is retained, not interchangeable with this frozen binding.
Prompt/schema, model/reranker artifacts, composition sources and input hashes are
bound. Old manifests/answers/failed gates and user-owned `uv.lock` remain untouched.

```powershell
& D:\project\.doppel-eval-cu128\Scripts\python.exe -m benchmarks.public_memory_expansion `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-10-manifest-v1.json `
  --run-dir data/doppel/public-memory-expansion-10-v1 `
  --output data/doppel/longmemeval-expansion-10-live-v1.json `
  --reranker-model-path D:/project/.doppel-eval-models/bge-reranker-v2-m3 `
  --embedding-cache-dir C:/Users/freeze/AppData/Local/Temp/fastembed_cache `
  --local-pg-container doppel-ablation-pgvector --live
```

Use a distinct output path and add `--cache-only` for replay. No secret in commands.
Offline tests cover selection/exclusion, backward compatibility, no gold routing,
three-profile completeness, fixed budgets, stopped partial histories, stale inactive
indices, quote anchoring, preserved label inconsistencies and zero-call replay.
Run tests/lint/types before the committed live execution. Do not tune from new results
and then continue to call this sample unopened; it becomes development data once run.
