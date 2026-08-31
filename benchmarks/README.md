# Doppel benchmarks

This directory contains repository-only benchmark tooling. It is not installed as part
of the `doppel-memory` package and is not a public runtime API. Store performance,
retrieval evidence quality, observable style, and semantic-index correctness remain
separate reports; Doppel does not combine them into a flattering but meaningless
"memory intelligence" score.

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
`datasets/personal-relation-ablation-zh-v1.json` provides that edge-level gold: 14
authoritative memories, 30 queries, 3 exact owner scopes, explicit entity anchors,
rich relation facts, current/history/as-of boundaries, same-name cross-scope
collisions, unknown entities, and wrong-relation adversaries. Run the four relation
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
