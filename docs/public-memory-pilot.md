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
