# Late-arrival recovery on real PostgreSQL/pgvector, 2026-11-11

Four independent processes exercised the host arrival inbox against the existing
healthy PG container. A separate retained schema `doppel_arrival_20261111` and
directory `data/examples/arrival-pg-20261111` were used. Existing lifecycle data,
other schemas, volumes and journals were not reset or deleted. No real-chat data,
paid provider, model download or Graphiti call was used.

The analyzer emits scripted drafts from synthetic messages; it is not an LLM.
The local 512-dimensional BGE SentenceTransformer ran on CPU using the previously
downloaded snapshot and index profile `pgvector:dplv_bd356b4301164b5d`.

| Stage | Fixture analyzer calls | Local embedding calls | Store row audits | Outcome |
|---|---:|---:|---:|---|
| seed | 2 | 9 | 4 | Two exact scopes initialized and acknowledged |
| interrupt | 1 | 5 | 9 | Expected index boundary failure; original batch remains pending |
| resume | 0 | 9 | 9 | Saved index stage resumed, manifest repaired, batch acknowledged |
| replay | 0 | 5 | 9 | Queue empty; complete Store digest unchanged |

Total local embedding calls: **28**. Paid LLM calls: **0**. The 31 row audits are
repeated checks over stages, not 31 independent memories or quality questions.
Nine source/derived records remain at the end, including raw and inactive records.

## Observed behavior

- A newer explicit correction was processed before an older assertion arrived.
  The late assertion did not replace the current value; its source ID was added
  alongside the newer source in the canonical evidence chain.
- A second late record had an explicit bounded validity interval. Current and
  outside-interval queries excluded it; the inside-interval as-of query returned
  it with `as_of_match=validity_match`. Source timestamps were preserved.
- An actual other-owner fixture remained independently queryable; the empty-owner
  query had no hits. Every returned record matched its exact requested scope.
  This is a small integration check, not an adversarial multi-tenant benchmark.
- The expected writer-boundary fault left **one inactive index entry** plus
  **four active entries missing or carrying outdated fingerprints**. The batch
  was not acknowledged. The query still used authoritative Store checks; the
  incomplete index was not reported as healthy or complete.
- Recovery cleared those divergences. Completed-stage current and as-of hits
  carried actual semantic candidate support, so passing was not solely lexical.
  The incomplete stage had zero such supported final hits, as reported.
- Recovery and replay each made zero analyzer calls. The full serialized Store
  digest was identical across interruption, recovery and replay; maintenance
  repaired derived index state without rewriting authoritative records.

Final Store digest:
`99248c24dacccfbcf10a9f0a1a9e2e7c38d24d2845e9c577b3720fbebd0efbcf`.

## Reproduction and validation

See [runner instructions](../../docs/late-arrival-pg.md). Receipts are retained at
`data/doppel/arrival-pg-20261111-{stage}.json`. The summary at
`data/doppel/arrival-pg-20261111-summary.json` binds all four receipt hashes and the
runner source hash; execution used the working tree based on `c2f6eeb`.

Five new offline driver tests and the related arrival/runtime/lifecycle checks:
**58 passed**. Full-repository Ruff, changed-file formatting and runner Pyright
passed. No full-suite rerun this round; the preceding commit's full-suite result
was 2,557 passed / 33 skipped / 3 subtests passed and is a separate observation.

This validates the explicitly wired arrival path, not bypassed or previously
unknown omissions. The queue still has a single exclusive consumer. There is no
real network-loss, multi-instance, Graphiti or production-throughput result here.
Explicit temporal metadata and the scripted analyzer do not establish extraction
quality, overall recall or answer accuracy. The older same-topic assertion is
retained as provenance, not promised as a separately reconstructable old value.
