# Reserved10: configuration lock before opening histories

State at registration: **not run; no score available**. Only original frozen
manifest metadata is inspected, not reserved questions/history text or answers.
Opened50 final comparison selects fusion under its predeclared rule; no other
configuration may be chosen after viewing reserved outcomes.

Selection result SHA-256:
24a8bf0c56d421d969c91c0d5eaaa85278e7e48a874d45fbc2ba8cbadd420991.
Parent manifest `longmemeval-fresh-high-config-50-manifest-v1.json` SHA-256:
661f72949426cde42855bdfa69ea23dcc3062bd6e636f80fea44731e9b651ab5.
Dataset `longmemeval_s_cleaned.json` SHA-256:
d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442.

## Immutable source cohort/order

Use exactly the10 entries whose literal partition is **`reserved-not-run`**, in
the parent manifest's order. Do not select `partition == "reserved"` (there are
no such entries), substitute cases, select on outcomes or mix diagnostic history
groups. Preserve original payload/chunk fingerprints and question reference time.

| Order | Case ID | Original raw messages | Ingestion chunks |
|---|---|---:|---:|
|1|a3045048|584|57|
|2|4b24c848|514|51|
|3|65240037|489|52|
|4|a96c20ee|489|51|
|5|35a27287|519|51|
|6|ba358f49_abs|477|48|
|7|7527f7e2|490|46|
|8|gpt4_1d4ab0c9|483|53|
|9|e493bb7c|506|51|
|10|6222b6eb|497|46|

Total5048 raw messages/506 transport chunks,9 answerable/1 predeclared negative.
Strata:2 temporal,2 knowledge update,2 historical assistant,1 multi-session,
1 preference/advice,1 owner fact,1 public-no-answer-ID. No per-type percentage
from one/two cases is a stable capability estimate. Public data and model training
exposure mean this is not proof of model-unseen independence.

## Locked single profile

- Raw-only histories, trusted user/assistant attribution, source text/timestamps
  and session order preserved. Separate scope per case; dedicated new namespace/
  PostgreSQL schema. No mutation/reset of previous benchmark databases/schemas.
- Ingest+local indexing only; no eager extraction, miner/analyzer, Graphiti,
  LLM selection or query-specific memory authoring. State clearly that this is
  the selected raw-history profile, not the whole structured-memory product.
- Same symmetric local `fastembed:BAAI/bge-small-zh-v1.5`, version0.8.0/512
  dimensions, existing cached artifact. No provider/model change for reserved.
- Existing BM25/vector equal-weight RRF60, candidate80, no lexical-only fallback.
- Same local BGE-reranker-v2-m3 artifacts/runtime6.0.1, CUDA batch1/max8192.
  Complete80-item neural order fused with retrieval order, equal RRF60, stable
  original-input ties. No source role/length/date quota or new planner heuristic.
- Final20 complete source items, same ranked-fit24000 UTF-8 JSON bytes. Reader
  sees question/reference date/original attributed source objects, not labels.
- Same ReaderV2/schema, DeepSeek-v4-flash/json_object/thinking disabled/temperature0,
  2048 output cap; same provisional task judge1024 cap. No prompt changes.

## Execution gates and budget

First freeze runner/config/source/model/code bindings. Then ingest/index full10
histories and prepare contexts locally, recording original corpus/source/index
receipts and full80 rankings. That phase uses0 paid calls. Do not count partial
history preparation as a completed reserved evaluation. No destructive cleanup;
any existing target schema must be verified or execution must stop.

Freeze actual10 Reader request hashes/context digests before paid answering.
Reader maximum10 attempts, judge maximum10, separate durable reservations before
send and raw-output caches; no automatic retry/output repair/replacement.100000
canonical request bytes/call,1000000/stage. Report actual usage/missing usage and
failures, never silently extend caps. This is a new bounded20-call evaluation,
not an extension/reuse of the already exhausted opened50 recovery budget.

Use all10 in order. Score only after selection/generation. Report answerable9
and negative1 separately, per-case failures/grades and evidence/structural checks.
An independent cache-only replay must reproduce answers/grades with0 new calls.
Do not pool with opened50 to claim a60-question independent score. Preserve any
negative result, do not tune on it, and do not claim official LongMemEval500,
AML model compliance, semantic faithfulness or publication readiness from it.

After this one profile completes, move to integration/deployment acceptance.
Further ranking/Reader/embedding changes require a new development cycle and new
unopened validation material, not retries against this reserved cohort.

## Execution supplement, frozen before opening histories

`benchmarks.public_memory_reserved_final` implements the above single profile.
It verifies selected-report/model/code/manifest/dataset identities before work,
rejects any existing target schema, uses a dedicated `reserved_final_*` schema
and `longmemeval-reserved10-final-fusion-v1` namespace. Preparation writes only
that new raw Store/vector index; QA reopens it server-read-only and validates
current originals before/after every answer. Both complete80-item orders and
candidate payloads are preserved. No data/volume/schema reset or cleanup.

Commit runner/tests before the first actual preflight. Keep code/HEAD unchanged
through prepare, answers and cache-only replay. Use the existing CUDA environment
for fixed model/runtime identity; no new model installation or download.

```powershell
D:\project\.doppel-eval-cu128\Scripts\python.exe -m benchmarks.public_memory_reserved_final --phase prepare --output data/doppel/reserved10-prepare-frozen-v1.json
D:\project\.doppel-eval-cu128\Scripts\python.exe -u -m benchmarks.public_memory_reserved_final --phase prepare --execute --frozen-preflight data/doppel/reserved10-prepare-frozen-v1.json --run-dir data/doppel/reserved10-prepare-v1 --output data/doppel/reserved10-prepare-live-v1.json
D:\project\.doppel-eval-cu128\Scripts\python.exe -m benchmarks.public_memory_reserved_final --phase answers --preparation data/doppel/reserved10-prepare-live-v1.json --output data/doppel/reserved10-answers-frozen-v1.json
D:\project\.doppel-eval-cu128\Scripts\python.exe -u -m benchmarks.public_memory_reserved_final --phase answers --preparation data/doppel/reserved10-prepare-live-v1.json --execute --frozen-preflight data/doppel/reserved10-answers-frozen-v1.json --run-dir data/doppel/reserved10-answers-v1 --output data/doppel/reserved10-answers-live-v1.json
```

Each phase/output must be new. On failure retain partial receipts/schema, report
the stage and stop; no automatic second attempt. Preparation clears provider-key
variables in its child process. Reader/judge keys remain environment-only. Cache
replay uses the same answer preflight, `--cache-only`, read-only `--cache-parent`
pointing at the successful answer directory, and fresh run/output paths.
