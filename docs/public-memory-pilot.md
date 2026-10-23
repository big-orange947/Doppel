# Public raw-history pilot: local embeddings first

Decision: 2026-10-06. Keep `BAAI/bge-small-zh-v1.5` (512 dimensions) and the
existing local `bge-reranker-v2-m3`; defer text-embedding-v4 until initial pipeline
defects are found. This is a development diagnostic, not a compliant AML academic
model profile, external leaderboard score or release gate.

## Current prospective run: source preparation is not answer accuracy

Delivery update2026-10-23: a runnable authenticated local AML HTTP smoke service
now uses durable raw SQLite/BM25 with immediate attributed search, restart-safe
retries, pending-write isolation and revocation revalidation. Real loopback TCP
restart test passes;12 new service tests, final full2176/33 skipped/three subtests.
The cached50 artifact,3 parent bindings and50 answer citation structures recheck
with37/50 unchanged, not new retrieval/QA scoring. No model calls or Docker action.
An explicit local-hybrid HTTP profile now connects PG/pgvector + BM25 RRF60 +
offline cross-encoder with index-readiness and pending-repair checks. Its live
PG/model acceptance is pending (Docker engine unavailable); offline fake-boundary
tests do not establish a quality gain. Full2187 passed/33 skipped/three subtests;
see the [local-hybrid delivery report](../benchmarks/reports/aml-local-hybrid-service-2026-10-23.md).
Full structured high-config HTTP/model
compliance/public deployment remain unfinished;
see the [delivery report](../benchmarks/reports/aml-service-readiness-2026-10-23.md)
and [local startup](aml-service.md). Do not submit the lexical smoke profile as
the highest-config evaluation system.

Source-grounding follow-up is complete:9 calls/27805 tokens,8/8 authored controls
match, but real windows expose2 bad completion claims from one source and1 false
rejection of a valid owner claim. No hard-filter promotion. The optional wrapper
defaults to annotation; a frozen zero-new-call replay retains all71 eligible
proposals with typed unverified reviews, preserving6 actor/source quarantines.
Time precision mismatch is flagged without erasing candidates or inventing dates.
Full2164 tests pass; no new QA score. With the deadline close, stop iterating on
review prompts and focus on runtime/profile freeze, cached fixed-cohort regression
and adapter/API smoke. See the
[full result and failure](../benchmarks/reports/source-grounding-result-2026-10-20.md).

The bounded candidate-feedback follow-up is complete: reuse and exactly replay
all8 prior source-bound views/plans, then test their4 count plans. The reported-
total case changes to lookup and recovers both4/5 assertions previously blocked
by episode filtering; other3 enumeration plans/hits stay unchanged. Final lookup
also retains2 attributed plans, not4 counted events. Four feedback calls/6761
tokens; zero new extraction/QA calls, no new answer score, byte-identical key-free
replay. Module-only opt-in, not a default promotion; see the
[routing result](../benchmarks/reports/public-memory-quantity-feedback-result-2026-10-20.md).

Opt-in Analyzer V11/Planner V3 repair is now tested on the same opened-eight
contexts: raw6/8 versus structured7/8, but the sole gain depends on provisional
judging of a conditional count, not proven new answer coverage. The stronger
engine result is a same-proposal ablation:3 December episodes recalled in
January are retained with occurrence coordinates,0 without. Two elapsed-duration
routes become lookup; reported-total routing is still wrong. Preserve discovered
decision-to-completion and time-precision-label errors.48 calls/239698 tokens,
key-free replay byte-identical; no graph/source writes or default promotion. See
the [frozen protocol](../benchmarks/reports/public-memory-event-time-plan-2026-10-20.md)
and [result with limitations](../benchmarks/reports/public-memory-event-time-result-2026-10-20.md).

The frozen opened-eight structured-memory counterfactual is complete: raw6/8,
structured6/8, one gain/one regression. Existing V10/miner/transient/Planner V2/
QueryEngine were actually exercised in an ephemeral candidate Store, not merely
mentioned in a prompt.64 candidates have no typed effective bounds; December
events described in January are rejected by interval filtering, elapsed-day
queries become event counts and reported totals are mis-gated as episodes.
Raw fallback remains unchanged; no net advantage or default promotion claimed.
48 calls/227719 tokens, no graph/source writes; key-free replay byte-identical;
full2098 tests pass. Next repair is generic event-time/quantity semantics, not
more eager graph extraction or question-specific rules. See the
[paired result and concrete traces](../benchmarks/reports/public-memory-structured-pair-result-2026-10-18.md).

Uniform logical50 baseline is complete: **37/50 (74%)**, positives30/43 (69.8%),
negatives7/7. The fixed complement scores15/20, merged with unchanged22/30,
never best-arm substitution. Raw-only BM25/vector/BGE/24KB whole-message context
and unchanged QA; not highest-config/official/independent validation. Evidence
candidate72/76 (94.7%), top20 66/76 (86.8%), packed60/76 (78.9%); expanded sample
must not inherit the old30-question97.6%@20 claim. Positive advice2/7, temporal
and multi-session4/7 each; fact7/8, assistant6/7, update7/7. New40 calls/160347
tokens; all50 QA100 successful calls/398460 tokens, excluding historical graph/
ingestion/local compute.2089 tests pass. Ten reserved histories remain closed.
See the [fifty scorecard, failures and accounting](../benchmarks/reports/public-memory-uniform-fifty-result-2026-10-18.md).

Uniform affordable baseline now completes fixed ordinals11–40 under identical
saved BM25/vector/BGE top20,24KB whole-message ranked-fit and unchanged QA:
**22/30 (73.3%)**, positive18/26 (69.2%), negative4/4; previously-unanswered27
score20/27.60 successful calls/238113 tokens, zero retries or source/model reruns.
All50 distinct histories now have some QA; only these30 have this exact uniform
baseline, so no current uniform50 score exists. Seven of eight failures already
contain all annotated turns; Reader task use, intention/decision semantics and
contextual-inference conservatism join the remaining packing/window omission.
Keep scores/defaults unchanged and ten reserved histories closed; next bring
the other20 onto the same baseline. See the
[uniform result, type scores and failure observations](../benchmarks/reports/public-memory-uniform-qa-result-2026-10-18.md).

Fresh fixed ordinals46–50 finish actual same-selector paired QA: native matched
candidate widening5/5 vs neighborhood4/5 (positive4/4 vs3/4; negative1/1 each).
Both candidate/selected pools cover7/7 annotated turns; full packed original-turn
retention5/7 vs6/7. More evidence did not fix the recommendation Reader refusal.
Keep neighborhoods optional and defaults unchanged; this is five diagnostic
questions, not general100% accuracy, a full benchmark, or AML performance.
31 new calls/578578 tokens,93.6% selector; no retries/graph calls.2067 tests pass.
The fifty diagnostic histories are now opened; ten reserved histories stay closed.
Next freeze a lower-cost general selection configuration before fresh validation,
not another unchanged whole-pool paid sweep. See the
[actual paired QA and accounting](../benchmarks/reports/public-memory-neighborhood-trial-result-2026-10-18.md).

Latest zero-LLM opened-five source-neighborhood audit completes: original80-pools
contain9/11 positive annotated turns; ±1 pre-selection neighborhoods11/11 versus
same-size native BM25/vector10/11. This is candidate availability, **not a new QA
score**; previous3/5 vs3/5 stays unchanged. Expanded/native806 total candidates
consume988815/818136 formatted bytes; no cost-free/generic recall claim. Keep
optional, document trusted source order and eligibility boundaries, then freeze
untouched native-versus-neighborhood selection/QA. Full2056 tests pass; paid0.
See [audit and same-count control](../benchmarks/reports/public-memory-neighborhood-audit-result-2026-10-18.md)
and [source-order integration](source-neighborhoods.md).

Latest prospective ordinals41-45 complete:five full S histories/2517 messages,
paired BGE/LLM QA **3/5 vs3/5**, answerable2/4 each and predeclared negative1/1.
Full annotated-turn text retained3/11→9/11; packed bytes118299→27298, not a net
provider-cost saving or proven QA gain. Preference evidence is recovered but the
Reader still refuses a recommendation; the temporal pool misses two owner turns
next to retrieved replies. Keep labels/defaults unchanged. Thirty calls/183243
tokens, zero retries;2031 tests pass. Next evaluate bounded authorized source
neighborhoods before selection, not post-selection padding or new graph authoring.
See [five-case results, source audit and actual costs](../benchmarks/reports/public-memory-prospective-selection-41-45-result-2026-10-18.md).

Latest bounded up-to20 selection completes the remaining two opened cases:
transport correct, wedding count refusal incorrect, **1/2 vs reused baseline1/2**.
All three reference wedding owner statements now survive selection and packing,
but other real wedding mentions/relative dates remain ambiguous; do not call this
a QA gain or silently force3. Eight successful calls/89402 tokens; this turn's
exact-k failure adds1 call/19378 tokens and stays failed. Keep defaults unchanged,
stop tuning these examples and next freeze a small untouched non-graph comparison.
See [actual answers, integrity and accounting](../benchmarks/reports/public-memory-bounded-topk-result-2026-10-18.md)
and [bounded selector contract](topk-selection.md).

Latest listwise smoke stopped on its first source-ranking response:79 unique
IDs for80 candidates, one omission. All three preflight candidate/source bindings
reproduced, but no new answer or quality grade exists. One call /19290 tokens;
remaining11 calls unspent, no automatic repair/retry. Full1985 tests pass. Next
use a separately frozen explicit top-k contract, not benchmark rules or a rescore
of the failed output. See [actual execution and accounting](../benchmarks/reports/public-memory-listwise-result-2026-10-18.md)
and [opt-in scorer contract](listwise-reranking.md).

Latest source-aware ablation did not demonstrate a gain: exact reused passage
baseline2/3 vs metadata+MMR1/3 provisional grades. More owner passages include
irrelevant topics; transport has useful evidence but a conservative Reader
conclusion. Keep grade sensitivity and retrieval/Reader attribution separate.
Six new calls /28402 tokens, no retries, old baseline spend preserved. New adapter
remains experimental, diversity default disabled; no expansion to fresh questions
or tuning on these cases. See [source-aware result and next decision](../benchmarks/reports/public-memory-source-aware-result-2026-10-18.md).

2026-10-18 latest: optional source-bound passage handoff is implemented. A fixed
three-opened-case whole-message/passage QA comparison yields2/3 vs2/3, not a proven
accuracy gain. Source-window omission and assistant-heavy text-only fragment
ranking remain; another transport answer succeeds with unannotated sufficient
owner evidence, demonstrating annotation-recall limits. Twelve paid calls /50335
tokens, no graph/source writes. Keep default unchanged and prioritize generic
source-aware ranking, not judge recalibration or source-ID scoring of fragments.
See [implementation and actual-answer result](../benchmarks/reports/public-memory-passages-result-2026-10-18.md).

Latest prospective continuation31–40 is complete:5103 raw messages, three arms,
no paid-provider calls. On nine answerable questions /15 labelled turns,
hybrid-reranked retrieves14/15 at20 but packs10/15 under either24KB policy;
vector-reranked packs11/15 with skip-to-fit. The opened20-question26/27 fit score
does not generalize uniformly. No post-result tuning or default promotion.
See [new ten-history result and evidence-granularity decision](../benchmarks/reports/public-memory-raw-31-40-result-2026-10-17.md).

Latest bounded comparison: existing skip-to-fit packing improves hybrid-reranked
answer-support coverage23/27 →26/27 and fully covered questions14/17 →16/17 under
the identical24,000-byte/top20 budget. All old prefix contexts reproduce exactly;
all sources remain unchanged. No new model calls or scenario-specific rules.
Keep the remaining missed turn and validate on untouched continuation before
claiming generalization; do not continue tuning the opened twenty questions.
See [fixed-budget comparison and decision](../benchmarks/reports/public-memory-packing-fit-11-30-2026-10-17.md).

Latest follow-up: the unchanged24,000-byte context budget reduces hybrid-reranked
evidence27/27 to23/27, while vector-reranked and unreranked BM25/vector retain25/27.
All160 saved rankings were source-bound and packed without new retrieval/models;
twenty read-only inventory hashes stay unchanged and a second run reproduces the
entire JSON byte for byte. No QA/default changes. The next issue is budget-aware
evidence handoff, not missing candidate evidence or justification for more graphs.
See [packing result and limits](../benchmarks/reports/public-memory-raw-packing-11-30-result-2026-10-17.md).

2026-10-17 latest: a separately frozen **raw retrieval-only** expansion on original
ordinals11–30 completed twenty full S histories /9,883 messages /eight profiles.
Seventeen answerable questions have27 labelled turns: vector-reranked finds25/27
at20 and BM25/vector-reranked27/27, but at5 the latter trails18/27 vs20/27.
BM25-only reranking ties the hybrid. Three unanswerable questions with related
history annotations are reported separately, not counted as answer support.
Zero paid LLM/provider tokens/graph calls; no Reader, judge, extracted memory or
context-packing measurement. No independent/full500/AML or100% QA claim.
See [twenty-history result, denominator and limits](../benchmarks/reports/public-memory-raw-retrieval-11-30-result-2026-10-17.md).

2026-10-17: full-history graph authoring is **paused at the user's request**.
Scope06 retains103 completed/one started projection; graph07 never started. Graph
code/data and previous receipts are preserved. Earlier high-config assessment
ends at five paired questions, not ten, with no proven stable graph uplift.

A separately frozen non-graph follow-up on fixed ordinals06–10 is complete:
raw baseline and production BM25/vector/mixed-memory reranking both score4/5,
find all six answerable labelled turns/sessions, and correctly abstain on the
single unanswerable case. Shared preference-task failure is Reader over-abstention
despite relevant evidence, not demonstrated missing retrieval. Citation judge
mistakenly calls that task refusal correct; preserve both labels. Thirty successful
calls / 135,024 tokens, no graph/source calls, unchanged source/Store/vectors,
exact empty-key replay with zero new attempts. Existing source preparation is
excluded from marginal cost; no full-fresh-corpus cost or independent score claim.
See [non-graph result and limits](../benchmarks/reports/public-memory-nograph-06-10-result-2026-10-17.md).

Historical high-config checkpoint (not the current non-graph protocol):

Latest 2026-10-15: scope 04 graph recovered within its original attempt ceiling,
all 162 projections complete and no deletions/slot repairs. Fourth paired question
correct in **both** profiles with explicitly attributed historical assistant
evidence, legal supported citations and exact empty-key replay. Full really runs
paths/exploration with clean execution, but raw also succeeds: no causal graph
uplift. Four provisional paired questions are scored (full 4/4, raw 3/4, still
third-question judge-sensitive); the first ten source histories are ready.
See [fourth paired result and current caveats](../benchmarks/reports/public-memory-fresh-high-config-scope04-result-2026-10-15.md).

Earlier same-day checkpoint, before authorized graph recovery:

2026-10-15 checkpoint: **ten** fixed histories / 499 chunks / 5,016 raw messages
are source-complete, with 7,494 provenance checks and zero failures. Original
network failure remains recorded; an explicitly approved identical-request
recovery plus 119-chunk continuation completed the prefix without tuning. Fourth
scope graph stopped at 126/162 on a separate transport error, with no QA on the
partial projection. Three paired questions are scored (provisional task judge:
full 3/3, raw 2/3; the third raw grade conflicts with the citation judge's own
correctness field). No stable graph-uplift claim or fifty-case score is granted.
See [checkpoint and failure accounting](../benchmarks/reports/public-memory-fresh-high-config-stage04-result-2026-10-15.md).

Earlier source-preparation checkpoint (superseded by the counts above):

The frozen 2026-10-13 fifty-case cohort remains distinct from the earlier opened
vector-only questions. Three histories (149/2,479 chunks, 1,464 raw messages) are
now fully ingested, source-audited and empty-key replayed. These are not three
answered questions. Highest-config Graphiti projection proceeds on each closed
source scope without waiting for all fifty histories; scope-local completion
never becomes a whole-cohort completion claim. Original query/gold fields are
withheld until that scope's graph/schema gates pass.

See [source continuation result](../benchmarks/reports/public-memory-fresh-high-config-50-stage02-result-2026-10-13.md),
[first scope graph plan](../benchmarks/reports/public-memory-fresh-high-config-50-graph01-plan-2026-10-13.md)
and [unchanged paired query execution supplement](../benchmarks/reports/public-memory-fresh-query-adapter-2026-10-13.md).
No core/prompt revision, analyzer candidate promotion, answer-conditioned graph
selection or new live control campaign is part of these operational adapters.

The first selected question now completed in both profiles: both provisional
task grades correct, its single annotated turn covered, citations legal and
anchored. The full profile really executed graph paths/exploration. Both answers
used Chinese for an English question; full execution is still `review_required`
for two retained open-conflict warnings. Exact empty-key checkpoint replay made
zero new calls. See [first paired result](../benchmarks/reports/public-memory-fresh-high-config-scope01-result-2026-10-13.md).
This is one of fifty scored questions, not an aggregate accuracy or graph-uplift
claim. The fixed cohort/configuration remains unchanged.

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

The [recovery result](../benchmarks/reports/public-memory-expansion-50-block04-recovery-result-2026-10-09.md)
replayed353 chunks and completed the failed chunk with one unchanged request.
Progress is354/2,420 chunks, with5,467 provenance checks and zero failures. The
recovery call used4,403 reported tokens; the two prior transport failures have
unknown usage. The [block05 plan](../benchmarks/reports/public-memory-expansion-50-ingestion-block05-plan-2026-10-09.md)
sets the next extraction cap at200 calls without retrieval or answer scoring.

The [final ingestion result](../benchmarks/reports/public-memory-expansion-50-ingestion-complete-2026-10-09.md)
now completes all fifty histories and 2,420 chunks. The Store contains 24,891 raw,
9,746 derived (including inactive) and 125 governance records; all 37,454 source
checks pass. The [retrieval plan](../benchmarks/reports/public-memory-expansion-50-retrieval-plan-2026-10-09.md)
freezes six raw/owner-memory/combined profiles using the existing vector index,
local reranker and unchanged 80-candidate/20-item/24KB prefix budgets. A first
attempt produced no rows because the harness assumed every derivative was an
owner record; legitimate agent derivatives are now source-validated and explicitly
counted as excluded from the owner-memory channel. All fifty cases remain selected.

The [retrieval result](../benchmarks/reports/public-memory-expansion-50-retrieval-result-2026-10-09.md)
completes 300 rows with zero paid calls: packed annotated-turn macro coverage is
92.18% raw reranked, 79.25% owner-memory reranked and 93.20% combined reranked,
over 49 questions with annotated evidence. Store snapshots match; 8,269 packed
source checks and 12,000 local reranker pairs complete, with zero truncation.
The [QA plan](../benchmarks/reports/public-memory-expansion-50-quality-plan-2026-10-09.md)
freezes five ten-question batches, the existing Reader v2/primary Judge, exact
packed inputs and a durable cap of 300 new attempts. Its preflight uses zero calls.

The [fifty-question QA result](../benchmarks/reports/public-memory-expansion-50-quality-result-2026-10-09.md)
now completes all 150 answer rows and their key-free replay. Inspection catches
the primary Judge excusing answerable refusals based on missing context. One
separately frozen reference-only regrading passes six generic controls and scores
all 150 original answers: raw 35/50, owner-memory 28/50 and combined 33/50. These
same-model task labels remain provisional; earlier inflated rates are preserved
but superseded. Two primary support-quote observations remain unanchored. All
answers/checks/grades replay with zero new calls. Strong source coverage does not
imply task completion; full Planner/Graphiti, unopened groups, competition models
and complete LongMemEval remain to be evaluated.

The [low-cost S-derived oracle diagnostic](../benchmarks/reports/public-memory-oracle-cost-result-2026-10-10.md)
and [paired response-policy diagnosis](../benchmarks/reports/public-memory-response-policy-result-2026-10-10.md)
reuse opened cases without new graph work. The paired policies each receive 6/7
task labels in both S-raw and full-session oracle contexts. Generic new-advice
instructions fix the preference refusal but also expose an oracle count regression,
S judge inconsistency and plan-to-experience overstatement. The candidate stays
benchmark-only, not a new core/default or a claimed retrieval improvement. These
small, unequal-budget diagnostics are not pooled with highest-config/AML scores.

The [official-protocol regrade plan](../benchmarks/reports/public-memory-official-regrade-plan-2026-10-10.md)
now freezes grading of the same 28 unchanged answers with the content-pinned
LongMemEval prompt and `gpt-4o-2024-08-06`. Four seven-question hypothesis files
retain original IDs; source/gold go only to scoring. Free exports/preflight pass,
with no new Reader, graph or retrieval work. Live scoring awaits an appropriate
channel/key and is capped at 28 attempted requests, with no automatic retry.
Prior labels remain untouched. Official grading of DeepSeek-generated opened
answers is neither an AML-compliant run nor an independent/full LongMemEval score.

The user opted to keep DeepSeek Flash. The separately frozen
[DeepSeek prompt regrade](../benchmarks/reports/public-memory-deepseek-prompt-regrade-result-2026-10-10.md)
completed all 28 unchanged answers: four arms each 6/7, zero old-label changes,
7,298 reported tokens, and identical key-removed zero-call replay. This reuses
official prompts, **not the official GPT-4o model**; same-family judge agreement
does not establish correctness or resolve the known count/safety ambiguity.
Official grading remains available but deferred. Next work is generic Reader
policy controls, not further repeated judging or eager S graph expansion.

The [grounded Reader V2 controls](../benchmarks/reports/grounded-reader-v2-controls-result-2026-10-10.md)
complete 18 fresh outputs but reject the candidate: manual frozen-rubric results
7/9 candidate vs 8/9 baseline, with speaker inversion, language drift and an
abstention-flag issue retained. Quote anchoring verifies review provenance, not
independent semantic correctness. Paired QA is blocked before paid calls; no
default is promoted. Full regression now passes 1,658 tests plus three subtests,
with 33 skipped. Next reference-Reader work should try an explicit language and
speaker output contract, not more domain-specific rules or repeated long prompts.

### Bounded query-time analysis, not more Reader policy tuning

The [attributed-content contrast](../benchmarks/reports/aml-evidence-representation-result-2026-10-10.md)
preserves source labels through the actual AML content exporter but does not fix
the local Reader's speaker inversion. No candidate/default promotion follows.

The subsequent [query-time proposal plan](../benchmarks/reports/public-memory-lazy-proposal-plan-2026-10-10.md)
and [result](../benchmarks/reports/public-memory-lazy-proposal-result-2026-10-10.md)
reuse the already-opened first temporal/update questions' exact saved S raw
contexts. Two existing reference-analyzer/miner calls create 16 candidate proposals;
four Reader outputs complete, with zero new graph/retrieval/Store/Judge work.
One temporal answer becomes coherent and reference-matching; the update baseline
was already correct. All four answers still drift into Chinese. Candidate path
tokens are 29,412 vs direct 13,374 (2.20x), not an unqualified low-cost quality gain.
Key-removed replay matches all rows/diagnostics with zero new calls.

No effective interval is extracted, and old/new project values both remain
`current`: the missing downstream temporary temporal interpretation is visible,
not silently solved by the analyzer. This route augments raw evidence and does
not claim a complete governed timeline or causal/as-of replay. Next work should
reuse generic governance/time capabilities with source clocks preserved, followed
by a modest preregistered temporal/update expansion. Do not resume costly S-wide
eager analysis or continue this local Reader-policy loop. Public SDK defaults and
persistent personal-memory analysis remain unchanged.

The [read-only transient view](transient-memory-view.md) now exposes original
source observation spans versus unknown/explicit effective intervals and reuses
the existing consolidator for unapplied advice. The
[fresh four-call contrast](../benchmarks/reports/public-memory-transient-view-result-2026-10-10.md)
reuses all 16 cached proposals without extraction: both fresh arms answer both
opened cases, so no additional task success is shown. One retrospective observation
caveat becomes explicit; an advisory slot conflict does not force refusal. All
claims/raw sources remain available, none is promoted or retired. Input tokens
increase 19.16%; key-removed replay matches all views/rows with zero new calls.
Do not keep tuning these two cases. Expand a modest preregistered diagnostic
cohort next; persistent analysis, recall ranking and default policies are unchanged.

The [five-case source-order expansion](../benchmarks/reports/public-memory-transient-cohort-result-2026-10-13.md)
now completes 5 shared analyses and 10 Readers, without new retrieval or graph.
Manual non-independent coherent task completions are 3/5 plain versus 4/5 indexed:
one calendar-time reasoning correction, no incremental update/refusal success.
A unique-count reference task remains unresolved because raw statements conflict;
preserve faithful uncertainty separately from task completion. Its analyzer also
omits the six-count assertion despite source availability, leaving no advisory
conflict in the proposals. Sixty-three candidate proposals all lack effective
bounds; index input overhead is 30.54%. Key-removed 15-hit replay matches every row,
view and checkpoint. Next prioritize generic extraction-preservation controls and
versioned analyzer work, not repeated tuning of these cases or default promotion.

The [V8/V9 preservation controls](../benchmarks/reports/analyzer-preservation-controls-result-2026-10-13.md)
now run 16 extraction calls on eight unrelated synthetic controls with no task
Reader/Judge or old-cohort execution. V8 prompt/default stays byte-identical;
V9 is explicit opt-in. Manual frozen-rubric passes 4/8 vs 7/8; the candidate's
all-eight gate remains false. Two unmarked changes no longer receive invented
correction markers in V9, with different advisory downstream behavior, but both
models split two compatible coat attributes rather than producing one enriched
draft. No information loss is demonstrated by that split. Preserve the failure,
unverified negative-statement revision markers and date precision caveats; settle
generic atomic-slot semantics prospectively instead of forcing a format or
rewriting this rubric. No default promotion or original shoe-omission fix claim.

The [new atomicity controls](../benchmarks/reports/analyzer-atomicity-controls-result-2026-10-13.md)
freeze a prospective independent-property contract without editing the old coat
fixture. Sixteen new analyzer calls produce V9 6/8 versus opt-in V10 7/8 under
new rubrics: agent disagreement no longer becomes an owner retraction, but both
arms fail same-occurrence episode enrichment. No facts are shown lost there;
details survive in separate episode drafts with one event key. Keep the failure,
date-bound/type variability and temporal denial caveats. V8 remains default and
both old/new gates remain false. Input overhead 19.75%, 24,887 tokens total; exact
16-hit zero-key replay. Next inspect event-level grouping/count/detail retention
without model calls rather than looping on prompts or rerunning old task cases.

The [zero-model event audit](../benchmarks/reports/event-consolidation-audit-result-2026-10-13.md)
confirms distinct-key counting already avoids duplicate detail records, but catches
destructive custom merges that keep only one sentence and deterministic merges that
ignored occurrence keys/bounds under a shared topic. Episode consolidation now
requires identical declared-identity/content/temporal snapshots (consolidator V5),
including execution-time validation of legacy plans. Complementary details remain
active. Optional read-only grouping retains all eight actual saved episode claims
and sources, with declared identity still advisory. Neither failed analyzer rubric
is rescored; no new extraction/Reader/Judge or external database calls occur.

The [prospective highest-config cohort](../benchmarks/reports/public-memory-fresh-high-config-50-plan-2026-10-13.md)
now freezes 50 previously unused questions plus ten new reserved histories, excluding
80 prior/opened/reserved groups. Selection uses public type/ID and complete source
histories, with question/gold/evidence annotations removed. Two profiles only:
production full high-config and raw-vector-reranked baseline, fixed Reader/judges/
context caps. There are 25,002 source messages / 2,479 ingestion chunks, and at
most 400 later QA calls; graph/type-schema budgets require actual source inventories
and separate binding. Docker/CUDA/models are ready but the new corpus is empty.
The first committed source supplement permits 49 attempts for the first history,
with no graph/QA calls or default/algorithm tuning. Report progress and failures
without mistaking source preparation for answer accuracy or a full-500 score.

The [first fresh source result](../benchmarks/reports/public-memory-fresh-high-config-50-stage01-result-2026-10-13.md)
now completes the first new history: 49/49 chunks, 474 original messages, 216
personal memories and six conflict records, with 747 source checks/zero failures.
Eleven drafts are quarantined (nine mixed-actor, one unknown evidence, one subject
mismatch), not semantically repaired. Source/vector inventory is current at 696/696.
Forty-nine calls use 247,047 tokens; key-removed journal replay makes zero calls
and reproduces audits. Overall progress is 1/50 source histories, not a scored
question. Continue the frozen new-cohort materialization/graph/QA stages, not another
prompt-control loop; old scores/reserved groups remain unchanged.
