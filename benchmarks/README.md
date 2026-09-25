# Doppel benchmarks

This directory contains repository-only benchmark tooling. It is not installed as part
of the `doppel-memory` package and is not a public runtime API. Store performance,
retrieval evidence quality, observable style, and semantic-index correctness remain
separate reports; Doppel does not combine them into a flattering but meaningless
"memory intelligence" score.

Development results: [2026-09-05 natural Planner replay: relation candidates and
BGE reranking](reports/relation-candidate-replay-2026-09-05.md). All six local
profiles executed; quality gates still fail. The report documents the
recall/false-acceptance tradeoff, an interval-scoring correction, and remaining
evidence-qualification work rather than claiming publication readiness.

## Chinese IM memory quality

The v1 quality lab uses a hand-labeled Chinese IM fixture with stable facts, explicit
corrections, speaker/authority traps, cross-user adversaries, explicit user-scope
expansion, long-horizon distractors, repeated evidence, and an abstention case:

```bash
uv run python -m benchmarks.memory_quality \
  --dataset benchmarks/datasets/memory-quality-zh-v1.json \
  --output benchmarks/results/memory-quality.json
```

Four deterministic baselines run over the same 10 cases, 34 messages, 13 gold
memories, and 11 queries:

- `no_memory`: no persistent context;
- `recent_window`: latest authorized messages only;
- `raw_lexical`: all authorized raw events ranked by transparent Chinese character
  n-gram cosine similarity;
- `doppel_v0_7_events`: current raw-event ingest and default Store retrieval, without
  invoking the optional extractor or consolidator stages.

Gold queries describe required evidence as groups. Any message in one group can
satisfy that fact, so repeated statements do not force a system to return every copy.
Forbidden message IDs measure stale, wrong-speaker, agent-output, and unauthorized
evidence. Out-of-scope output is a hard runner failure; same-scope stale or
wrong-authority evidence remains a reported quality defect so weak baselines can be
measured instead of making the benchmark impossible to run.

The retrieval report includes macro evidence recall, candidate precision, reciprocal rank,
abstention accuracy, forbidden hits, redundant relevant candidates, context character
count, and query/prepare latency. The dataset already includes future extraction and
consolidation gold memories, but v0.7.1 explicitly reports those dimensions—along with
answer correctness and model token cost—as `not_yet_measured`. They become comparable
only when a reference intelligence implementation exists.

v0.7.2 adds a separate extraction runner rather than changing these retrieval scores.
`run_memory_extraction_quality_benchmark()` accepts one or more
`MemoryExtractionBaseline` implementations. `PersonalMemoryExtractionBaseline` adapts
an injected `PersonalMemoryAnalyzer` to the real exact-scope history, periodic miner,
proposal, and Store path, so a local or hosted model can be evaluated without changing
the dataset or granting it direct write access.

## v0.9 personal-retrieval quality suite

`memory-quality-suite-zh-v2.json` is the draft manifest for the next held-out personal
retrieval evaluation. The suite deliberately keeps the existing v1 fixture as a
development member; it does **not** relabel those 10 cases as a new, larger benchmark.
The manifest declares publication gates of 150 cases, 1,500 messages, 150 queries, 10
users, and non-empty dev/heldout/adversarial partitions. Until all gates pass and the
manifest is marked frozen, its audit reports `publication_ready=false`:

```bash
uv run python -m benchmarks.quality_suite
uv run python -m benchmarks.quality_suite --require-publication-ready
```

The second command intentionally exits non-zero while the suite remains a draft. A
content-addressed suite fingerprint binds the manifest, every member dataset, and every
metamorphic variant.

The first generalization variant simultaneously substitutes fixture entities and
domain words while preserving message IDs, scopes, actors, timestamps, required
evidence, and forbidden evidence. Deterministic baselines must keep the same evidence
recall, ranking, abstention, and isolation metrics after substitution. This is a guard
against product code recognizing Shanghai, Beijing, cilantro, coffee, or other fixture
vocabulary. Runtime modules are also statically prohibited from importing the
repository-only `benchmarks` package.

## v0.9 personal hybrid retrieval ablation

On Windows, the local benchmark services can be checked (and existing stopped
containers started) without printing credentials or changing volumes:

```powershell
.\scripts\check-ablation-runtime.ps1 -Start
```

The preflight is intentionally non-repairing: it never resets WSL, removes a
container/volume, or rewrites Docker Desktop data. If Docker Desktop itself is not
ready, `-Start` uses the Desktop CLI and waits for the server. Existing benchmark
containers should use `restart=unless-stopped`; enable Docker Desktop's own
“start when you sign in” setting separately if automatic boot is desired.
If the current startup log contains Docker Desktop's inaccessible stale
`dockerInference` socket signature, the preflight fails early with a content-free
diagnostic instead of waiting for the generic timeout. It still does not delete or
repair the socket automatically because that may require terminating Desktop, WSL,
or a host-level filesystem repair outside benchmark authority.

The bounded relation-path adapter has a separate opt-in live contract test. It uses
unique exact-scope fixture groups, creates no Graphiti LLM/embedder, and removes the
fixture in `finally`; point it only at a disposable or explicitly authorized local
Neo4j instance:

```powershell
$env:DOPPEL_LIVE_NEO4J = "1"
$env:DOPPEL_NEO4J_URI = "bolt://127.0.0.1:7687"
$env:DOPPEL_NEO4J_USER = "neo4j"
$env:DOPPEL_NEO4J_PASSWORD = "<local-only password>"
.\.venv\Scripts\python.exe -m pytest tests/test_graphiti_relation_path_live.py -q
```

Without `DOPPEL_LIVE_NEO4J=1` the test is skipped. A passing run requires successful
one/two-hop traversal plus direction, temporal, provenance, isolation, and zero-residue
assertions; a mock-driver pass is not reported as live coverage.

After the contract test passes, run the independent oracle-path ablation:

```powershell
$env:DOPPEL_NEO4J_PASSWORD = "<local-only password>"
.\.venv\Scripts\python.exe -m benchmarks.personal_relation_path_ablation `
  --output data/doppel/personal-relation-path-ablation-v1.json
```

`personal-relation-path-ablation-zh-v1.json` is generated deterministically by
`build_personal_relation_path_v1.py`. Its 26-query draft has nine exact owner scopes,
eight answerable two-hop chains, eight one-hop controls, eight wrong-type adversaries,
one second-hop time boundary, and one orphan-provenance boundary. Two owners deliberately
receive identical “相机” entities and query text; uniqueness is enforced per scope so
the collision remains an isolation test instead of being renamed away.

The runner executes `typed_one_hop`, `typed_bounded_path`, and
`typed_one_hop_path_union` over the same preseeded rich edges and authoritative
in-memory Store records. It reports evidence recall and complete-evidence rate
separately from forbidden hits, scope leakage, expected path count, endpoint accuracy,
cleanup, and latency. A one-hop candidate may be useful related context without being
mistaken for a complete two-hop answer. No Planner, extractor, embedding model, external
HTTP request, or paid LLM is involved. Neo4j failures produce a non-zero, structured
`runtime_unavailable` report rather than fabricated metrics. The suite remains
`frozen=false` and `publication_ready=false` until independent semantic review and a
larger path/adversarial corpus are complete.

The first live Neo4j development run is recorded in
[`reports/personal-relation-path-live-2026-09-19.md`](reports/personal-relation-path-live-2026-09-19.md).
On this deliberately narrow oracle-path draft, bounded paths raised evidence recall
from 0.667 to 1.000 and complete-evidence rate from 0.500 to 1.000, with zero
forbidden hits, scope leakage, path-count failures, or endpoint failures. These are
structural ceiling measurements, not natural-language Planner or answer-quality
scores. [`personal-relation-path-ablation-result.schema.json`](personal-relation-path-ablation-result.schema.json)
versions the success and structured runtime-failure envelopes.

Candidate path widening has a separate v2 draft and does not rewrite the v1 ceiling:

```powershell
$env:DOPPEL_NEO4J_PASSWORD = "<local-only password>"
.\.venv\Scripts\python.exe -m benchmarks.candidate_relation_path_ablation `
  --output data/doppel/candidate-relation-path-ablation.json
```

`candidate-relation-path-ablation-zh-v2.json` is generated by
`build_candidate_relation_path_v2.py`. Its 36 queries preserve the nine exact owner
scopes and add eight ontology-drift recovery cases, a deliberately related-but-not-
required branch, disconnected and over-bound topology observations, the temporal
boundary, and the orphan-provenance boundary. Alternative relation groups exist only
in the dataset; the runtime compiler contains no entity, query, or scenario vocabulary.

The runner compares `strict_path`, `candidate_path`, and `exact_candidate_union` using
the real `GraphitiRelationIndex`, `RelationPathIndex`, authoritative Store reload, and
route-level RRF deduplication. Recovery recall, candidate noise, hard forbidden hits,
scope leakage, dual-route attribution, compilation rejection, cleanup, and latency are
reported separately. Per-profile graph route-query counts and aggregate compilation
counts prove that disconnected/over-bound observations were rejected before I/O. The
hard gate requires complete union evidence, full recovery of
the predeclared drift cases, zero temporal/provenance forbidden hits, zero leakage,
correct deduplication/attribution, and zero residue. Candidate noise is deliberately
reported rather than mislabeled as either proof or a security failure. The run performs
zero model calls, external HTTP requests, or paid tokens. Its envelope is versioned by
[`candidate-relation-path-ablation-result.schema.json`](candidate-relation-path-ablation-result.schema.json).
The immutable interpretation for its first live execution is recorded in
[`reports/candidate-relation-path-preregistered-2026-09-23.md`](reports/candidate-relation-path-preregistered-2026-09-23.md);
that document was committed before Docker produced any v2 result.
The [first live Neo4j report](reports/candidate-relation-path-first-live-2026-09-23.md)
records 36 completed queries, eight of eight drift cases recovered, zero forbidden
hits or scope leakage, and five occurrences of related but non-required candidates.
This is generated-topology retrieval evidence; it does not measure whether a model
can produce those candidate topologies from natural-language questions.

The downstream candidate assembly has a separate opened-corpus live ablation. It
compares independent Store lexical + PostgreSQL/pgvector retrieval, Graphiti typed
paths, and their bounded Store-revalidated union on the same 36 cases:

```powershell
$env:DOPPEL_NEO4J_PASSWORD = "<local-only password>"
$env:DOPPEL_ABLATION_PG_PASSWORD = "<local-only password>"
.\.venv\Scripts\python.exe -m benchmarks.hybrid_path_candidate_ablation `
  --output data/doppel/hybrid-path-candidate-ablation.json
```

Its fixed interpretation and gates are recorded in
[`reports/hybrid-path-candidate-preregistered-2026-09-23.md`](reports/hybrid-path-candidate-preregistered-2026-09-23.md).
This run uses dataset-supplied topology to isolate retrieval and assembly. It keeps
candidate noise separate from temporal/provenance-forbidden evidence and leaves answer
support unassessed. Both live backends are required; there is no silent degraded mode,
and the run makes no external or paid model calls.

The [first opened run](reports/hybrid-path-candidate-first-live-2026-09-23.md)
improved evidence recall from `0.900` to `1.000`, but correctly exited non-zero under
the original labels: the path-only corpus called a valid first-hop memory forbidden
when it could not prove the complete second hop. Since assembled candidates explicitly
leave answer support unassessed, V2 preregisters a domain-neutral label correction in
[`reports/hybrid-path-candidate-v2-preregistered-2026-09-23.md`](reports/hybrid-path-candidate-v2-preregistered-2026-09-23.md).
Hard authorization, lifecycle, time, scope, and provenance failures remain forbidden;
active authoritative but incomplete first-hop context is measured as related noise.
The [V2 live result](reports/hybrid-path-candidate-v2-live-2026-09-23.md) passed:
assembled evidence recall was `1.000` versus `0.900` for independent lexical +
pgvector, complete-evidence rate was `1.000` versus `0.833`, and hard forbidden hits,
scope leakage, Store-revalidation failures, path-budget omissions, and backend residue
were all zero. Per-query candidate IDs were identical to V1; only the preregistered
candidate-versus-proof label projection changed. The corpus is still opened and uses
dataset-supplied topology, so this is architectural evidence rather than a publication
or natural-language generation claim.

The first combined V1 corpus was superseded before execution when offline validation
found repeated full provider prompts across its deliberate cross-owner collisions; it
has no model or retrieval result. The corrected frozen corpus is
[`combined-retrieval-zh-v2.json`](datasets/combined-retrieval-zh-v2.json). It contains
144 queries across 36 exact owner scopes and 3,600 memories—100 per scope—with repeated
cross-owner entity names, same-scope semantic distractors, one-hop and two-hop graph
questions, semantic questions, and temporal incomplete-path adversaries. The file is
generated deterministically by `build_combined_retrieval_v2.py` (which preserves the
auditable V1 topology generator and adds unique wording) and validated by
`combined_retrieval_quality.py`. V2 preserves the same density and topology while all
144 provider inputs are unique. Its fingerprint, resumable provider-acquisition
rules, V3 candidate-path profile, and topology/retrieval gates were fixed before any
provider or live retrieval run in
[`reports/combined-retrieval-v2-preregistered-2026-09-24.md`](reports/combined-retrieval-v2-preregistered-2026-09-24.md).
This suite is provider-unseen and frozen, but not author-hidden; it is a stronger
development generalization check, not yet publication-grade independent evidence.

Topology acquisition is deliberately resumable and exposes no partial quality score:

```powershell
$env:DOPPEL_API_KEY = "<provider key>"
.\.venv\Scripts\python.exe -m benchmarks.combined_retrieval_acquire `
  --live --max-new-calls 20
```

Repeat the same command until `status` becomes `complete`. The cache manifest rejects
changes to the dataset/catalog fingerprints, V3 generator, model configuration, or
implementation commit. Only then is the first topology report written. The live
retrieval stage additionally requires the dedicated PostgreSQL/pgvector and Neo4j
containers:

```powershell
$env:DOPPEL_ABLATION_PG_PASSWORD = "<local-only password>"
$env:DOPPEL_NEO4J_PASSWORD = "<local-only password>"
.\.venv\Scripts\python.exe -m benchmarks.combined_retrieval_live `
  --gate exploration
```

The live runner refuses partial or fingerprint-mismatched topology reports and compares
independent lexical + pgvector, generated typed paths, bounded Graphiti exploration,
the typed-only hybrid, and the exploration-enhanced hybrid. It keeps topology quality,
evidence recall@5, complete evidence@10, two-hop gain, semantic recall, hard-forbidden
evidence, lifecycle/authority, scope, provenance, cleanup, context size, source
attribution, and p50/p95/p99 latency separately observable. `--gate legacy` remains the
default for compatibility with the original typed-only experiment; use
`--gate exploration` when the additive preregistered exploration gate should control
the process exit status. Both gate results are always written to the report.

Rejected candidates are reported by cause. Expected authority/lifecycle filtering is
kept separate from actual Store revalidation failures such as stale index references
or a scope mismatch after authoritative Store reload.

### Semantic overfetch and whole-memory reranking

The first bounded-exploration run isolated a weaker semantic-only slice. The follow-up
protocol in
[`reports/combined-semantic-rerank-preregistered-2026-09-25.md`](reports/combined-semantic-rerank-preregistered-2026-09-25.md)
separates candidate coverage, overfetch/backfill, and reorder-only local cross-encoder
quality without changing the 20-item final context bound:

```powershell
$env:DOPPEL_ABLATION_PG_PASSWORD = "<local-only password>"
D:\project\.doppel-eval-cu128\Scripts\python.exe `
  -m benchmarks.combined_semantic_rerank_live `
  --reranker-model D:\project\.doppel-eval-models\bge-reranker-v2-m3 `
  --reranker-device cuda
```

The runner makes no network or provider call. It fails if the baseline drifts, the
cross-encoder silently degrades, candidate membership changes, final Store filtering
leaks an ineligible record, or the preregistered quality thresholds are missed.

The first frozen live result is recorded in
[`reports/combined-semantic-rerank-first-live-2026-09-25.md`](reports/combined-semantic-rerank-first-live-2026-09-25.md).
All 36 required memories were already present inside the unchanged 64-candidate window.
Overfetch alone left recall unchanged, while local whole-memory reranking reached 1.000
Recall@1/5/10/20 and MRR with zero candidate-membership, scope, or eligibility
violations. Median latency increased from 65.6 ms to 257.2 ms. This is component-level
evidence for an opt-in highest-quality profile; the narrow synthetic semantic slice is
not a general perfect-score claim.

The complete 144-query composition test is separately preregistered in
[`reports/combined-retrieval-memory-rerank-preregistered-2026-09-25.md`](reports/combined-retrieval-memory-rerank-preregistered-2026-09-25.md).
It leaves graph paths outside the reranker and requires their one-hop, two-hop, and
temporal complete-evidence rates to remain unchanged:

```powershell
$env:DOPPEL_ABLATION_PG_PASSWORD = "<local-only password>"
$env:DOPPEL_NEO4J_PASSWORD = "<local-only password>"
D:\project\.doppel-eval-cu128\Scripts\python.exe `
  -m benchmarks.combined_retrieval_live `
  --reranker-model D:\project\.doppel-eval-models\bge-reranker-v2-m3 `
  --reranker-device cuda `
  --gate reranking
```

The first frozen full result is recorded in
[`reports/combined-retrieval-memory-rerank-first-live-2026-09-25.md`](reports/combined-retrieval-memory-rerank-first-live-2026-09-25.md).
The highest-quality profile reached 1.000 evidence recall@5 and complete evidence@10
overall and in each of the one-hop, two-hop, temporal, and semantic categories. MRR
rose from 0.616 to 0.796, with zero membership, isolation, eligibility, provenance,
time, or path-atomicity violations. The quality premium raised p50 from 150.8 ms to
419.6 ms and p95 from 192.9 ms to 542.7 ms, so reranking remains an opt-in quality
profile rather than the unconditional default.

### Heterogeneous personal-memory generalization corpus

The perfect recall above is a result on a narrow, previously opened 144-query
development corpus. It is not treated as a general Doppel quality score. The next
evaluation uses the independently generated and frozen
[`heterogeneous-retrieval-zh-v3.json`](datasets/heterogeneous-retrieval-zh-v3.json):
480 unique Chinese queries, 48 exact owner scopes, and 9,216 memories. Owner scopes
are disjoint across 120 dev, 280 sealed, and 80 adversarial queries. The corpus covers
current and historical residence, corrected facts, event-key-aware episode counts,
one- and two-hop possession relations, document facts, cross-conversation preferences,
subject corrections, and related-but-insufficient evidence.

The generator is deterministic, the dataset is synthetic and contains no real personal
data, and the contract rejects cross-scope labels, repeated full queries, invalid time
intervals, unprovenanced edges, and malformed relation gold. The corpus is author-known
and therefore remains `publication_ready=false`. V1's dev-only run exposed one label
error before any sealed/adversarial result was opened: a superseded peer claim was
hard-forbidden even though it is useful conflict context. V1 remains immutable; V2
changes only those 48 evidence roles from hard-forbidden to related and leaves every
memory, edge, entity, query text, split, threshold, and retrieval rule unchanged. The
original protocol and the V2 correction are recorded in
[`reports/heterogeneous-retrieval-v1-preregistered-2026-09-25.md`](reports/heterogeneous-retrieval-v1-preregistered-2026-09-25.md)
and [`reports/heterogeneous-retrieval-v2-label-correction-2026-09-25.md`](reports/heterogeneous-retrieval-v2-label-correction-2026-09-25.md).
In particular, related context such as “the book is held by someone” is not mislabeled
as proof of who bought it: retrieval coverage and answer sufficiency are scored
separately.

The V2 dev-only diagnostic then showed that exact episode counting cannot be evaluated
as retrieval execution unless the oracle plan supplies the same generic memory type and
topic fields that a production Planner would need to derive. V3 adds only those
structured count-plan labels; all corpus text, graph data, evidence roles, splits, and
thresholds stay unchanged. It also enables a single generic literal-entity reservation
in hybrid assembly so a named object's related context cannot be erased by an
answer-relevance reranker. The frozen V3 delta is documented in
[`reports/heterogeneous-retrieval-v3-oracle-plan-2026-09-25.md`](reports/heterogeneous-retrieval-v3-oracle-plan-2026-09-25.md).
Natural Planner quality remains a separate future track and receives none of these gold
fields.

The live runner defaults to the open dev partition. It requires real local pgvector and
Neo4j services plus the local reranker, but makes no external HTTP or paid LLM call:

```powershell
$env:DOPPEL_ABLATION_PG_PASSWORD = "<local-only password>"
$env:DOPPEL_NEO4J_PASSWORD = "<local-only password>"
D:\project\.doppel-eval-cu128\Scripts\python.exe `
  -m benchmarks.heterogeneous_retrieval_live `
  --partition dev `
  --reranker-model D:\project\.doppel-eval-models\bge-reranker-v2-m3 `
  --reranker-device cuda
```

Opening all partitions additionally requires the explicit `--partition all
--sealed-first-run` pair. The runner separately reports independent lexical/pgvector
retrieval, oracle-route Graphiti execution, bounded Graphiti exploration,
Store-revalidated assembly with and without exploration, and exploration-enhanced
assembly with reorder-only memory reranking. Oracle routes isolate graph execution
quality; they are not presented as natural-language Planner performance. Exploration
may discover related context but never claims answer support. The committed
[`heterogeneous-retrieval-result.schema.json`](heterogeneous-retrieval-result.schema.json)
binds the result envelope and safety accounting.

The final pre-sealed dev result is preserved in
[`reports/heterogeneous-retrieval-v3-exploration-dev-result-2026-09-25.md`](reports/heterogeneous-retrieval-v3-exploration-dev-result-2026-09-25.md).
On 120 open queries, the highest-quality profile reached 1.000 evidence recall@5,
complete evidence@10, related-context recall@10, and exact episode-count accuracy,
with MRR 0.958 and zero isolation, eligibility, temporal, provenance, or membership
violations. Bounded exploration raised related-context recall from 0.250 to 1.000
without treating explored context as answer proof. This remains a development result;
the all-partition first run is the independently meaningful generalization check.

That first all-partition run is preserved unchanged in
[`reports/heterogeneous-retrieval-v3-first-live-2026-09-25.md`](reports/heterogeneous-retrieval-v3-first-live-2026-09-25.md).
It passed the complete frozen gate across 480 queries and 9,216 memories: final
evidence recall@5 was 0.998, complete evidence@10 and related-context recall@10 were
1.000, and MRR was 0.933. Sealed recall@5 was 1.000; adversarial recall@5 was 0.989
with every required item present by rank 10. All isolation, eligibility, temporal,
provenance, Store-revalidation, membership, boundedness, and cleanup checks passed.
The corpus remains synthetic, author-known, oracle-routed for graph execution, and
non-publication evidence.

### Multi-instance reliability gate

Retrieval quality does not prove that shared backends remain correct when several
Agent workers run at once. `multi_instance_reliability_live.py` therefore exercises a
separate, deterministic live contract across four PostgreSQL pools, four pgvector
adapters, four Neo4j drivers, eight exact owner scopes, 128 logical records, and 512
concurrent write attempts. It verifies scope-local database idempotency, optimistic
state races, vector replay and reconciliation, typed Graphiti relation reads, stale
graph-edge suppression through authoritative Store reloads, restart recovery, latency,
and fixture cleanup. It uses local embeddings and makes no external HTTP or LLM call.

The frozen first-run protocol and limitations are recorded in
[`reports/multi-instance-reliability-v1-preregistered-2026-09-25.md`](reports/multi-instance-reliability-v1-preregistered-2026-09-25.md).
The result envelope is bound by
[`multi-instance-reliability-result.schema.json`](multi-instance-reliability-result.schema.json).
Without `--live`, the command prints the complete workload contract without reading
credentials or touching either backend:

```powershell
python -m benchmarks.multi_instance_reliability_live

# Live mode resets only the dedicated doppel_ablation database and uses run-scoped
# Neo4j groups. Set both local-only passwords in this PowerShell process first.
python -m benchmarks.multi_instance_reliability_live --live
```

This V1 gate intentionally excludes Graphiti's LLM-driven concurrent episode
extraction. It tests multi-driver typed relation retrieval and stale-edge revalidation;
provider-dependent graph ingestion belongs in a separate budgeted benchmark.

The immutable first V1 result is recorded in
[`reports/multi-instance-reliability-v1-first-live-2026-09-25.md`](reports/multi-instance-reliability-v1-first-live-2026-09-25.md).
All idempotency, isolation, lifecycle-race, search, stale-edge, reconciliation,
restart, and cleanup checks passed. The overall gate still failed: three pgvector
operations raised exceptions that V1 did not classify, and a 512-request burst reached
781 ms write p95 against the frozen 500 ms ceiling. Vector search p95 was 37 ms and
typed graph path p95 was 424 ms. V2 must improve diagnostics and resolve the generic
initialization/connection-pool behavior without rewriting the V1 observation.

The versioned V2 repair protocol is frozen in
[`reports/multi-instance-reliability-v2-preregistered-2026-09-26.md`](reports/multi-instance-reliability-v2-preregistered-2026-09-26.md).
It retains all 512 simultaneous calls and the original 500 ms write-p95 gate, adds
stage-specific vector failure accounting, uses the database-global extension lock,
and limits each of four pools to two connections after diagnostics showed that larger
pools amplify unique-key contention. V1 remains the immutable first observation; V2
is a distinct repair measurement.

The first V2 live result is preserved in
[`reports/multi-instance-reliability-v2-first-live-2026-09-26.md`](reports/multi-instance-reliability-v2-first-live-2026-09-26.md).
Every gate passed: 128 logical events under 512 simultaneous calls produced exactly
128 creates and 384 database-level duplicates, with zero isolation, lifecycle, vector,
graph, reconciliation, restart, or cleanup failures. Write throughput was about 1,508
ops/s with p95 303 ms; pgvector search p95 was 37 ms and typed Graphiti path p95 was
278 ms. The result validates the bounded local burst contract, not a long soak,
network partition, or LLM-driven Graphiti ingestion.

Natural-language path planning is evaluated on a separate draft,
[`datasets/relation-path-planner-quality-zh-v1.json`](datasets/relation-path-planner-quality-zh-v1.json).
The structural retrieval fixture above intentionally contains graph-known intermediate
relations that its short questions do not always state; using those hidden paths as
Planner gold would reward guessing. The independent Planner draft instead contains 32
questions whose expected path comes only from wording plus the governed relation
catalog: 12 explicit two-hop chains, 12 one-hop controls, and eight no-path cases.
It includes inbound traversal, nearby-relation confusions, unsupported and ambiguous
relations, non-relation queries, and an explicitly over-bound three-hop request.

`relation_path_planner_quality.py` scores whole-path exactness, hop count, per-hop type,
direction, entity anchors, missed/false path selection, forbidden nearby types, and
planner errors independently. An exception never counts as a correct no-path decision.
The dataset remains unfrozen and not publication-ready; the committed tests exercise a
gold Planner only to verify the evaluator. A real provider result must be cached and
reported separately before the experimental Planner v3 can gain execution authority.

`relation_path_planner_live.py` is the bounded provider runner for that separate
measurement. It is dry-run by default, selects only the 11-case `dev` partition by
default, makes at most one provider request per selected case, performs no retries,
and never executes a graph path. Successful raw JSON objects are stored in the same
content-addressed provider-output cache used by the earlier Planner benchmarks. Cache
hits are revalidated by the current Planner and consume zero call budget. An
authentication, rate-limit, transport, timeout, or other provider-level failure stops
the run after its first occurrence; remaining cases are recorded as not run rather
than issuing the same failing request repeatedly.

```powershell
# Preview the exact dev call topology. No key read, network client, or output file.
.\.venv\Scripts\python.exe -m benchmarks.relation_path_planner_live --max-calls 11

# Development measurement. Set the key in this same PowerShell process first.
$env:DOPPEL_API_KEY = "<provider key>"
.\.venv\Scripts\python.exe -m benchmarks.relation_path_planner_live `
  --live --max-calls 11 --partition dev `
  --output data/doppel/relation-path-planner/dev-v1.json

# Re-score the same dev provider outputs after local scorer changes: zero HTTP calls.
Remove-Item Env:DOPPEL_API_KEY -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m benchmarks.relation_path_planner_live `
  --live --max-calls 0 --partition dev `
  --output data/doppel/relation-path-planner/dev-v1-rescored.json
```

Only after the prompt/contract is frozen from `dev` should the 12 held-out and nine
adversarial cases be opened together:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.relation_path_planner_live `
  --live --max-calls 21 --partition heldout --partition adversarial `
  --min-exact-path-accuracy 0.85 --min-path-recall 0.85 `
  --min-relation-type-accuracy 0.90 --min-direction-accuracy 0.90 `
  --min-no-path-accuracy 1 --max-false-path-count 0 `
  --max-forbidden-relation-type-hits 0 `
  --output data/doppel/relation-path-planner/sealed-v1.json
```

These sealed thresholds were registered before inspecting any heldout/adversarial
provider output. Entity-mention exactness is diagnostic rather than a gate because
the current draft gold does not yet encode equivalent surface references separately.
The sealed result remains valid evidence if it fails; do not tune against it and rerun
under the same held-out label.

The first sealed run is recorded unchanged in
[`reports/relation-path-planner-v3-sealed-2026-09-22.md`](reports/relation-path-planner-v3-sealed-2026-09-22.md).
It failed the pre-registered gate because one adversarial three-hop request produced a
schema-rejected three-step draft instead of an explicit no-path outcome. Heldout was
12/12 exact; all 15 answerable one/two-hop cases had exact types and directions; no
valid draft produced a false or forbidden path. The safety boundary worked, but a
validation error is not relabeled as a correct abstention, so V3 receives no default
query-engine execution authority.

Planner V4 is a new module-only protocol, not a reinterpretation of the sealed result.
It adds explicit `execute`/`abstain` and `exact`, `ambiguous`, `unsupported`,
`over_bound`, or `nonrelation` reasons. An executable decision still requires exactly
one or two bounded steps; abstention requires empty steps, zero path confidence, and
no soft relation candidates. Host validation continues to reject malformed output and
never truncates an over-bound chain.

Because every V1 partition has now been opened, V4 evaluation over these 32 cases is
permanently labeled `opened_regression` and is ineligible as unseen evidence:

```powershell
# Dry run: 32-case topology, no key read and no network call.
.\.venv\Scripts\python.exe -m benchmarks.relation_path_decision_live

# One opened-corpus regression run. This does not create a new held-out claim.
.\.venv\Scripts\python.exe -m benchmarks.relation_path_decision_live `
  --live --max-calls 32 `
  --min-exact-path-accuracy 0.90 `
  --min-decision-accuracy 0.95 --min-reason-accuracy 0.90 `
  --min-over-bound-reason-accuracy 1 --max-wrong-execute-count 0 `
  --output data/doppel/relation-path-decision/v4-regression-v1.json
```

The regression report keeps V3 path-shape metrics and independently measures decision
accuracy, reason accuracy, execute/abstain accuracy, explicit over-bound handling,
wrong execution, wrong abstention, and invalid decisions. Passing it only qualifies
V4 for a new-corpus experiment; it does not grant graph execution authority. A new V2
dev corpus and independently unopened sealed corpus remain required.

The first opened V4 regression is recorded in
[`reports/relation-path-planner-v4-opened-regression-v1-2026-09-22.md`](reports/relation-path-planner-v4-opened-regression-v1-2026-09-22.md).
It fixed the original three-hop abstention and kept wrong execution at zero, but failed
the gate because it over-abstained on eight valid two-hop questions, rejected one valid
inbound one-hop question as ambiguous, and treated one safe ambiguous soft-candidate
result as schema-invalid. These findings informed V4 version 2; they are not unseen
quality evidence.

Every result records dataset/catalog/selection fingerprints, provider settings without
credentials, cache hits/misses, provider call budget, aggregate token usage, per-case
sanitized errors, implementation hashes, partition/category/trait metrics, and a
SHA-256 sidecar. A completed low-quality run is distinct from an incomplete provider
run. Optional exact-path/no-path thresholds affect only the report gate; they do not
change model output or scoring. Do not tune against the sealed partitions and then
describe a rerun as held out.

`personal_retrieval_ablation.py` compares the same pre-extracted fixture set across
four main execution profiles and three index-direct diagnostics. Every main profile
runs the real `PersonalMemoryQueryEngine` end-to-end (planner -> lexical/semantic
candidates -> exact-scope Store reload -> subject/authority/lifecycle/temporal
gates -> ranked hits); results never compare raw index memory IDs.

```bash
uv run python -m benchmarks.personal_retrieval_ablation `
  --dataset benchmarks/datasets/personal-retrieval-ablation-zh-v1.json `
  --profiles lexical,lexical_vector,lexical_graph,lexical_vector_graph `
  --output data/doppel/personal-retrieval-ablation.json

# strict gates for CI
uv run python -m benchmarks.personal_retrieval_ablation `
  --require-live-postgres --require-live-neo4j --require-all-profiles `
  --max-scope-leakage 0 --max-temporal-violations 0
```

Profiles are named by what actually executes: `lexical`, `lexical_vector`,
`lexical_graph`, `lexical_vector_graph`; diagnostics are `vector_direct`,
`graph_direct`, `composite_direct`. The dataset is a candidate draft (37 queries,
5 users, dev/heldout/adversarial partitions) and is **not** frozen or
publication-ready.

The `lexical_graph` profiles intentionally retain the compatibility
`GraphitiSemanticIndex` path, so this ablation can measure the redundancy and latency
of full Graphiti hybrid search next to pgvector. They are not a benchmark for the new
`GraphitiRelationIndex`. Relation-only quality requires fixtures with explicit entity
anchors, relation-bearing rich edges, and edge-level gold labels; it must not be
inferred by renaming the existing graph profile or by treating fallback edges as
relations.

The separate draft fixture
`datasets/personal-relation-ablation-zh-v1.json` provides that edge-level gold: 28
authoritative memories, 65 queries, 5 exact owner scopes, explicit entity anchors,
rich relation facts, current/history/as-of boundaries, same-name cross-scope
collisions, same-entity multi-relation distractors, colloquial paraphrases, expired
relations, unknown entities, and wrong-relation adversaries. Run the four relation
ablation paths with zero paid LLM calls:

```bash
uv run python -m benchmarks.personal_retrieval_ablation `
  --dataset benchmarks/datasets/personal-relation-ablation-zh-v1.json `
  --profiles lexical,lexical_vector,lexical_relation,lexical_vector_relation `
  --planner-modes oracle --no-metamorphic `
  --gate-profiles lexical_relation,lexical_vector_relation `
  --require-live-postgres --require-live-neo4j --require-all-profiles `
  --output data/doppel/personal-relation-ablation.json
```

`oracle` labels only intent/time/entity/relation structure; it never injects a scope,
memory ID, target entity, or topic key. `relation_final_hit_attribution` counts only
final Store-revalidated hits carrying `relation_match`, then checks them against
required/forbidden gold. Raw graph adjacency does not count as a correct contribution.
`graph_final_hit_attribution.per_mode` similarly crosses `graph_direct` edge/episode
mappings and `vector_direct` candidate IDs with final accepted hits for each Planner
mode independently. The legacy top-level `graph` / `vector` fields remain oracle-only,
so a real Planner replay cannot be mislabeled as a confound-free oracle result.
Each profile executes one discarded warm-up query before latency measurement so a
later profile cannot inherit an unfair Neo4j/provider cold-start advantage. The
dedicated PostgreSQL schema and exact Neo4j fixture scopes are both cleared in
`finally`; no benchmark fixture is retained after the run.
`hard_gates_by_profile` preserves an independent verdict for every planner/profile
pair. `--gate-profiles` selects which candidate profiles determine the process exit
code; the aggregate `hard_gates` and all weaker control failures remain in the report
and are never rewritten as passes. Omitting this option retains the legacy strict
aggregate gate across every executed profile.
The fixture remains `frozen=false` and `publication_ready=false`; it is an engineering
baseline, not public numerical evidence yet.

The expanded candidate dataset
`datasets/personal-relation-ablation-zh-v2.json` is intentionally separate from the
65-query v1 fixture that influenced runtime development. Draft.2 contains 72 memories,
240 queries, 12 exact owner scopes, and a fixed 72/96/72 dev/held-out/adversarial
split. Every query explicitly grades the entire 72-memory corpus as 0 (irrelevant or
unauthorized), 1 (useful related context but not proof), or 2 (direct answer evidence),
so nDCG can distinguish “retrieved a useful clue” from “retrieved evidence that answers
the question.” Twenty-four queries specifically have related context but no direct
answer; twenty-four use unknown entities. Draft.2 additionally labels retrieval intent
as `direct_evidence`, `related_context`, or `no_evidence`. Reports therefore expose
related-context Recall@1/5 and no-evidence abstention separately instead of treating
answer-layer uncertainty as a reason for the retriever to hide useful context. See the
[v2 annotation notes](datasets/personal-relation-ablation-zh-v2.md) and verify the
checked-in generator output with:

```bash
python -m benchmarks.build_personal_relation_v2 --check
```

The first no-LLM live structural diagnostic is recorded in
[personal relation v2 structural retrieval](reports/personal-relation-v2-structural-2026-09-09.md).
It separates direct evidence, related context, and true no-evidence behavior; its
typed-oracle result is a retrieval ceiling, not production Planner quality.
The paired fixed-Reference-Planner replay and the resulting typed candidate-ranking
change are recorded in
[personal relation v2 Reference retrieval](reports/personal-relation-v2-reference-retrieval-2026-09-09.md).

The v2 split is preassigned, not secret: the public generator and gold remain
`frozen=false` and `publication_ready=false` until an independent semantic review.
Do not tune runtime code against its held-out/adversarial cases or describe them as a
blind result. The v1 file remains available for exact regression comparisons.

With opt-in `--candidate-fusion union`, an evidence lookup whose model draft has
entity/relation anchors but empty `search_text` uses the raw question only for bounded
lexical/semantic candidate discovery. Reports expose the fallback in warnings and
query traces. This does not repair the Planner draft, change its intent/time, or grant
relation/scope authority; Planner-quality metrics must still count the empty-field
failure separately. Count queries and the default relation-gate mode are unchanged.

`--candidate-fusion anchored_union` exercises the same independent candidate pool
with an additional explicit-entity admission check. When the Planner supplies
`entity_mentions`, a hit needs a normalized literal anchor in the authoritative
memory/relation metadata or a qualified graph relation. This measures unknown-entity
false positives without turning relation hints into exact-answer judgments. Run it
as a separate report; its config fingerprint is not interchangeable with either
`union` or `relation_gate`.

Retrieval reports now use evaluation semantics v4. Runtime hits expose structured
`candidate_evidence`, but always declare `answer_support=unassessed`; only benchmark
gold assigns `judged_evidence_role` (`direct_evidence`, `related_context`, or
`non_evidence`). `accepted_candidate_pool` reports direct-evidence recall at 10/20,
while no-evidence queries report candidate-empty/nonempty rates as retrieval
diagnostics. The old `no_evidence_abstention_accuracy` field remains as a deprecated
candidate-empty alias for report compatibility and is not answer quality or a paired
Planner promotion gate. Dataset `forbidden` candidates are likewise counted and
surfaced as `candidate_diagnostics`, not treated as answer failures: the retrieval
runner has no answer model with which to judge whether the context was misused.
Scope, subject, authority/lifecycle, time, and provenance remain independent hard
gates.

The relation dataset also carries a closed, host-owned relation ontology and one
canonical relation-type label per query. `oracle_typed` selects those labels through
the same public `available_relation_types` / `relation_types` binding used by a real
host, while ordinary `oracle` continues to emit only open-vocabulary surface hints.
Running both modes over the same profiles measures the retrieval ceiling gained from
correct relation typing without crediting that gain to Graphiti or a cross-encoder.
It is deliberately an oracle ceiling, not evidence that a production LLM Planner can
choose the type reliably; Planner type-selection quality must be measured separately.

Production relation matching may expand a long Chinese hint into bounded contiguous
2-4 character fragments, but the planner-quality runner deliberately continues to
score the concise gold surface predicate exactly. This keeps planner quality honest
while separately measuring whether the retrieval adapter can recover safely. The
fragment expansion contains no fixture vocabulary and must retain zero forbidden hits
on the wrong-relation adversarial partition.

`RelationReranker` is now an injectable, text-only edge scoring protocol, but this
65-query draft does not calibrate its threshold and no checked-in result claims
cross-encoder quality. The runner now exposes distinct
`lexical_relation_reranked` and `lexical_vector_relation_reranked` profiles. They never
silently degrade into their non-reranked names: a missing model, missing threshold, or
load failure produces structured `unavailable`. `relation_reranker` runtime metadata
records model/version, the explicit threshold, and sigmoid normalization; final-hit
contributions separately count `relation_reranker` promotions. When the model is a
local directory, the report also hashes every model file into a content-addressed
manifest and records the `model.safetensors` SHA-256, so renaming or silently
replacing a local checkpoint cannot masquerade as the same evaluation.

The first local-only BGE run can be invoked after the model is available:

```bash
uv run python -m benchmarks.personal_retrieval_ablation `
  --dataset benchmarks/datasets/personal-relation-ablation-zh-v1.json `
  --profiles lexical_relation,lexical_relation_reranked,lexical_vector_relation,lexical_vector_relation_reranked `
  --planner-modes oracle --no-metamorphic `
  --relation-reranker-model BAAI/bge-reranker-base `
  --relation-reranker-threshold 0.75 `
  --gate-profiles lexical_relation_reranked,lexical_vector_relation_reranked `
  --require-live-postgres --require-live-neo4j --require-all-profiles `
  --output data/doppel/personal-relation-reranker-ablation.json
```

The threshold above is an explicit example, not a recommended default. A scorer must
ultimately be evaluated as a separate profile over an expanded frozen
held-out/adversarial set: report recall gain, newly introduced forbidden hits,
threshold sweep, latency, model identity, and failure fallback. Scope, time,
provenance, lifecycle, and authoritative Store-reload gates remain mandatory
regardless of the scorer result. The oracle run primarily tests false promotion and
safety because its gold surface relation hints already reach full recall. To measure
recovery from real Planner paraphrases, repeat the same profiles with
`--planner-modes report --planner-report <cached-report>`; report replay makes zero LLM
calls and preserves Planner failures as a separate attribution bucket.

Add `--query-trace-limit 200` to record bounded engine-stage diagnostics in each
successful case. This does not change ranking or retry failed source drafts. Trace
coverage is `engine_boundary`: it does not reveal index-internal discarded edges.
Keep diagnostic latency separate from uninstrumented baseline timing; see
[query diagnostics](../docs/query-diagnostics.md).

Model selection is deliberately an ablation, not a framework constant. The current
FastEmbed harness supports `BAAI/bge-reranker-base`, so it remains the small,
reproducible operational baseline. The next comparison matrix is:

| candidate | role | license | current harness |
| --- | --- | --- | --- |
| `BAAI/bge-reranker-base` | lightweight baseline | MIT | FastEmbed |
| `BAAI/bge-reranker-v2-m3` | multilingual quality candidate, 0.6B | Apache-2.0 | optional SentenceTransformers |
| `Qwen/Qwen3-Reranker-0.6B` | instruction-aware 100+ language candidate | Apache-2.0 | optional SentenceTransformers |
| `Qwen/Qwen3-Reranker-4B` | maximum-quality GPU profile candidate | Apache-2.0 | optional SentenceTransformers |
| `jinaai/jina-reranker-v2-base-multilingual` | research-only comparison | CC-BY-NC-4.0 | FastEmbed; never a general default |

No model is promoted from public leaderboard numbers. A candidate must win on this
dataset's heldout/adversarial partitions after threshold sweep while preserving zero
scope/time/provenance failures and not increasing forbidden hits beyond an explicitly
reviewed budget. Reports must also include p50/p95 latency, peak host/GPU memory,
model revision, score normalization, and offline availability. Doppel may eventually
publish a lightweight profile and a highest-quality profile; the public protocol
remains provider-neutral in either case.

The embedding model is a separate decision. `BAAI/bge-small-zh-v1.5` remains the
512-dimensional low-cost baseline used by the current reproducible pgvector run; its
high recall does not make it a relation classifier. Candidate replacement profiles
are `BAAI/bge-m3` (1024 dimensions; dense/sparse/multi-vector capable) and the
instruction-aware Qwen3-Embedding family. Qwen3 4B/8B native dimensions exceed
pgvector's 2,000-dimension HNSW `vector` limit, so a fair Doppel run must use the
models' supported reduced output dimension (for example 1024), record that choice,
create a new vector namespace, and rebuild the derived index. It must never reuse or
reinterpret vectors produced by the existing 512-dimensional provider.

The benchmark does not add Transformers/PyTorch to Doppel's runtime dependencies.
When `sentence-transformers` is installed in the evaluation environment, the same
runner can load those candidates explicitly. Score normalization is mandatory for
that backend because some CrossEncoder configurations expose raw logits while others
expose a provider-normalized 0..1 score. The report records the selected backend,
model, package version, revision, normalization, dimension, and query-prefix hash.
Missing packages or model files remain structured `unavailable`.

Use a current evaluation environment for these model families: the upstream Qwen3
reranker integration targets SentenceTransformers 5.4+, while Qwen3 model loading
requires Transformers 4.51+. These are benchmark-environment requirements only and
do not become Doppel runtime dependencies. A CUDA-capable machine must also install
a CUDA-enabled PyTorch build explicitly; a CPU-only `torch` wheel paired with
`--embedding-device cuda` or `--relation-reranker-device cuda` is correctly reported
unavailable and must not be presented as a GPU benchmark. Reports record the requested
device, batch size, PyTorch/CUDA versions, CUDA availability, and detected GPU name.

If Hugging Face Xet/CAS is unreachable in the evaluation network, retrying with
`HF_HUB_DISABLE_XET=1` selects the standard Hub download path. A partially downloaded
or unavailable model still remains structured `unavailable`; the runner never falls
back to another model under the requested profile name.

Example BGE v2 relation run (the threshold is deliberately illustrative):

```bash
uv run python -m benchmarks.personal_retrieval_ablation `
  --dataset benchmarks/datasets/personal-relation-ablation-zh-v1.json `
  --profiles lexical_relation,lexical_relation_reranked `
  --planner-modes oracle --no-metamorphic `
  --relation-reranker-backend sentence-transformers `
  --relation-reranker-model BAAI/bge-reranker-v2-m3 `
  --relation-reranker-score-normalization sigmoid `
  --relation-reranker-threshold 0.75 `
  --require-live-neo4j --require-all-profiles `
  --output data/doppel/relation-bge-v2-m3.json
```

Example instruction-aware Qwen3 embedding run:

```bash
uv run python -m benchmarks.personal_retrieval_ablation `
  --dataset benchmarks/datasets/personal-relation-ablation-zh-v1.json `
  --profiles lexical,lexical_vector `
  --planner-modes oracle --no-metamorphic `
  --embedding-backend sentence-transformers `
  --embedding-model Qwen/Qwen3-Embedding-0.6B `
  --embedding-dimensions 1024 `
  --embedding-query-prefix "Instruct: Retrieve personal memories that answer the query.`nQuery: " `
  --require-live-postgres --require-all-profiles `
  --output data/doppel/vector-qwen3-0.6b.json
```

`relation_reranker_threshold_sweep` is built from the raw score of every graph edge
candidate before the configured promotion gate. It maps opaque fixture edge IDs back
to gold only inside the repository benchmark and reports 0.05 increments separately
for dev, heldout, adversarial, and all. Normalization, instruction, and threshold must
be selected using dev only; heldout/adversarial rows are read after freezing them.
The machine-generated `dev_recommendation` applies one fixed rule: require zero
promoted forbidden memories and zero abstention false promotions, maximize required
recall, then choose the smallest threshold among ties. Reports also disclose tracked
dirty paths and hash the benchmark plus the complete `doppel_memory` Python source
tree, so an uncommitted implementation cannot masquerade as the recorded HEAD.

### Offline whole-candidate reranking replay

`personal_candidate_rerank_replay.py` reorders, but never adds or removes, the
authorized final candidates from one existing retrieval profile. It was used to
decide whether a cross-encoder merited the provisional runtime
`PersonalMemoryReranker` API; the replay remains the isolated before/after diagnostic.
The source report and exact historical dataset must share a fingerprint. A Git
revision can supply a historical dataset without overwriting the current draft:

```powershell
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
python -m benchmarks.personal_candidate_rerank_replay `
  --source-report data/doppel/candidate-union-experiment-20260906.json `
  --dataset benchmarks/datasets/personal-relation-ablation-zh-v1.json `
  --dataset-git-revision 6f316c3c0629ad2ad39bce4642d6862b61a4d44e `
  --planner-report data/doppel/catalog-ablation/20260903T083605Z-a794943e/definitions.json `
  --profile lexical_vector_relation_reranked `
  --model D:/project/.doppel-eval-models/bge-reranker-v2-m3 `
  --device cuda --batch-size 16 --include-planner-context `
  --output data/doppel/personal-candidate-rerank-replay.json
```

The reranker receives opaque item IDs plus authorized memory content and extracted
relation type. It cannot change the candidate set; malformed/missing score bindings
abort the run. `raw_question` and `planner_context` are separate arms. Planner context
is model-suggested retrieval context, not authority. The CLI uses a local
SentenceTransformers model and records zero external LLM calls. Report latency is
order-sensitive: the first arm includes model loading/cold start. Metrics retain the
source dataset's development/post-hoc limitations and do not measure answer quality.

The main ablation runner can now exercise the same algorithm through the real runtime
protocol by adding `--memory-reranker`. It reuses the explicitly configured local
`--relation-reranker-model` and normalization, while keeping edge-level relation
calibration observations separate. `--memory-reranker-max-candidates`,
`--memory-reranker-max-input-chars`, and `--memory-reranker-timeout-seconds` bind the
runtime call. The report records whether the stage was requested and available plus
each case's content-free reranking summary; no profile may silently claim execution
when the requested scorer is unavailable.

The first paired live runtime result is recorded in
[personal-memory-reranking-runtime-2026-09-08.md](reports/personal-memory-reranking-runtime-2026-09-08.md):
on the draft v1.5 relation set, the scorer changed no candidate membership and moved
Recall@1 from 0.88 to 0.92 and MRR from 0.91 to 0.93, while p50 latency moved from
97.608 ms to 204.837 ms. Scope, temporal, provenance, and inactive-record failures
remained zero. These are development results, not publication-ready claims.

### Natural-language relation planner quality

Retrieval ablation uses an oracle plan so graph quality is not confused with planner
quality. `relation_planner_quality.py` evaluates the real planner separately over the
same 65 natural-language questions and the same dev/heldout/adversarial partitions:

```bash
# zero-network structural baseline
uv run python -m benchmarks.relation_planner_quality `
  --planner deterministic --no-cache `
  --max-structural-failures 65 `
  --output data/doppel/relation-planner-deterministic.json

# OpenAI-compatible reference planner; credentials stay in the environment
$env:DOPPEL_MODEL = "deepseek-v4-flash"
$env:DOPPEL_OPENAI_BASE_URL = "https://api.deepseek.com"
$env:DOPPEL_SCHEMA_MODE = "json_object"
$env:DOPPEL_API_KEY = "..."
uv run python -m benchmarks.relation_planner_quality `
  --planner reference --max-calls 65 `
  --max-completion-tokens 768 --max-tokens-parameter max_tokens `
  --thinking disabled --max-relation-type-failures 0 `
  --output data/doppel/relation-planner-deepseek.json
```

The runner evaluates the structured draft before any Store/index call: exact intent,
semantically accepted intent alternatives, point-in-time or explicitly labeled
covering intervals, entity and relation recall, unexpected terms, unrequested hard
`memory_types`/`topic_keys` filters, trusted-subject binding, provider failures, and
latency. The host's closed `relation_types` ontology is passed in every request and
scored independently as exact selection, recall, precision, unexpected labels, and
out-of-ontology violations. `typed_structure_accuracy` requires both the original
surface-plan contract and exact canonical relation typing; the original
`exact_structure_accuracy` remains unchanged for comparison with older reports.
`--max-relation-type-failures` is an opt-in exit gate, so old structure-only commands
keep their previous behavior. Relation hints are scored against the concise normalized surface predicate;
an overlong phrase containing the gold term does not receive credit because it would
not satisfy the production relation gate. The reference runner caches the raw JSON
object returned by `StructuredOutputModel`, before Planner projection or validation.
Every hit therefore re-runs the current projection, calendar grounding, subject
binding, and strict validation. A successful provider response is cached even when
that current Planner rejects it, so a later implementation can be evaluated without
paying again. Provider HTTP failures are not cached. The versioned
`provider-output-v1` namespace never reads legacy final-draft entries.
`--max-calls` is checked before each actual reference-provider call, after raw-cache
lookup; it does not limit deterministic local planning. Provider token usage is an
aggregate content-free ledger. The cache fingerprint binds the structured model
identity and complete generation request—input, instructions, and output schema—but
never includes an API key. Reports identify cache kind, schema, namespace, ignored
invalid entries, and the invariant zero legacy-final-draft reads. The result contract is
[`relation-planner-quality-result.schema.json`](relation-planner-quality-result.schema.json).

### Paired Query Plan v1/v2 ablation

`query_plan_v2_ablation.py` compares the v1 Reference Planner with the opt-in
operation/time-orthogonal v2 Planner on the same 240 non-deferred relation questions,
plus an independent 72-case matrix covering all 18 `lookup/list/count × temporal_view`
combinations. Both arms receive the same v2 relation ontology, host calendar timezone,
and provider settings. It measures planning
only—no Store, index, retrieval, reranking, or answer generation is involved. Start
with the zero-network plan inspection:

```bash
uv run python -m benchmarks.query_plan_v2_ablation
```

For a live paired run, keep the credential in the process environment:

```powershell
$env:DOPPEL_API_KEY = "..."
uv run python -m benchmarks.query_plan_v2_ablation --live
```

Each run gets an immutable directory under `data/doppel/query-plan-v2/` containing
the preflight plan, one report per completed arm, a comparison report, and SHA-256
sidecars. Raw provider output is cached by complete prompt, output schema, and model
identity, so the v1 and v2 schemas cannot collide. `--max-calls-per-arm` is a hard
network-call ceiling after cache lookup; use `0` to perform a cache-only replay. The
runner stops if source/dataset/catalog identity changes between arms and sanitizes
unexpected provider failures to an exception class without persisting response text.

The relation dataset carries independently reviewed v2 `operation` and
`temporal_view` labels instead of deriving them from the legacy intent at score time.
The separate operation dataset is generated by
`build_query_plan_operations_v1.py`; `--max-calls-per-arm` defaults to 312 and remains
a hard ceiling after raw-cache lookup.

The promotion gate is deliberately one-sided: v2 must complete without reducing
valid drafts or regressing operation, temporal view/coordinates, subject binding,
entity/relation recall, or relation-type metrics. Top-level and
`orthogonal_by_partition`/`orthogonal_by_category` fields are authoritative for v2;
the old `by_partition`/`by_category` fields retain a legacy intent projection only
for historical comparison. Exit code 1 means the no-regression gate did not pass,
not that the data should be hidden. The current 240-query dataset is still unfrozen,
so no result from this runner is publication-ready yet.

The resulting v1/v2 reports can be replayed together through one local Store and
one shared set of indexes. This stage makes zero provider calls and preserves the
v2 `operation`/`temporal_view` draft instead of projecting it back to v1. The paired
modes require both files to come from the same experiment directory, verify their
shared runner/dataset/catalog identity and optional `plan.json`, and reject swapped
schema arms. They add per-profile retrieval deltas plus a conservative promotion
gate. The gate uses final ranked quality, abstention, forbidden evidence, execution,
and scope/time/provenance safety; source/effective Planner structure remains a
separate diagnostic because the upstream Planner report already scores it. For the
current relation dataset, a
full local vector/Graphiti comparison is:

```powershell
$env:DOPPEL_ABLATION_PG_PASSWORD = "<local PostgreSQL password>"
$env:NEO4J_PASSWORD = "<local Neo4j password>"
uv run python -m benchmarks.personal_retrieval_ablation `
  --dataset benchmarks/datasets/personal-relation-ablation-zh-v2.json `
  --profiles lexical,lexical_vector,lexical_graph,lexical_vector_graph,lexical_relation,lexical_vector_relation `
  --planner-modes report_v1,report_v2 `
  --planner-report-v1 data/doppel/query-plan-v2/<run>/v1.json `
  --planner-report-v2 data/doppel/query-plan-v2/<run>/v2.json `
  --candidate-fusion anchored_union --no-metamorphic `
  --require-live-postgres --require-live-neo4j --require-all-profiles `
  --output data/doppel/query-plan-v2-retrieval.json
```

This is the first result that can determine whether shorter relation hints or
overlapping `LOCATED_AT`/`STORED_IN` candidate types improve or harm accepted Top-K
memories. The earlier Planner-only gate cannot answer that question. Source Planner
failures, effective-plan failures, retrieval failures, and scope/time/provenance
safety failures remain separate in the report.

A prior paid result can be re-scored without another provider request. Replay now
requires the same dataset fingerprint and verifies per-case request fingerprints
when available. Original failure types remain failures with `error_origin=source_report`;
legacy reports without field diagnostics are explicitly marked as lacking them.
The replay report records the source path, SHA-256, original dataset fingerprint,
and `provider_calls=0`. Replay latency is local overhead, not provider latency:

```bash
uv run python -m benchmarks.relation_planner_quality `
  --replay-report data/doppel/relation-planner-deepseek.json --no-cache `
  --max-structural-failures 65 `
  --output data/doppel/relation-planner-deepseek-rescored.json
```

### Relation definitions: isolated stage-one ablation

**Execution semantics after Planner v10:** model `draft.relation_types` are now
suggestions bound to `plan.candidate_relation_types`. Exact runtime filters come
only from the host's `required_relation_types` argument (or an explicitly trusted
stored execution plan). `oracle_typed` now passes fixture gold via this host
argument in both warm-up and measured runs, preserving its meaning as a known-type
retrieval ceiling. Normal/report planners never acquire that host privilege.
Historical model drafts replay with candidate semantics under the new engine;
compare engine source hashes before attributing changes to a model.

Strict type-set scores remain unchanged and still measure the proposed labels
against storage gold, not evidence relevance. New planner reports mark
`relation_type_execution_semantics=planner_candidates_host_constraints`; their
semantic overlay calls ambiguous nonempty suggestions `ambiguous_candidate_selection`,
not observed hard-filter/security failures. Old untouched reports keep their
original labels. Graph candidate expansion, reranker relevance, and final evidence
quality must be measured through retrieval separately. The existing report-based
retrieval runner still requires valid drafts for every case; it does not silently
drop a failed case to obtain a full score.

For a fresh two-arm comparison in **one command**, run from the repository root:

```powershell
# Preview only; zero network calls, no key prompt, no output directory created.
.\.venv\Scripts\python.exe -m benchmarks.relation_catalog_ablation

# Live: uses DOPPEL_API_KEY if present, otherwise asks for hidden console input.
.\.venv\Scripts\python.exe -m benchmarks.relation_catalog_ablation --live
```

The live command runs labels-only then definitions with the same fixed DeepSeek
settings below, no cached drafts and no provider retries, at most 65 calls per arm
(130 total). Input files and implementation hashes are checked between arms; do
not edit source/catalog/dataset files while it runs. A prompted key exists only
in the child process environment and is restored/removed in `finally`, never
written in the plan, reports, command arguments, or shell history. Noninteractive
execution without an environment key fails before any calls.

Each invocation creates a unique directory under `data/doppel/catalog-ablation/`
with `plan.json`, per-arm reports, and `comparison.json` with SHA-256 sidecars.
The comparison keeps raw metrics, provider usage, post-hoc ambiguity counts, and
per-query type-success/status transitions. Existing results are not overwritten.
Ordinary quality exit 1 does not stop the second arm; authentication failure or
zero valid drafts stops further arms. `completed` means both reports were produced;
`quality_gate_passed` remains false when either arm fails the strict quality gate.
An individual invalid response remains visible, and provider completeness is
reported independently. Do not rerun merely because the final exit is 1: inspect
`comparison.json` first. Sequential single runs are exploratory, not randomized
or repeated trials, and no quality improvement is claimed by the wrapper itself.

`--relation-catalog` adds host-owned schema descriptions to every Planner request.
The JSON array is validated as `list[RelationTypeDefinition]`: canonical name,
meaning, directed source/target roles, and optional constraints. Duplicate or
out-of-allowlist names fail before provider calls. The opt-in example is
[`catalogs/personal-relations-v1.json`](catalogs/personal-relations-v1.json), covering
the fixture's 16 labels. It contains no query IDs, entity instances, per-question
labels, facts, or answers; the same complete catalog is passed to every query.
It is a host vocabulary example, **not** a mandatory Doppel ontology. Its definitions
were authored after the initial evaluation: results on the existing, repeatedly
inspected 65 questions remain exploratory, not new held-out evidence.

Stage one changes only schema information and accompanying instructions, not draft
output fields, retrieval/ranking logic, dataset gold, scoring, or quality gates.
Ambiguous predicates still permit empty types. Definitions describe constraints;
they do not cause the engine to infer relation equivalence or validate edge endpoint
types, and do not automatically configure Graphiti extraction.

```powershell
# Offline wiring check: no Docker, GPU, or provider credentials required.
.\.venv\Scripts\python.exe -m benchmarks.relation_planner_quality `
  --planner deterministic --no-cache `
  --relation-catalog benchmarks/catalogs/personal-relations-v1.json `
  --max-structural-failures 65 `
  --output data/doppel/relation-planner-catalog-offline.json

# Real definitions arm: set DOPPEL_API_KEY in this same PowerShell beforehand.
# Use a NEW output path for each experiment; do not overwrite the old 44.6% report.
.\.venv\Scripts\python.exe -m benchmarks.relation_planner_quality `
  --planner reference --model deepseek-v4-flash `
  --base-url https://api.deepseek.com --schema-mode json_object `
  --relation-catalog benchmarks/catalogs/personal-relations-v1.json `
  --max-calls 65 --max-completion-tokens 768 `
  --max-tokens-parameter max_tokens --thinking disabled `
  --semantic-review benchmarks/datasets/relation-planner-semantic-review-zh-v1.json `
  --max-relation-type-failures 0 `
  --output data/doppel/relation-planner-deepseek-catalog-v1.json
```

A fresh labels-only control uses the same command with `--relation-catalog` omitted
and a different output path. Both arms together are at most 130 planner calls; each
arm has its own 65-call cap, with provider retries still disabled. Keep the model,
token cap, temperature, questions, and scoring identical. Preserve first-pass
failures; do not repeatedly retry until success and call that improved reliability.
The deterministic offline check does **not** demonstrate an LLM quality gain.

Reports include `relation_catalog` (mode, full definitions, count, canonical SHA-256),
and the complete definition content participates in request/cache fingerprints.
Replay of a definitions report requires the same `--relation-catalog`; missing or
changed definitions cannot be re-scored as if the provider saw a different input.
Old labels-only report fingerprints remain replay-compatible only with their original
dataset and Planner versions. Historical v9 reports can be replayed without paying
again, but must not be presented as fresh control runs.

Planner v12 additionally distinguishes mutable present state from enduring
attribution/provenance, represents imprecise calendar periods as intervals, and asks
for the smallest supported relation-type candidate set. Its Reference boundary treats
provider output as untrusted: schema-known fields are projected, unknown fields are
inert, and recognized values still undergo strict type and temporal validation. The
only temporary incomplete state is `intent=as_of` without `as_of`: it may reach the
host's domain-neutral explicit-numeric-calendar grounding and must pass complete draft
validation immediately afterward. Ambiguous, relative, invalid, or multiple dates are
not repaired, and every other temporal/type invariant remains strict. This execution
ordering changes no prompt, schema, or provider request fingerprint. An object with no
recognized field remains invalid. Historical v8-v11 reports remain
versioned exploratory references, not concurrent controls for v12; do not attribute
every between-run fluctuation to the new instructions.

Dataset v1.5 corrects two gold-label defects found by the first v12 live run: the
“last year” repair query now requires the complete 2025 interval, and the passport
renewal-date query is an enduring lookup rather than history. Query text, relation
gold, fixtures, and provider inputs are unchanged, so this is a scoring correction,
not a prompt improvement. See the immutable run note in
[`reports/relation-planner-v12-live-2026-09-08.md`](reports/relation-planner-v12-live-2026-09-08.md).

`output_diagnostics` records truncations, invalid drafts, safe validation-code
counts, and explanation length percentiles/over-80 counts for valid drafts only.
No valid drafts yields null length statistics; truncated output lengths are unknown,
not zero. The 80-character instruction is not a new rejection/scoring rule and
does not change replayed drafts. No automatic repair/retry or output-cap increase
is included in this revision. Measure first-pass validity and truncation alongside
relation quality before deciding whether to change either.

Compare strict type scores **and** explicit-relation omissions, ambiguous hard
filters, entity/time accuracy, invalid drafts, usage, and latency. The optional
semantic overlay remains post-hoc and cannot change strict scores or gates. A
nonzero quality exit is expected when failures remain; the report is still written.
Only after this isolated comparison should soft type candidates/ranking changes
or model replacements be tested. New predeclared held-out data is still required
before making generalized quality claims.

Scoring version 3 distinguishes point-in-time accuracy from interval presence and
boundary accuracy; a calendar month/year can no longer pass by choosing an arbitrary
representative date. Reviewed alternative open-interval day boundaries remain
explicit dataset gold. It also preserves the v2 distinction between valid, failed,
and not-run cases. An authentication
failure stops further calls, with remaining cases marked `not_run`; budget misses
also remain not-run but do not prevent later cache hits. Missing `DOPPEL_API_KEY`
is rejected before provider setup when calls are enabled. Unauthenticated local
providers require explicit `--allow-unauthenticated`. `--max-calls 0` is a cache-only
audit and never sends a provider request. Any error or not-run case keeps the exit
code nonzero even when quality failure limits are relaxed.

Ratios with no denominator are `null`, not a perfect score. Provider errors and
not-run counts remain visible and `execution.quality_measurement` is unavailable
when no draft is valid. Validation diagnostics retain only schema-known field names,
list indices, built-in validation codes, and the closed content-free temporal codes
`query_as_of_required`, `query_time_range_reversed`, `query_time_timezone_required`:
input values, unknown extra-key names,
exception messages, and validation context are not persisted. CLI reports include
implementation fingerprints and a SHA-256 sidecar; replay cannot overwrite its source.
Replay preserves `truncated` errors and safe HTTP status codes. Old root `value_error`
diagnostics remain unspecified; they are not retroactively assigned a cause.

The optional `--semantic-review` overlay is separate from storage gold. The bundled
[`relation-planner-semantic-review-zh-v1.json`](datasets/relation-planner-semantic-review-zh-v1.json)
was authored **after** inspecting typed-v2 and is explicitly `posthoc_diagnostic`,
not untouched heldout evidence. It never changes provider input, cached drafts,
strict metrics, retrieval labels, or pass/fail gates. It distinguishes correct/missed
explicit predicates, conservative abstention on underdetermined questions, and risky
ambiguous hard filters. A filter matching the hidden stored edge can still be risky;
an empty type can be valid protocol behavior without demonstrating good retrieval.

Temporal review matches declared shapes and explicit timestamp alternatives. An
open lower bound is accepted only for an explicitly open-interval expectation, not
as a generic replacement for a point query. Dataset v1.4 reviews the “after August
10” fixture as an open interval and records both inclusive-day and next-day lower
bound readings. No corrected overall pass rate is
derived from this review.

```powershell
uv run python -m benchmarks.relation_planner_quality `
  --replay-report data/doppel/relation-planner-deepseek-typed-v2.json --no-cache `
  --semantic-review benchmarks/datasets/relation-planner-semantic-review-zh-v1.json `
  --max-structural-failures 65 --max-relation-type-failures 65 `
  --output data/doppel/relation-planner-deepseek-typed-v2-reviewed.json
```

The same report can then drive the real Store + pgvector + Neo4j chain
without repeating the paid planner call for every profile. The exact dataset
fingerprint must match; planner failures and retrieval failures remain separate:

Explicit failed attempts are replayed as `source_planner_failure`, without retries,
provider error text, or fabricated drafts. Valid attempts continue; missing attempts,
duplicate queries, and entries with neither a draft nor an error are rejected.
Recall/MRR/evidence metrics retain failed evidence-bearing attempts in the denominator;
abstention metrics retain all attempts. Hard gates attribute source failures to the
Planner, not retrieval. Latency describes successful local replay executions only,
not the original LLM latency. Report provenance records the source file SHA-256,
valid/failed attempt counts, zero replay provider calls, and candidate-type execution
semantics. Replaying an older report tests the current engine with those stored
drafts; it does not measure the newer Planner prompt.

Replay cases keep two structural views. `planner_failures` is evaluated against the
immutable source draft, so an engine-side calendar repair cannot make the source
Planner look more accurate. `effective_plan_failures` evaluates the bound plan used by
retrieval, and `time_grounding_recovered`/`time_grounding_recovery_count` identifies
cases where generic calendar grounding removed a source intent/time failure. Temporal
and retrieval failures are attributed against the effective plan, while Planner hard
gates continue to report the original model error.

```bash
uv run python -m benchmarks.personal_retrieval_ablation `
  --dataset benchmarks/datasets/personal-relation-ablation-zh-v1.json `
  --profiles lexical_vector_relation --planner-modes report `
  --planner-report data/doppel/relation-planner-deepseek-v5.json `
  --gate-profiles lexical_vector_relation --no-metamorphic `
  --require-live-postgres --require-live-neo4j --require-all-profiles `
  --output data/doppel/personal-relation-ablation-deepseek-v5.json
```

The deterministic planner intentionally has no domain/entity parser and therefore is
expected to score zero exact relation structures. It remains a temporal/aggregation
baseline; these results must not be "fixed" by adding fixture vocabulary to runtime
code.

The runner executes both a fixture-bound `oracle` planner mode (retrieval isolation)
and the real domain-neutral deterministic planner (planner + retrieval baseline).
Full hybrid is unavailable unless both vector and graph sources are live. Graph
attribution reports unique edge/episode-to-final-hit links separately from unique
accepted hits and unique queries; direct returned-edge counts do not prove a final-hit
contribution. Reproducibility records a canonical payload hash in the report and a
SHA-256 sidecar for the final serialized JSON, avoiding a self-referential file hash.

Budget discipline: the runner performs **zero** external LLM calls and **zero** paid
tokens. Graphiti relations are preseeded directly into Neo4j (local
`BAAI/bge-small-zh-v1.5` embeddings via fastembed); pgvector uses the same local
provider in a profile-specific table; the extractor is not involved. When Neo4j or
PostgreSQL is unreachable the affected profiles report structured `unavailable` and
only `--require-live-*` turns that into a non-zero exit.

Metric definitions and hard gates:

- hard gates (must be zero or the command exits non-zero): scope leakage,
  cross-user hits, unauthorized-subject hits, Store-revalidation bypass, invalid
  provenance accepted, temporal leakage (expired/current), future plan treated as
  completed episode, candidate accepted without a Store record, same memory ID
  across scopes incorrectly deduplicated;
- quality metrics (reported honestly, failures allowed): recall@1/5, hit@1, MRR,
  required-evidence recall, forbidden hits, abstention/ambiguity/count accuracy,
  latency p50/p95/max, per-source contribution (vector/graph/both) from
  `semantic_source:` reasons;
- Graphiti edges are classified `fallback` (`DOPPEL_MEMORY_FALLBACK`) vs `rich`
  (`HAS_PERSONAL_MEMORY`) in the `graph_direct` diagnostic; a fallback edge only
  proves discoverability and provenance, never relation understanding;
- the planner's ability to recognize explicit dates and intents is reported per
  query (`as_of_recognized`, `actual_intent`). This benchmark does not claim a
  planner capability it does not have;
- metamorphic variants re-run the lexical profile and compare
  leakage/forbidden/abstention/count/evidence behaviour before and after
  substitution.

The extraction report measures:

- gold memories whose labeled evidence is covered by a correctly attributed,
  correctly scoped candidate;
- candidate support precision based on hand-labeled evidence;
- subject attribution and target-scope accuracy;
- writes citing ignored/noise or agent/system evidence;
- cross-user scope leakage as a hard correctness failure;
- end-to-end extraction latency.

Evidence overlap does not prove that generated content has the right meaning. The
report therefore keeps `semantic_content_correctness`, consolidation, conflict
resolution, final-answer correctness, and model token cost in `not_yet_measured`.
Live-model reports should preserve the analyzer/provider/model version, prompt/schema
version, dataset fingerprint, decoding settings, and raw candidate inspection rather
than comparing a single aggregate score.

[`memory-quality-result.schema.json`](memory-quality-result.schema.json) versions the
machine-readable envelope. [`reference-results/`](reference-results/) contains a
committed baseline from the release revision; latency values are observations from the
recorded environment, while evidence metrics and the dataset fingerprint are the
portable comparison surface.

## Personal-memory consolidation quality

The v0.8.2 consolidation runner exercises the real `InMemoryStore`,
`ConsolidationRunner`, and conservative deterministic consolidator over a versioned
Chinese fixture:

```bash
uv run python -m benchmarks.consolidation_quality \
  --dataset benchmarks/datasets/consolidation-quality-zh-v2.json \
  --output benchmarks/results/consolidation-quality.json
```

The fixture includes exact duplicates, explicit correction/retraction, unmarked
incompatible assertions, and equal-time conflicts, plus negative cases for unrelated
preferences, identical episode text without event identity, equal text in different
topic slots, a newer historical mention, and planned/current coexistence. The report
counts false actions, missing actions, wrong canonical choices, source lifecycle
errors, scope leakage, and latency. It also verifies that conflict markers are active
and isolated while their source claims remain active. Every correctness count must be
zero or the command exits nonzero.

[`consolidation-result.schema.json`](consolidation-result.schema.json) versions the
machine-readable report. This deterministic fixture validates policy and execution
boundaries; it does not establish semantic quality for an injected model consolidator.
Live-model evaluation still needs held-out paraphrases, ambiguous conflicts, human
review, and provider/prompt/version metadata.

## Chinese personal-memory query quality

The v0.8.0 query benchmark runs the real deterministic planner and
PersonalMemoryQueryEngine over one versioned multi-user fixture:

~~~bash
uv run python -m benchmarks.personal_query_quality \
  --dataset benchmarks/datasets/personal-query-quality-zh-v1.json \
  --max-missing-hits 3 \
  --max-forbidden-hits 1 \
  --output benchmarks/results/personal-query-quality.json
~~~

The nine questions cover current, planned, historical, and explicit point-in-time
residence; travel enumeration; exact distinct-event counting with repeated mentions;
count abstention when an event identity is missing; current preference; and a Chinese
lexical paraphrase. It reports missing and forbidden hits, intent/count/ambiguity
errors, scope leakage, and latency. The deterministic planner only recognizes closed
temporal/aggregation syntax; it does not contain residence, travel, food, work, or
other domain dictionaries. Consequently the committed lexical-only baseline currently
exposes three missing evidence hits and one semantically over-broad hit. The CLI ceilings
above make CI reject regressions without relabeling those gaps as perfect correctness;
the report's `correctness.passed` remains false until the raw expectations are met.

personal-query-result.schema.json versions the result envelope and records the retrieval
mode explicitly as `lexical-domain-neutral`. This fixture is not an embedding-model
score. Semantic indexes must be evaluated separately on held-out queries; regardless
of provider quality, their candidates remain subject to the authoritative Store,
scope, subject, and temporal gates. Omitting the ceiling arguments keeps the command
strict and returns a non-zero exit code for any missing or forbidden hit.

## Personal-memory governance quality

The v0.8.1 governance benchmark runs the real deterministic policy, integrity-bound
planner, ProposalWriter, InMemoryStore lifecycle, and checkpoint release:

```bash
uv run python -m benchmarks.governance_quality \
  --dataset benchmarks/datasets/governance-quality-zh-v1.json \
  --output benchmarks/results/governance-quality.json
```

The fixture requires an ended temporary state to archive and distinct trusted evidence
to reinforce. Negative controls protect a future state, an old long-term fact, an old
preference, an ephemeral record while decay is disabled, and repeated Agent output.
False/missing actions, wrong operations, importance errors, source/replacement lifecycle
errors, and scope leakage are hard failures. `governance-result.schema.json` versions
the machine-readable report. The fixture validates the default deterministic policy;
custom retention policies need their own domain-labelled false-positive evaluation.

## Store performance and correctness

The Store benchmark deliberately measures only behavior Doppel owns:

- sequential Store writes and idempotent duplicate writes;
- exact-scope search latency and expected-result recall;
- filtered search latency;
- stable paginated scan throughput;
- forbidden-memory and cross-scope leakage counts.

It does not claim to measure general “memory intelligence.” Embedding models, LLM
extractors, rerankers, prompts, and application retention policies need separate,
explicit evaluations.

### Quick run

Run the same 1,000-record dataset against both stable reference Stores:

```bash
uv run python -m benchmarks.store_benchmark \
  --backend memory \
  --output benchmarks/results/memory-small.json

uv run python -m benchmarks.store_benchmark \
  --backend sqlite \
  --output benchmarks/results/sqlite-small.json
```

Generated files under `benchmarks/results/` are ignored by Git. The SQLite command uses
a fresh temporary database unless `--database` is supplied. A supplied database path
must not already exist: the runner refuses to mix benchmark records with existing data.

The process exits with status 1 if a correctness gate fails. No performance threshold
is enforced: shared CI runners are too noisy for meaningful regression limits. Store
latencies and throughput are observations, while exact-scope leakage and missing data
are correctness failures.

### Reproducibility

[`datasets/synthetic-small.json`](datasets/synthetic-small.json) is a compact generator
configuration rather than a large committed record dump. Its generator name, version,
seed, scope count, record count, query sample count, and page size determine a dataset
fingerprint included in every result.

The `doppel.synthetic.v1` generator creates the same IDs, timestamps, scopes, content,
filters, and query sample order on every platform. Every search needle exists in every
scope. A query authorizes only one scope, so a backend that ignores exact-scope
isolation produces an immediately visible forbidden hit.

Latency percentiles use the nearest-rank method. Warmup searches are excluded from
measurements. When comparing results, use the same:

- dataset fingerprint and Doppel revision;
- Python implementation and version;
- operating system and hardware;
- backend configuration;
- number of repetitions and a quiet machine.

Run several repetitions and compare medians rather than treating one execution as a
stable performance claim.

### Result contract

[`result.schema.json`](result.schema.json) defines the machine-readable result envelope.
`result_schema_version` versions the output structure independently from the dataset
generator and Doppel package. Results include environment and capability metadata so
numbers from materially different setups are not silently compared.

The benchmark currently supports `memory` and `sqlite`. Future backend adapters should
plug into the same runner only after they satisfy the Store contract; benchmark speed
never compensates for failed isolation, idempotency, filtering, or pagination.

Third-party adapters can call the repository utility without modifying the CLI factory:

```python
from benchmarks.dataset import load_dataset_config
from benchmarks.store_benchmark import benchmark_store

config = load_dataset_config("benchmarks/datasets/synthetic-small.json")
result = await benchmark_store(
    config,
    my_store,
    backend_name="my-store",
)
```

The caller owns and closes a Store passed to `benchmark_store()`. The convenience
`run_store_benchmark()` function owns the built-in Store it constructs.

## Observable style quality

The separate StyleProfessor benchmark evaluates deterministic guidance and black-box
reply samples; it is not a Store performance benchmark:

```bash
uv run python -m benchmarks.style_quality \
  --dataset benchmarks/datasets/style-quality-v1.json \
  --output benchmarks/results/style-quality.json
```

The committed fixture contains a reference distribution, a matched output set, and a
deliberately contrasting output set. Its correctness gates require the matched case to
clear a minimum score, the contrasting case to stay below a maximum score, and both
pass decisions to match their labels. `style-result.schema.json` versions the output
envelope, and the dataset fingerprint makes fixture changes visible.

`StyleQualityEvaluator` is independent from `StyleProfessor`: it observes generated
message length, short-message, question, exclamation, emoji, multiline, and terminal
punctuation distributions. It does not inspect the guidance prompt or ask the generator
to grade itself. Common-phrase overlap is intentionally excluded so copying source
content is not rewarded as style quality.

These metrics do not measure factual correctness, semantics, identity, helpfulness, or
safety. Production evaluations should use held-out conversations and real model
outputs, keep sampling settings fixed, report every feature score, and add human blind
review instead of treating one aggregate number as “persona fidelity.”

## pgvector and hybrid correctness

The pgvector benchmark is separate from Store performance and observable style quality:

```bash
uv run python -m benchmarks.vector_quality \
  --dsn "postgresql://doppel:secret@127.0.0.1:5432/disposable_test" \
  --allow-mutating-benchmark \
  --dataset benchmarks/datasets/vector-quality-v1.json \
  --output benchmarks/results/vector-quality.json
```

The target must be a disposable pgvector-enabled PostgreSQL database. The fixture
provides every record/query embedding directly through a deterministic provider. This
isolates Doppel's responsibilities: complete and idempotent indexing, expected semantic
and hybrid top-1 IDs, exact-scope filtering, and zero forbidden cross-scope hits.

The score is not an embedding-model leaderboard. It cannot establish whether a real
provider understands an application's language or domain. Evaluate each production
provider/version on held-out labeled queries before switching its profile. The dataset
fingerprint and `vector-result.schema.json` make fixture and result-envelope changes
visible in CI.

## Experimental candidate-path generation

The earlier live Neo4j candidate-path ablation supplied candidate topologies as
fixtures. It proved what the graph can retrieve *given* a topology; it did not prove
that a model can derive one from a new question. The independent
[`candidate-path-generation-zh-v1.json`](datasets/candidate-path-generation-zh-v1.json)
contains 18 new Chinese questions (6 dev, 6 heldout, 6 adversarial) and four no-path
controls. It is frozen but deliberately not publication-ready. Its gold routes are
used only by the scorer, never included in model requests.

Dry-run (no API key access or network call):

```powershell
.venv\Scripts\python.exe -m benchmarks.candidate_path_generation_live --partition dev
```

For a first paid measurement, commit the implementation and dataset before running,
set `DOPPEL_API_KEY` in the current PowerShell process without writing it to a file,
then use a fresh ignored cache and output path:

```powershell
.venv\Scripts\python.exe -m benchmarks.candidate_path_generation_live --live --sealed-first-run --max-calls 18 --output data/doppel/candidate-path-generation-first-live.json
```

The runner defaults to DeepSeek `deepseek-v4-flash`, `json_object`, disabled thinking,
1,024 maximum completion tokens and no provider retries. A call budget stops network
requests before the limit; content-addressed raw-output cache hits cost no calls.
It reports required-route coverage, excess routes/types, no-path false candidates,
invalid observations, and token use. Neither this scorer nor the generator opens
Neo4j. These metrics must not be described as real evidence recall, temporal safety,
or answer quality. The next stage should feed model-generated routes into the
existing live graph ablation and measure evidence gain, irrelevant candidate load,
latency, scope isolation, temporal validity, and Store provenance together.

The first sealed run uses thresholds committed before any provider output is opened:
overall and one-hop required-route recall at least 0.80; two-hop recall at least 0.75;
no-path false-candidate rate at most 0.25; extra routes at most 0.50 per case; extra
types at most 1.00 per generated route; and zero provider/validation errors or invalid
topology compilations. These are development gates for deciding whether an end-to-end
Neo4j trial is worthwhile, not publication-grade quality claims. A sealed run must
include all three partitions and reserve one provider call for every case.

After a provider run, the same raw outputs may be re-scored with `--live --max-calls 0`
and the existing cache. This mode does not require an API key and cannot make a network
call: a missing cache entry is reported as a budget error. Such re-scoring is opened
diagnostic evidence, never a new sealed result. Reports retain the model's raw bounded
topologies so disconnected endpoints and split multi-hop chains can be distinguished
from compiler or scoring defects.

A partition-only diagnostic cannot pass the complete quality gate unless its selection
contains at least one one-hop route, one two-hop route, and one no-path control. Its
individual metrics remain valid, but an absent category is not positive evidence.

The optional `--review-protocol` adds one non-authoritative review pass over the first
topology observation. It receives the same question, fixed anchor, host ontology, and
the fallible first output; it still has no scope, graph, memory ID, answer, or execution
authority. A fresh run therefore requires up to two provider calls per case. When the
single-pass raw-output cache is reused, first-pass hits consume no call budget and only
the review requests reach the provider. Reports identify the protocol and generator
version explicitly.

The experimental `--planner-backbone` profile is a controlled architectural comparison,
not another candidate prompt. It runs the existing two-pass V7 relation-atom Planner,
lets its trusted host compiler order steps and derive directions, then converts that
compiled route back into a retrieval-only candidate topology. It grants the Planner no
graph or scope authority and uses up to two provider calls per uncached case. Use a
separate cache because its structured requests differ from the candidate-generator
protocol. The profile exists to decide whether Doppel should share one path-understanding
backbone instead of maintaining two competing natural-language topology protocols.
