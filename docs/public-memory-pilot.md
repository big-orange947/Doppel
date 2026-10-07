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
