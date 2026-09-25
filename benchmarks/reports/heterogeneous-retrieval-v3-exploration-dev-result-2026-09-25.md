# Heterogeneous retrieval V3 — bounded-exploration dev result

This report preserves the only dev-partition run of the bounded-exploration runner
revision committed as `45a7b9c7a95c01e8c0c8017817610a6b25e90315`. It was recorded
before opening either the sealed or adversarial partitions. No external HTTP request,
paid LLM call, or provider token was used.

## Reproducibility

- dataset: `doppel-heterogeneous-retrieval-zh-v3` (`3.0.0`)
- dataset fingerprint:
  `ead91761f9da403c31c8b759d427c4551709daf7d29f35d26d786f94ec167f88`
- selection: 120 dev queries, 12 scopes, 2,304 of the frozen 9,216 memories
- implementation commit: `45a7b9c7a95c01e8c0c8017817610a6b25e90315`
- report payload hash:
  `b70ecfd06bd2603802dea0ef3ddcf06e6bb57f06b7ce53ad1d1e7bc21a017832`
- raw JSON file SHA-256:
  `edf5b7c86c734bfbf15ae4f9dbf3eea81744d2ab1cc4ca74af136bb0137ff811`
- authoritative Store: PostgreSQL
- independent retrieval: PostgreSQL lexical plus 512-dimensional pgvector cosine
  search using `BAAI/bge-small-zh-v1.5`
- relation retrieval: local Neo4j/Graphiti exact paths and separately reported bounded
  exploration
- reranker: local `bge-reranker-v2-m3`, CUDA, 64-record window
- context bound: 20 memories
- tracked dirty path disclosed by the runner: the pre-existing user-owned `uv.lock`

The ignored raw result is
`data/doppel/heterogeneous-retrieval-v3-exploration-dev-live.json`. The committed
dataset, runner, schema, preregistration, and this report contain everything needed to
repeat and interpret the measurement; the large machine-local output is intentionally
not committed.

## Profile results

| Profile | Evidence recall@5 | Complete evidence@10 | Related context@10 | MRR | p50 / p95 ms |
|---|---:|---:|---:|---:|---:|
| independent lexical + vector | 0.818 | 0.778 | 0.250 | 0.838 | 79.0 / 110.9 |
| exact oracle graph path | 0.273 | 0.222 | 0.000 | 0.222 | 0.0 / 17.1 |
| bounded graph exploration | 0.273 | 0.222 | 1.000 | 0.222 | 0.0 / 16.6 |
| assembled exact hybrid | 0.902 | 0.880 | 0.250 | 0.838 | 162.6 / 277.7 |
| assembled exploration hybrid | 0.909 | 0.889 | 1.000 | 0.838 | 162.6 / 273.0 |
| exploration hybrid + memory reranking | **1.000** | **1.000** | **1.000** | **0.958** | 296.7 / 482.9 |

The exact-path and exploration profiles are intentionally not general retrieval
profiles. They run only typed paths that exist in the frozen oracle plan. Their low
overall recall is expected because most queries do not ask for a relation path. The
useful comparison is between assembled profiles: adding exploration raises related
context recall from 0.250 to 1.000 without reducing answer evidence, and reorder-only
memory reranking then raises evidence recall@5 and complete evidence@10 to 1.000.

The exploration result does **not** claim that adjacent context proves an answer. For
example, a `HELD_BY` edge may be useful context for a question about who bought an
object, but it is still reported with `answer_support=unassessed`. The answering model
or an optional evidence verifier remains responsible for sufficiency.

## Category result for the final profile

All ten categories reached 1.000 evidence recall@5 and complete evidence@10, including
current residence, historical residence as-of a date, corrected facts, exact episode
counts, document facts, cross-conversation preferences, subject corrections, one-hop
relations, two-hop relations, and no-answer queries with related context. Exact episode
count accuracy was 1.000. The lower aggregate MRR of 0.958 is concentrated in subject
correction: both the owner's correction and the peer's related conflicting statement
are retrieved, while the answer-bearing correction is not always ranked first.

## Safety and accounting

The final profile recorded zero hard-forbidden hits, cross-scope leakage, subject
violations, ineligible-state hits, temporal violations, orphan provenance, Store
revalidation failures, path-budget omissions, and reranker membership violations.
Neo4j and PostgreSQL fixture cleanup both completed. All 120 reranker outcomes were
accounted for: 108 completed and 12 legitimately `not_run` because the no-answer or
structured-count branch had no independent candidate window to rerank.

The result envelope reports `gate.ok=false` only because `selection_complete=false`:
this is deliberately a dev diagnostic, not the required all-partition first run. Every
quality, safety, boundedness, accounting, and cleanup check passed. The next action is
the already-frozen `--partition all --sealed-first-run` measurement. Its result remains
valid evidence whether it passes or fails; sealed/adversarial output must not be used
for iterative tuning.
