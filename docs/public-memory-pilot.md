# Public raw-history pilot: local embeddings first

Decision: 2026-10-06. Keep `BAAI/bge-small-zh-v1.5` (512 dimensions) and the
existing local `bge-reranker-v2-m3`; defer text-embedding-v4 until initial pipeline
defects are found. This is a development diagnostic, not a compliant AML academic
model profile, external leaderboard score or release gate.

## First completed step: offline LongMemEval projection

`benchmarks/public_longmemeval.py` prepares the
[official cleaned LongMemEval](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned)
source format. The first target is `longmemeval_s_cleaned.json`, not the
evidence-only oracle file. Pin the downloaded bytes by SHA-256; the upstream main
branch can change. Preserve upstream attribution and license information.

The adapter explicitly selects raw roles, content, session identities and dates.
It preserves ALL historical turns, including assistant-side text, and does not
decide that either transport role is a verified owner fact. It passes no answers,
`has_answer`, evidence-session labels, categories or reference summaries to memory
writes or natural-language queries. Those labels exist only in a separate
`ScoringCase`; never pass the containing `PreparedCase` into a production backend.
Source IDs become scope-local opaque IDs; identical session names in different
samples cannot collide. Repeated source IDs within one sample use occurrence
ordinals as well, preserving both copies instead of overwriting either one.
Query text/date changes do not condition memory writes.

Blank string turns remain in the raw projection but are not sent to the nonblank
text-ingestion contract. `IngestionChunk.source_turn_indices` maps transport
message positions back to original turn positions; downstream write ledgers must
retain that map for evidence scoring. This decision never reads `has_answer`.
No placeholder content is synthesized, and no assistant-side text is dropped.

Dates preserve time-of-day and explicit UTC offsets. Naive upstream dates use a
declared UTC benchmark-calendar assumption, not an inferred speaker timezone or
the current computer clock. All turns in a session receive its source session
timestamp: the adapter does not invent individual turn times. A local
`QueryInput.reference_time` retains the supplied question date. AML Search has no
such field; using this local context requires a separately declared benchmark
protocol, not a hidden oracle-time injection into the AML profile.
Source sequence is preserved even when timestamps are not sorted. Sessions later
than the question reference time are counted, not silently removed. The temporal
evaluation policy must be declared before any quality run; passing this format
check does not resolve when evidence should have been available to an agent.

Run the preflight after separately obtaining the official public file:

```powershell
cd D:\project\Doppel
.\.venv\Scripts\python.exe -m benchmarks.public_longmemeval `
  --dataset data\public-benchmarks\longmemeval_s_cleaned.json `
  --limit 3 `
  --output data\doppel\longmemeval-local-preflight-next.json
```

For complete schema coverage, use `--limit 500` and a **new output filename**.
The CLI will not overwrite previous reports or its source input. It runs no
Embedding, LLM, database, graph, retrieval, answer or paid API operation. It reports
source hash, session/message/chunk counts and projected history hashes, without
answer text or raw message content. It explicitly sets `quality_metrics_available`
and `publication_ready` to false. A prefix selection is a format check only, not a
representative quality sample. Its 20-message batching is deterministic local
batching; AML's additional word-count boundary is not implemented or claimed.

Tests use synthetic schema examples, not copied benchmark questions:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_public_longmemeval.py tests/test_aml_contract.py -q
```

## Actual source preflight, 2026-10-06

The official cleaned S file was downloaded from the public dataset repository.
The 277,383,467-byte snapshot has SHA-256
`d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
All 500 cases passed the **format/projection check**, with these source observations:

- 23,867 session occurrences and 246,750 raw turns;
- 246,738 nonblank transport messages in 24,129 local Add chunks;
- 13 repeated source-session IDs within samples, preserved as separate occurrences;
- 12 blank turns in seven samples, retained in raw input and explicitly not indexed;
- 211 samples contain adjacent timestamp inversions (3,167 inversions total);
- 76 samples contain sessions after the question reference time (1,475 such sessions).

These findings corrected adapter assumptions, not production retrieval rules.
The original data, order, dates, questions and scoring answers were not rewritten.
No sample was excluded to make the format check pass. In particular, the final
two temporal observations are **unresolved evaluation-protocol questions**, not
proof that either Doppel or the dataset has incorrect temporal reasoning.

The ignored local artifact is
`data/doppel/longmemeval-local-preflight-full-v1.json`. It contains hashes/counts,
not raw conversations or gold answer text. The earlier three-case preflight was
made before occurrence-aware identity handling; it is retained as an earlier
observation, not interchangeable with this final projection. No embedding, LLM,
retrieval or QA execution was performed, so there is **no new recall score**.

## What must still be built before reporting retrieval quality

1. Compose actual raw event persistence, reference analysis/consolidation,
   local-vector indexing and graph projection; no preseeded gold memories or edges.
   Give both historical roles explicit attribution. Do not remove assistant evidence
   or reclassify it as verified owner information merely to improve scores.
2. Add a durable write ledger, bounded per-stage provider budgets, request caches
   and interrupted-ingestion recovery. Fully account for dropped/rejected drafts.
   Persist chunk-to-original-turn mappings. No Add success until index completion
   and Store validation.
3. Run the production natural Planner and candidate/path/reranker functions, not
   oracle intent/entity/time fields. Record local reference-time availability.
4. Score retrieval against upstream evidence annotations only in the scoring
   process, with separate turn/session metrics and explicit denominators. Freeze
   source-order and question-relative time semantics before interpreting temporal
   scores; do not selectively discard later background sessions. Do not
   conflate any one evidence hit with complete multi-session evidence coverage.
   Labels need not describe every alternative valid piece of evidence.
5. Add a frozen reader/scorer outside Doppel. Align retrieved-token budgets and
   candidate counts across comparisons; QA and retrieval are separate metrics.
   Upstream evaluator/configuration changes must be declared.

First real execution should use a few **complete histories**, not shortened
haystacks. Before inspecting quality, freeze selected IDs, random seed and grouped
development/holdout selection. Holdouts sharing the same history must stay in the
same group. Expand only after scope, provenance, chronology, completeness and
cost accounting pass. Do not reconstruct synthetic "blind" data by iterating
generation/review until it passes.

LongMemEval-S is English; local BGE-small-zh is a Chinese baseline. Low recall may
reflect language mismatch as well as pipeline defects. Preserve this result and
later change only the embedding configuration in a paired comparison, rebuilding
both document/query vector namespaces rather than mixing incompatible vectors.

LoCoMo's original public release is a separate future adapter. Its original and
Refined versions, licenses, category rules and multimedia/text projections must
not be silently substituted for one another.

## Durable composition and preregistered pilot, 2026-10-07

`integrations/aml/ingestion.py` now composes the existing production
`PersonalMemoryMiner`, `ProposalWriter`, `ConsolidationRunner` and `IndexMaintainer`.
The host injects the analyzer/model, consolidator and real index writers. The
authoritative Store can be file-backed SQLite or a transactional/paginated Store
such as PostgreSQL; non-SQLite callers must bind a trusted, non-secret, stable
`store_identity` to the database/schema. This declaration does not prove a custom
Store's durability. This round exercised **real SQLite, fake models/indexes**; it
did not verify a live PostgreSQL/vector/Neo4j composition.

This is an ingestion component, **not a completed AML Search backend or server**.
`IngestionCompletion` is deliberately not `WriteReceipt`: reported index
maintenance completion does not itself prove retrieval/answer correctness.
Keep core role/state policies intact; specifically:

- Role attribution is explicit host configuration (`role_actors`), not something
  inferred as verified owner identity from an incoming `role="user"`. The personal
  owner-chat pilot binds user to owner and historical assistant to agent. Contact
  attribution needs a richer trusted speaker binding and is not implemented here.
- Both roles remain in raw storage. Original text is retained even where
  `ChatMessage` normalizes surrounding whitespace. Excluding an input role or
  truncating a chunk is an error, not silent successful ingestion.
- Extracted claims still pass subject/source-actor and scope gates. Configuring a
  proposed lifecycle state does not change source authority. Default core
  extraction policy is unchanged. Assistant evidence needs an attributed context
  retrieval channel; do not lower owner-fact gates to pass assistant-side questions.
- Raw event IDs, extracted proposals and bound consolidation plans are persisted
  before later stages. Successful-stage replay does not re-extract. Raw provenance
  is reloaded from the exact authoritative Store; index loss is repairable, but
  missing raw evidence is an explicit failure, not fabricated/reinserted history.
- SQLite checkpoints commit separately from a coordinator transaction. Cooperating
  local processes sharing the journal/coordinator have one writer. A competing
  writer fails before model calls; process termination releases the coordinator
  lock. This is not distributed multi-host locking, nor protection against direct
  external Store mutations. A later chunk in a scope waits for its pending predecessor.
- Provider response caching is **still required** for the crash interval between a
  successful model response and proposal-plan persistence. Do not claim exactly-once
  billing from the write journal alone. Invalid-draft/low-confidence rejection
  accounting is also a remaining live-execution gate.

The subprocess crash test exposed and fixed a core fingerprint defect: extractor/
Miner `allowed_source_actors` was JSON-serialized as an unordered set, producing
different checkpoint identities under different Python hash seeds. It is now
sorted before hashing. **Compatibility note:** old host checkpoints/caches may
carry the former noncanonical fingerprint. Preserve them; use a new diagnostic
namespace or an explicit audited migration, not automatic deletion or bypass of
profile checks. Different hash-seed subprocesses now verify stable fingerprints.

The manifest generator is zero-model and refuses to overwrite a prior plan:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_memory_pilot `
  --dataset data\public-benchmarks\longmemeval_s_cleaned.json `
  --output data\doppel\longmemeval-local-pilot-manifest-next.json
```

Fixed source snapshot: the SHA-256 recorded above. Fixed seed: `20261007`.
The generated local manifest is `data/doppel/longmemeval-local-pilot-manifest-v1.json`,
fingerprint `6f9f01932b6a93e5edabbfba412af724ab9c78a762db5f94e3ddcd33de90c9fc`.
It records chunk/event-to-original-session/turn mappings without query/answer text.
The selected diagnostic cases are `50635ada`, `0100672e`, `cc539528`: **145 sessions,
1,513 raw turns, 147 complete-history Add chunks**. Three other history groups are
reserved and not executed. Exact full-history groups are kept together; selection
does not consult questions, answers, evidence labels or categories. One session
content is shared across selected groups; the reserved set is explicitly **not
claimed as independently blind**. Do not select replacement cases after seeing scores.

Freeze the native local temporal protocol as: ingest the **entire supplied
haystack in source order**, retain every source timestamp, and use `question_date`
only as the question's calendar reference—not as an implicit history arrival
cutoff. The upstream [LongMemEval instructions](https://github.com/xiaowu0162/LongMemEval)
describe answering after all supplied sessions. This local choice does not assert
that the cleaned file's date inversions or later timestamps are correct; it avoids
silently editing the provided benchmark. Report those properties separately and
do not translate this into an AML `question_date` field.

At this manifest/ingestion stage, no live model or retrieval result existed. The
next section records the subsequent **raw-context-only** execution. Full extracted
memory, reranker, raw-derived graph projection, natural Planner/path retrieval and
reader/answer scoring remain unexecuted. Earlier oracle-seeded recall numbers must
not be copied onto this raw-history evaluation.

## Raw-context baseline and accounting, 2026-10-07

`benchmarks/public_memory_runtime.py` reuses the existing content-addressed raw
provider cache and adds a SQLite WAL/FULL ledger. Limits bind a non-secret run/stage
identity and stable provider name/version. Reserve attempts atomically before
provider generation; timeout, failure, cancellation and unresolved post-crash
reservations are **not refunded**. Instance-local duplicate requests are serialized;
different instances can still duplicate misses, but share the durable total cap.
Invalid cache envelopes fail without another provider call. Cache-only misses also
fail before reaching a provider. Successful raw JSON is cached even if downstream
draft validation rejects it, allowing schema/projection diagnostics to be replayed.

These are attempt and canonical request-JSON byte caps, **not a tokenizer-based
hard cap or an exact-billing guarantee**. Configure the provider's completion cap
separately. Wire `ledger.observe_usage` to the provider's usage callback: observed
input/output/total tokens are reported; missing or partial usage is explicit and
never reinterpreted as zero spend. A returned provider result is not proof of a
successful extraction/index/answer stage. Cache write failure after a paid response
is still a surfaced uncertainty; this is not exactly-once billing. Cache files hold
raw model outputs, so treat the ignored local cache as potentially sensitive data.

`ReferencePersonalMemoryAnalyzer` now optionally emits content-free per-response
valid/invalid draft counts and validation error types; it no longer logs arbitrary
model-supplied extra-field names. Bad top-level shape remains a hard stage failure.
The observer is observational and does not change extraction versions/proposals;
hosts must persist/report it with stage identities, and distinguish replay from
new responses when aggregating. Miner checkpoints include valid-draft,
low-confidence and exact-duplicate counts. Evidence/subject violations still fail,
rather than silently disappearing into a success count. Core authority/state
defaults were not weakened.

`integrations/aml/context.py` retrieves historical dialogue as an explicit context
channel, independent of personal-fact query results. Source roles, authority,
session, source event and timestamp are returned from the exact authoritative
Store after provenance reload. Stale/unconfirmed/orphan/unresolved records are
rejected and counted; scope violations fail. Optional rerankers can change order,
not fabricate evidence or rewrite its text/authority. Both user and assistant
evidence remain available without granting assistant claims owner-fact authority.
This is repository host composition, not an AML server or completed Search backend.

The raw-only runner is reproducible with a local PostgreSQL DSN supplied in the
`DOPPEL_PUBLIC_PILOT_PG_DSN` environment variable (do not commit the credential):

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_context_baseline `
  --dataset data\public-benchmarks\longmemeval_s_cleaned.json `
  --manifest data\doppel\longmemeval-local-pilot-manifest-v1.json `
  --output data\doppel\longmemeval-raw-context-baseline-next.json `
  --embedding-cache-dir C:\Users\freeze\AppData\Local\Temp\fastembed_cache
```

It verifies the frozen manifest/source hash and selection, then ingests only the
three diagnostic histories. The three reserved histories are not run. Original
roles, full histories, unsorted dates and source-turn positions are preserved.
Use a new output path: source, manifest and previous results are never overwritten.
The dedicated schema is `public_raw_6f9f01932b6a`; no database/schema/volume is reset
or deleted. Data and vectors remain for resumption/diagnosis.

Actual ignored artifact: `data/doppel/longmemeval-raw-context-baseline-v1.json`.
**145 sessions, 1,513 raw records, three queries, real PostgreSQL/pgvector and local
FastEmbed BGE-small-zh-v1.5 (512 dimensions), zero LLM calls/tokens.** The table uses
micro-averaged annotation coverage: five annotated turns and five annotated session
occurrences across three queries. It does not count any alternative valid evidence
as a false positive solely because it lacks the upstream annotation.

| Raw-only profile | Turn recall@5 | Turn recall@20 | Session recall@5 | Session recall@20 | Queries covering all annotated sessions@20 |
| --- | ---: | ---: | ---: | ---: | ---: |
| PostgreSQL lexical Store search | 0/5 | 0/5 | 0/5 | 0/5 | 0/3 |
| Local vector | 2/5 (40%) | 4/5 (80%) | 4/5 (80%) | 5/5 (100%) | 3/3 |
| Lexical + vector RRF | 2/5 (40%) | 4/5 (80%) | 4/5 (80%) | 5/5 (100%) | 3/3 |

There were 480 candidate Store/provenance revalidations across the two vector-backed
profiles (80 per query/profile), with zero rejected candidates in this run. This
alone is **not an adversarial isolation benchmark**; cross-scope/orphan/reranker
guards have separate synthetic tests.

The lexical result is a concrete baseline limitation: PostgreSQLStore currently
uses case-sensitive `strpos` with the entire supplied query, not BM25/FTS or a
natural-language keyword planner. All three full questions produce no lexical
candidates. Thus this run's RRF ranking is equivalent to the vector-only ranking;
it is **not evidence of an independently useful hybrid gain**. Preserve the failed
baseline when adding a generic lexical strategy. Do not add question-specific
keywords or preseed entity/time/intent fields.

Session coverage is not exact-turn completeness: case `50635ada` covers both
annotated sessions but misses one annotated source turn at top 20. The other two
cases need deeper ranks to recover their additional source turns. This is why
session-only "100% recall" must not be advertised as perfect memory performance.
Three questions are too few for a robust overall quality claim, and English
LongMemEval is not the strongest language setting for the Chinese BGE baseline.

No extractor, graph, natural Planner, reranker or answer reader was run/substituted
in this baseline. There is no QA accuracy, formal AML score or publication claim.
Recorded search timings include serial Store/provenance checks and are not the
highest-config GPU latency benchmark. Next, add generic lexical candidates and the
declared reranker, then compose bounded real extraction/derived-memory/graph and
natural planning against the same frozen histories, with a separate reader scorer.

## Generic lexical candidates and local reranking

The [2026-10-07 comparison](../benchmarks/reports/public-context-bm25-rerank-result-2026-10-07.md)
adds opt-in `doppel_memory.lexical.BM25RetrievalStrategy`. It implements the existing
`RetrievalStrategy` protocol and can be injected as
`HybridRetrievalStrategy(..., lexical_strategy=BM25RetrievalStrategy())`. No Store
capability/default/root API is silently changed. The module-only reference reads
each complete filtered scope per query, so its corpus and page limits are strict
and it is **not** an indexed/scalable replacement for production full-text search.
Its tokenizer uses NFKC/casefold word tokens and basic Han unigrams/bigrams; it
does not perform Chinese word segmentation, stemming, synonym/alias expansion,
translation or domain intent recognition. BM25 returns candidates, not facts.

Opt-in local BGE ordering uses the existing bounded personal-memory score
validation. It receives request-local candidate IDs, the raw question and candidate
content only. It cannot choose scopes, write memories or raise source authority.
Failures/limits stop the reranked profile instead of masquerading as execution.
The context retriever now exposes the authorized candidate-window IDs for
scoring-only analysis and rechecks selected Store snapshots after ordering.
Returned role/source/original text remains authoritative; intervening deletion,
expiration or record change is counted and not returned.

Using the existing CUDA evaluation environment/model directory:

```powershell
& D:\project\.doppel-eval-cu128\Scripts\python.exe -m benchmarks.public_context_baseline `
  --dataset data\public-benchmarks\longmemeval_s_cleaned.json `
  --manifest data\doppel\longmemeval-local-pilot-manifest-v1.json `
  --output data\doppel\longmemeval-raw-context-bm25-rerank-next.json `
  --embedding-cache-dir C:\Users\freeze\AppData\Local\Temp\fastembed_cache `
  --with-bm25 `
  --reranker-model D:\project\.doppel-eval-models\bge-reranker-v2-m3 `
  --reranker-device cuda --reranker-max-length 8192 --reranker-batch-size 1
```

Set the local diagnostic DSN in `DOPPEL_PUBLIC_PILOT_PG_DSN` first. Model loading
is local-only; no new model installation, account/key access or paid LLM call is
needed. Preserve existing outputs. The three reserved histories remain unrun.

The vector candidate pool already contained all five annotated turns, although
top-20 output missed one. Reordering this pool moved all five into top five in
this **three-question opened diagnostic**. BM25 and BM25/vector reached four of
five at top five; adding reranking to those pools did not improve that aggregate.
Do not promote one profile to the framework default based on these tiny results.
Next: compose bounded real extraction/derived-memory/graph and natural planning,
then compare extracted memory, raw context and their combination under a frozen
reader/evidence budget. Validate broader generalization without adding special
rules for already opened questions.

## Bounded real extraction and ingestion

`benchmarks.public_memory_ingestion` composes the production extraction, proposal
writes, deterministic consolidation and index-maintenance host with PostgreSQL
and the same local BGE/pgvector profile. The
[frozen ingestion plan](../benchmarks/reports/public-memory-ingestion-plan-2026-10-07.md)
separates this stage from subsequent graph/Planner/search/reader measurements.
Default execution is a zero-provider/database preflight; explicit `--live` is
required for extraction. The input is the same complete-history manifest, not
gold-seeded memories. An invocation-bound partial prefix is **not** a complete
history or an opportunity to score partial evidence as a full benchmark.

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_memory_ingestion `
  --dataset data\public-benchmarks\longmemeval_s_cleaned.json `
  --manifest data\doppel\longmemeval-local-pilot-manifest-v1.json `
  --output data\doppel\longmemeval-memory-ingestion-preflight-next.json `
  --model deepseek-v4-flash --base-url https://api.deepseek.com
```

After configuring the diagnostic DSN and API key in process environment variables,
add `--live --max-new-chunks 3`, a new report path, the existing local embedding
cache directory and optionally `--api-key-env DEEPSEEK_API_KEY`. Keep the same
`--run-dir` and fixed `--max-calls 147` when resuming. Completed chunks revalidate
provenance/repair indexes without repeating extraction. Failed stage checkpoints
and raw response caches remain for diagnosis; the first failed chunk stops the run.
Do not change the model/output cap/policy in place or delete a checkpoint to retry.

The host's audit exposes content-free per-chunk stage/analysis/proposal counts.
Missing analyzer observations are explicit. Schema-valid drafts are not necessarily
safe proposals; source-actor/evidence violations still fail. The benchmark host
explicitly confirms attributed proposals after these gates; core defaults stay
candidate and assistant claims stay agent_output. Actual Store record/evidence
counts are audited separately from proposal counts and semantic correctness.
No retrieval or QA metric is emitted by this runner, even after all 147 chunks.
With `--live --max-new-chunks 0`, only completed chunks are revalidated, the
structured model is cache-only, and no API key is read or required. Pending/new
chunks are not attempted. This is a zero-paid-call restart check, not additional
history ingestion.
For a failed chunk whose provider JSON already exists, `--live --cache-only
--max-new-chunks 1` may attempt it from that cache without reading a key or issuing
an LLM request. Invalid/missing cache still fails, and evidence gates still apply.
Store audits classify conflict markers separately as governance records; they
are not owner facts. An audit failure preserves the earlier ingestion stop as a
separate field instead of hiding the original failed stage.

### Opt-in batch evidence quarantine

The default still fails the whole chunk on unsafe evidence. A separate opt-in
`--evidence-error-policy quarantine` profile rejects only unsafe drafts and records
their closed reason counts and schema-valid analysis-list indices. It never changes
citations, subject identity or authority. Top-level schema/provider/storage/index
errors still fail; existing per-draft schema rejection is unchanged. Accepted
proposals plus low-confidence/duplicate/evidence rejections must
reconcile with all schema-valid drafts. An all-rejected chunk preserves raw events
and records zero accepted proposals, not "correct extraction" or "noise only".

Use a **new run directory** for the changed policy; the fixed plan gives it a new
PostgreSQL schema. Keep the old failure, journals and raw outputs. The
[quarantine replay plan](../benchmarks/reports/public-memory-quarantine-plan-2026-10-07.md)
freezes this host-only change before execution. Strict read-only cache reuse keeps
the same provider/model/request identity and fails on missing or invalid entries
in cache-only mode, without reading a key or making a model request:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_memory_ingestion `
  --dataset data\public-benchmarks\longmemeval_s_cleaned.json `
  --manifest data\doppel\longmemeval-local-pilot-manifest-v1.json `
  --output data\doppel\longmemeval-memory-quarantine-cache-next.json `
  --run-dir data\doppel\public-memory-ingestion-quarantine-v1 `
  --model deepseek-v4-flash --base-url https://api.deepseek.com `
  --embedding-cache-dir C:\Users\freeze\AppData\Local\Temp\fastembed_cache `
  --evidence-error-policy quarantine `
  --read-only-cache-dir data\doppel\public-memory-ingestion-v1\provider-cache `
  --live --cache-only --max-new-chunks 8 --max-calls 147
```

The first eight cached chunks yield 50 schema-valid drafts: 49 accepted proposals,
one mixed-source rejection, no low-confidence/duplicate drops. All 86 raw events
remain, with one separately audited governance record. The old profile remains
failed at chunk eight; the new profile has processed 8/147 chunks with zero new
provider calls. Source checks do not verify semantic truth. This is still a partial
opened diagnostic, not a new blind test, extraction-quality score or AML result.

### Consolidation trusted-partition revision

A later unchanged-profile continuation stopped at chunk 37 because the v3
deterministic consolidator grouped two different trusted kinds into one conflict
decision. The execution guard correctly refused it. V4 partitions both keyed and
unkeyed groups by actor/authority/kind; no runner gate or analyzer prompt is relaxed.
See the [v4 plan](../benchmarks/reports/public-memory-trusted-partition-plan-2026-10-07.md)
and [regression report](../benchmarks/reports/public-memory-trusted-partition-result-2026-10-07.md).

The old journals remain bound to v3. Use a new run directory
`data/doppel/public-memory-ingestion-quarantine-v2`, the same quarantine option and
two repeated `--read-only-cache-dir` options pointing to the original fail-batch
and quarantine-v1 provider caches. Cache-only regression reprocesses all 37 saved
responses with zero model calls, retaining the 392 raw events and 175 accepted
proposals. Only after this regression should the unchanged remaining 110 chunks
continue. Neither the saved prefix nor its source checks are a retrieval/QA score.

The committed v4 continuation subsequently completed **all 147 chunks** for the
three diagnostic owners: 1513 nonblank raw messages, 599 accepted derived memories,
4 governance records and 19 explicitly rejected drafts. Store/source audit:
2291 checks with zero failures. New-model usage was 110 calls / 557,750 reported
tokens; the prior 37 outputs were reused without another extraction call.
Zero-provider new-process replay of all 147 completed chunks preserved the exact
audit, Store counts and provider ledger. This finishes ingestion of the opened
pilot histories, not the full 500-case benchmark or a recall/answer-quality score.
This complete corpus enables the following raw/memory/combined retrieval comparison.
Reader/token budgets, reserved groups and AML model migration remain separate stages.

### Completed raw / memory / combined retrieval diagnostic

The [frozen comparison plan](../benchmarks/reports/public-memory-comparison-plan-2026-10-07.md)
and [actual result](../benchmarks/reports/public-memory-comparison-result-2026-10-07.md)
reuse this completed namespace without reingestion or reindexing. Same BGE/pgvector
profile, 80 candidates per route (combined shares the cap), at most 20 final items
and 24,000 serialized UTF-8 bytes. Local BGE-reranker actually runs on authorized
item text only; no answers/category/annotated evidence enter retrieval/reranking.

For the three already opened questions and five annotated turns, raw and combined
reranked outputs both cover 5/5 sources; owner-memory-only covers 4/5 citations.
The missing source is a historical assistant recommendation, not an owner fact.
Combined output uses 20.7% fewer JSON bytes than raw reranked output in this pilot,
but no reader has verified equal answer quality or token use. Derived citations
also do not prove that summaries preserved answer information. Two recalled airline
status summaries both retain `current` labels: metadata truth/temporal QA remains
unmeasured, even though the source-bearing text is retrieved.

CLI requires the manifest, completed ingestion report, run directory and existing
PG DSN environment variable. It preserves output files and fails on partial history,
source/profile mismatches, stale vector entries or a changed Store snapshot:

```powershell
& D:\project\.doppel-eval-cu128\Scripts\python.exe -m benchmarks.public_memory_comparison `
  --dataset data\public-benchmarks\longmemeval_s_cleaned.json `
  --manifest data\doppel\longmemeval-local-pilot-manifest-v1.json `
  --ingestion-report data\doppel\longmemeval-memory-trusted-partition-complete-replay-v1.json `
  --run-dir data\doppel\public-memory-ingestion-quarantine-v2 `
  --output data\doppel\longmemeval-memory-comparison-next.json `
  --embedding-cache-dir C:\Users\freeze\AppData\Local\Temp\fastembed_cache `
  --reranker-model-path D:\project\.doppel-eval-models\bge-reranker-v2-m3
```

This is an exhaustive small-corpus retrieval diagnostic, not the complete production
query engine, a scalability/latency benchmark, answer-quality score or AML result.
The next stage is a fixed reader/judge comparison on the packed outputs, with gold
isolated to scoring and explicit token bounds, before extending unopened histories.

### Unified reader and judge on the frozen rows

The [frozen answer plan](../benchmarks/reports/public-memory-answer-comparison-plan-2026-10-07.md)
and [actual result](../benchmarks/reports/public-memory-answer-comparison-result-2026-10-07.md)
add `benchmarks/public_memory_answer_comparison.py`: one reader prompt and schema for
all profiles, one judge prompt and schema, identical generation settings, and a
deterministic citation check against each row's own packed context. Reader input is
the question, the benchmark reference time and that row's packed items only; the
reference answer reaches the judge but never the reader. Citation legality is code,
while correctness and citation support are judged independently.

On the same opened rows: **10/18 answers correct, 18/18 citations legal, 17/18
citations supported**, 4/18 reader abstentions. 31 new provider calls (16 reader, 15
judge; 73,872 reported tokens) produced the live report; a separate-process
`--live --cache-only` replay reproduced every answer and judgment with zero new calls
and no API key. The two `50635ada` abstentions are a packing loss (no Silver item in
those contexts), not reader or temporal failure; the memory-only `cc539528` rows
cannot answer an assistant-recommendation question because their channel holds no
assistant text, and no assistant reply was promoted to an owner fact; the
`0100672e` arithmetic failures are reader conservatism over fully retrieved facts.
The same model served both reader and judge, and its near-identical labels differed
on near-identical answers, so this is a diagnostic comparison, not an independent
or publication-ready score.

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_memory_answer_comparison `
  --dataset data\public-benchmarks\longmemeval_s_cleaned.json `
  --manifest data\doppel\longmemeval-local-pilot-manifest-v1.json `
  --comparison data\doppel\longmemeval-memory-comparison-v1.json `
  --comparison-sha256 a152356232524db418bcdcc9b6104f9ce90c8d94627338effd379440e7195ae7 `
  --output data\doppel\longmemeval-answer-comparison-v1.json `
  --run-dir data\doppel\public-memory-answer-comparison-v1 --live
```

Add `--live --cache-only` to replay an existing run directory without a key. The
runner refuses a different comparison hash, a manifest mismatch, an incomplete row
set, an existing output path or a changed plan, and never re-retrieves, writes a
Store or expands a source.

Also see the [Judge v2 plan](../benchmarks/reports/public-memory-judge-v2-plan-2026-10-07.md):
`benchmarks.public_memory_answer_judge_v2` re-scores the preserved Reader v1 answers with
five orthogonal dimensions, per-record citation judgments, verbatim quotes bound to one
record each, absence claims checked against the complete supplied context, and row-level
support derived by code so a no-claim answer is `not_applicable` and never counted as
supported. The judge never sees profile names, original judge labels, audit conclusions
or the reader's abstention flag, and no reference-answer phrase check decides answer
presence.

The [result](../benchmarks/reports/public-memory-judge-v2-result-2026-10-07.md) records
the first real-model run: the six frozen controls consumed six calls, four matched all
five dimensions, and the gate **failed** on two rubric ambiguities (the refusal taxonomy
branch and the scope of "I have no record"). Per the frozen rule the preserved-rows arm
was not executed; its calls are unspent and no rows-arm result exists. The proposed
v2.1 derives the conflicting-premise escalation in code, closes the claims-scope
definition and leaves the control expectations unchanged. Six controls cannot validate a
judge, and a passed gate would not have proven it correct on the opened questions.

### Independent audit of the reader/judge rows

The [audit report](../benchmarks/reports/public-memory-answer-audit-2026-10-07.md) and
`benchmarks.public_memory_answer_audit` re-read the preserved answers with **no model
call**: the tool binds the live report, the comparison artifact and the dataset, and
every auditor quote or context presence/absence claim is re-verified before it counts.
The original judge is treated as evidence, not truth.

Five of eighteen labels change. Rows 9–11 convey the correct derived value with a
"not stated directly" caveat and were rejected while the near-identical row 8 was
accepted; one row (7) refuses on a premise its own cited item contradicts; rows 0/4
abstain because packing lost the reference value; rows 14/15 report a real channel gap
and their support is `not_applicable` rather than true/false. Revised totals: 13/18
answer correct, 13 supported + 1 partially + 4 not applicable, one contradiction and
one abstention-flag inconsistency. The report also freezes the reader/judge v2 design,
22 synthetic controls across eight groups and a proposed 42-call cap. At that audit
stage nothing was re-retrieved, re-ingested or rewritten, and no v2 code was run.
The subsequently frozen judge-only v2/v2.1 plans supersede that proposed next-round
budget; the historical audit does not describe actual later calls.

### Bounded Judge v2.1 revision: stopped at the failed gate

The [v2.1 plan](../benchmarks/reports/public-memory-judge-v21-plan-2026-10-08.md)
was committed before execution. Its
[result](../benchmarks/reports/public-memory-judge-v21-result-2026-10-08.md)
records six completed control requests, **four of six matching all frozen labels**,
and a **failed gate**. C3 now meets the conflicting-premise commitment rule through
host composition of model observations, with the original model label retained.
C2 supplies the right derived answer but is classified `committed` instead of
`hedged_derivation`; C4 still treats a scoped no-record report as a factual claim,
giving `unsupported` rather than `not_applicable`. The diagnostic scope flag does
not overwrite support. The controls and their expectations were not changed.

Only six new calls and 12,469 provider-reported tokens were used out of the fixed
30-attempt plan. The 18-row arm was blocked before provider/ledger creation, and
the six citation-order stability cases were not run. A separate key-free
`--live --cache-only` replay matched all model outputs, labels, metrics and gate
with zero new calls. Execution completed; exit 1 represents the failed semantic
gate, not an HTTP failure. No Reader, core algorithm, retrieval, reserved history,
Store or index changed, and no new score exists for the 18 preserved answers.

These are opened development controls, not independent judge validation. Text
anchors prove where a quote appears, not that a semantic judgment is correct.
This bounded round stops without another prompt revision to chase taxonomy labels.
Further measurement needs a new plan that exposes disputed auxiliary categories
without retroactively changing this failed gate, then returns to Reader/context
quality and unopened-history coverage. This is not a full LongMemEval or AML result.

### Reader-v2-only development comparison

The [Reader v2 plan](../benchmarks/reports/public-memory-reader-v2-plan-2026-10-08.md)
and [actual result](../benchmarks/reports/public-memory-reader-v2-result-2026-10-08.md)
return to Reader behavior without retrying the failed Judge gates. The new Reader
receives exactly the same packed contexts and all generation settings as v1, with
generic instructions for justified derivation, scoped absence, partial answers,
effective versus observed time, source authority and question language. Its optional
`derived` block names the input sources; legality is checked but semantic support
and arithmetic are not automatically scored. Baseline answers and gold are not
sent to the Reader. No retrieval, extraction, Store, index or reserved history runs.

Eighteen outputs completed via sixteen new requests, using 66,772 reported tokens.
A separate key-free cache-only replay matched outputs, derived blocks, checks and
metrics with zero new calls. All eighteen are structurally valid, seven include
derived blocks, and four keep abstained flags. These are not success counts:
`answer_correct` and `citation_supported` remain null. Most English questions still
receive Chinese answers, and one arithmetic row still withholds the requested
per-item value; no prompt resampling or post-run repair was used. A source-bound
semantic review and separately frozen unopened-history measurement remain future
stages, not implied by this completed development run.

### Ten new histories: first live attempt stopped in extraction

The [expansion plan](../benchmarks/reports/public-memory-expansion-10-plan-2026-10-08.md)
was committed before paid execution as `e1fa179`. It selects ten new exact-history
groups while excluding all six old pilot groups, keeps full histories, and plans
three fixed-budget reranked channels: raw, derived and combined. This uses real
production ingestion and local PostgreSQL/pgvector; it does not exercise the
production natural Planner or Graphiti retrieval path. Question-type metadata is
used only for sampling, not sent to extraction or the Reader.

The [actual result](../benchmarks/reports/public-memory-expansion-10-result-2026-10-08.md)
is **stopped**, not a completed performance comparison: 232 of 482 chunks complete,
four whole histories and most of the fifth. Extraction attempt 233 failed after
reporting 8,192 output tokens, exactly its cap. Truncation is the leading diagnosis,
but the original finish reason and failed raw response were not retained; the
report does not pretend to recover those missing observations. All 233 calls have
usage, totaling 1,208,023 tokens. Successful outputs and the pending journal remain
available; no automatic retry, prompt revision or subset scoring followed.

The partial Store audit has zero provenance failures, but does not certify semantic
accuracy. Forty-five drafts were quarantined by actor/evidence qualification and
one draft failed schema validation; these observations are not hidden as zero loss.
Retrieval, reranking, Reader and auxiliary Judge stages were not reached, so there
is no new recall/QA metric. The next stage is a separately bound, observable recovery
on the same selected histories, not another Judge-taxonomy calibration loop or a
case-specific tweak. Old scores, failed gates, reserved data and `uv.lock` remain
untouched. This is not a full LongMemEval, independent blind or AML result.

### Explicit one-attempt recovery observation

The [recovery plan](../benchmarks/reports/public-memory-recovery-observation-plan-2026-10-08.md)
and [result](../benchmarks/reports/public-memory-recovery-observation-result-2026-10-08.md)
preserve the original failure, clone its checkpoint into a fresh namespace, use a
new one-call ledger and keep parent caches read-only. Closed error/HTTP/finish
metadata is now available without retaining sensitive response or exception text;
legacy failure details are not fabricated. Docker must be opened manually by the
owner if unavailable, not auto-launched by these workflows.

The unchanged request succeeds with 6,340 output tokens and 10,388 total tokens.
232 prefix chunks are revalidated with no extra extraction, then pending chunk 233
completes. Its 32 schema-valid contact-subject drafts are all quarantined because
their evidence speakers are owner/agent. This is an attributed third-party coverage
boundary, not proof that the claims are false; raw evidence is preserved. The
observer stops with 233/482 chunks complete and 249 remaining. Aggregate accounting
retains the original failed attempt: 234 calls and 1,218,411 reported tokens.
No retrieval/Reader/Judge score exists. Continue only with a new remaining-work
binding, then measure all three channels; do not score a selected completed prefix.

### Same ten histories: completed retrieval and QA diagnostic

The [continuation plan](../benchmarks/reports/public-memory-continuation-10-plan-2026-10-08.md)
was committed as `3be1764` before execution. Its
[result](../benchmarks/reports/public-memory-continuation-10-result-2026-10-08.md)
completes all 482 chunks and all ten histories, then immediately measures all
thirty raw/derived/combined reranked rows. A generic completed-prefix operation
revalidates the exact journal payloads and every source record before new
extraction, reconciling the index once per scope instead of once per chunk.
Normal ingestion/replay behavior remains unchanged. No semantic gate or
case-specific exception was weakened.

Macro annotated-source-turn coverage in packed contexts is 95% raw, 80% derived
and 100% combined, with shared candidate/final-item/context-byte budgets. This
is provenance coverage, not proof that summaries retained every answer-bearing
fact. Source validation has zero failures across 7,450 checks. All thirty Reader
outputs have legal citation IDs and valid structure, but semantics remain separate.

Original auxiliary correctness labels are 7/10 raw, 8/9 derived (one quote-anchor
failure), and 9/10 combined. **These are not validated accuracy estimates**:
bounded inspection finds two answerable memory-only refusals and one combined
refusal accepted as correct. The combined channel improves two actual answers
over raw and preserves assistant information that the derived owner-fact channel
cannot provide. Count aggregation, excessive refusal, language drift and a
plan-versus-current-fact reference ambiguity remain open. Old outputs, scores and
failed Judge calibration gates are unchanged; no new tuning follows this result.

This continuation uses 307 new calls/1,560,223 reported tokens; the complete lineage
including the original failed attempt and recovery is 541 calls/2,778,634 tokens.
It is small public development, not full LongMemEval, independent blind or AML
evaluation, and does not execute the production natural Planner or Graphiti.
A separate key-free cache-only replay matches all thirty retrieval rows, model
outputs/checks, request identities and summaries with zero new calls. Original
parent artifacts, call ledgers and cumulative accounting remain unchanged.

### Zero-provider rank-fit packing diagnostic

The [packing plan](../benchmarks/reports/public-memory-packing-plan-2026-10-08.md)
was frozen as `797c735` before the local execution. Its
[result](../benchmarks/reports/public-memory-packing-result-2026-10-08.md)
compares the unchanged prefix strategy against an opt-in whole-item fit scan.
Both consume the same eighty-candidate reranker ordering and share final20/24KB
caps, without text editing, source expansion or authority changes. All thirty
original baseline rows reproduce exactly and every baseline item is preserved.

Sixty retrieval rows complete with zero provider calls/tokens. Five contexts
add ten items, but annotated-turn coverage does not improve: raw95%, memory80%,
combined100% for both packers. This is a null coverage result, not a QA gain.
The experiment remains opt-in; neither this harness's default nor the production
query engine changes. Input hashes remain unchanged, 1,573 Store/source checks
complete and the local models score2,400 pairs without truncation.

The subsequent [same-Reader plan](../benchmarks/reports/public-memory-packing-reader-plan-2026-10-08.md)
was committed before execution; its
[result](../benchmarks/reports/public-memory-packing-reader-result-2026-10-08.md)
reuses twenty-five exact outputs and runs only the five changed requests. Five
new calls consume30,759 tokens; thirty rows have legal citations/valid structure,
four answer strings change, but there is no demonstrated answer benefit. The
writing-count case still refuses a definite total. No new Judge or correctness
score executes. A key-free replay matches all outputs/checks/request identities
with zero new calls and unchanged parents. Default packing remains unchanged.

### Fifty new histories: selection and bounded ingestion

The [new plan](../benchmarks/reports/public-memory-expansion-50-ingestion-plan-2026-10-08.md)
freezes fifty diagnostic histories and ten reserved histories, excluding all
nineteen earlier selected groups. It contains24,891 raw turns and2,420 chunks;
six type strata have8--9 questions each. Only one question is labeled no-answer,
so this cannot support a reliable refusal rate. Shared session content also
precludes an independent-blind claim. Do not reseed or replace cases after results.

The first invocation permits only94 new chunks, representing two complete
histories, in a fresh PG schema and durable namespace. Full fifty-question
retrieval/Reader/scoring has not executed; its scoring harness requires a separate
freeze. The old thirteen measured questions remain the actual completed QA
coverage, not sixty-three. Reserved histories stay unopened.

The [first block result](../benchmarks/reports/public-memory-expansion-50-ingestion-block01-result-2026-10-08.md)
completes94/94 new chunks in two full histories, then stops at the invocation
boundary. The Store has924 raw records,393 derived records and4 conflict records;
1,404 provenance checks have zero failures. Of423 drafts, one is schema-invalid,
28 fail attribution gates and one is low-confidence, leaving393 proposals.
All94 calls succeed with479,138 reported tokens. Overall status remains partial:
48 histories /2,326 chunks remain before fifty-question retrieval/QA. There is
no new recall or answer-accuracy result yet.

The [second block plan](../benchmarks/reports/public-memory-expansion-50-ingestion-block02-plan-2026-10-08.md)
binds that exact checkpoint, durable ledger and cache, and permits at most200
additional extraction calls. It adds a tested continuation entrypoint with a
separate persistent budget per frozen block. No answer/query calls are part of
this stage.

Block02 stopped after36 new completions and one `transport_error`; the failed
attempt has no reported token usage. Its checkpoint remains intact. The
[recovery plan](../benchmarks/reports/public-memory-expansion-50-block02-recovery-plan-2026-10-09.md)
binds a single unchanged-request observation in a fresh checkpoint. The old
journal/cache are read-only; repeated failure ends this recovery path.

The [recovery result](../benchmarks/reports/public-memory-expansion-50-block02-recovery-result-2026-10-09.md)
completed the unchanged request on its one allowed attempt. The child validated
130 completed chunks and now has131/2,420 complete, with2,003 provenance checks
and zero failures. It used6,815 reported tokens; the preceding transport failure
has unknown usage. This remains ingestion only. The continuation entrypoint now
reconciles inherited checkpoints and the child's separate ledger.

The [block03 plan](../benchmarks/reports/public-memory-expansion-50-ingestion-block03-plan-2026-10-09.md)
continues from the recovered131-chunk prefix, binding its130 inherited chunks
separately from the one successful local recovery call. It authorizes up to200
more extraction calls and no retrieval/answer calls.

The [block03 result](../benchmarks/reports/public-memory-expansion-50-ingestion-block03-result-2026-10-09.md)
reaches331/2,420 chunks after a successful200-call block. Seven histories have
started, six are complete. The Store audit reports5,084 provenance checks with
zero failures; the pipeline has not run question retrieval or answer scoring.
The [block04 plan](../benchmarks/reports/public-memory-expansion-50-ingestion-block04-plan-2026-10-09.md)
freezes the next200-call boundary from the validated checkpoint.

Block04 stopped after22 successful new extractions and one `transport_error`,
with5,460 provenance checks and zero failures. Its failure is retained with
unknown token usage. A [separate recovery plan](../benchmarks/reports/public-memory-expansion-50-block04-recovery-plan-2026-10-09.md)
binds one unchanged-request observation in a fresh checkpoint; no automatic
retry loop or downstream scoring runs.
