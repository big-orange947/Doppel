# Doppel benchmarks

This directory contains repository-only benchmark tooling. It is not installed as part
of the `doppel-memory` package and is not a public runtime API.

The first benchmark deliberately measures only behavior Doppel owns:

- sequential Store writes and idempotent duplicate writes;
- exact-scope search latency and expected-result recall;
- filtered search latency;
- stable paginated scan throughput;
- forbidden-memory and cross-scope leakage counts.

It does not claim to measure general “memory intelligence.” Embedding models, LLM
extractors, rerankers, prompts, and application retention policies need separate,
explicit evaluations.

## Quick run

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

## Reproducibility

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

## Result contract

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
