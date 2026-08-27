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
  pretending that an extractor or consolidator exists.

Gold queries describe required evidence as groups. Any message in one group can
satisfy that fact, so repeated statements do not force a system to return every copy.
Forbidden message IDs measure stale, wrong-speaker, agent-output, and unauthorized
evidence. Out-of-scope output is a hard runner failure; same-scope stale or
wrong-authority evidence remains a reported quality defect so weak baselines can be
measured instead of making the benchmark impossible to run.

The report includes macro evidence recall, candidate precision, reciprocal rank,
abstention accuracy, forbidden hits, redundant relevant candidates, context character
count, and query/prepare latency. The dataset already includes future extraction and
consolidation gold memories, but v0.7.1 explicitly reports those dimensions—along with
answer correctness and model token cost—as `not_yet_measured`. They become comparable
only when a reference intelligence implementation exists.

[`memory-quality-result.schema.json`](memory-quality-result.schema.json) versions the
machine-readable envelope. [`reference-results/`](reference-results/) contains a
committed baseline from the release revision; latency values are observations from the
recorded environment, while evidence metrics and the dataset fingerprint are the
portable comparison surface.

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
