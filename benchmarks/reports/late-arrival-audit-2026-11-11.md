# Late-arrival boundary audit, 2026-11-11

Follow-up to the [normal-path PG integration](late-arrival-pg-2026-11-11.md),
based on `d66f8ac`. This round reviews host wiring and persisted queue integrity,
not extraction quality or retrieval ranking. Corruption and miswiring are injected
only in temporary test data; no existing user or benchmark data is modified.

## Repaired gaps

1. `drain_once` previously compared the host-supplied `history_identity` string
   without verifying the actual reader's snapshot. A different Store reader,
   different batch reader or empty selection could still advance the workflow
   and acknowledge the reserved batch. It now requires the native `FrozenHistory`
   with matching scope, identity and serialized message snapshot, before writing
   source records. General custom readers in the core history protocol remain
   supported; this restriction applies to the frozen arrival recipe.
2. Enqueue stored a semantic fingerprint, but reservations and acknowledgments
   did not revalidate it. A changed payload before first reservation could acquire
   a new, apparently valid batch ID. The recipe now verifies message identity and
   enqueue-time checksum on duplicate enqueue, initial/resumed reservation and
   acknowledgment. Invalid source rows stop the transaction rather than being
   incorporated into a replacement batch. Duplicate corruption is distinguished
   from a genuinely conflicting incoming message.

Seven regression controls cover three wrong-reader configurations and four
queue operations. They verify that wrong readers cause no source writes or
analyzer calls, and corrupted queue rows are not acknowledged. Batch hash format,
schema and workflow journal binding remain unchanged; no reset/migration is used.

These are host-error/integrity checks, not authentication. Checksums are not
signatures and cannot protect against a writer replacing both data and checksums.
Single-consumer ownership and host access controls remain required.

## Validation

The 65 related arrival/runtime/lifecycle tests pass, including independent-process
recovery and the five PG driver controls using a catalog double. Ruff and the
changed recipe's Pyright check pass.
Full repository regression: **2,569 passed / 33 skipped / 3 subtests passed**, with
one existing Graphiti/Pydantic deprecation warning and no test failures.

The unchanged PG driver ran four new independent processes in the retained schema
`doppel_arrival_audit_20261111`, using journals/inbox under
`data/examples/arrival-pg-audit-20261111`. All stages passed their expectations;
interruption remained incomplete until the resume stage, with one stale inactive
entry and four missing/changed active entries observed before repair. Resume and
replay each made zero analyzer calls. The full Store digest was identical across
interruption, resume and replay:
`d5350dafb2bc6c584510cafd0bf627cd70655082e40e02a5d08b3e1576c34642`.

Real local embedding calls: 28. Paid LLM calls: zero. Final current and interval
as-of hits retained actual vector candidate support; current value, source dates,
provenance, scope and temporal checks passed. No new semantic-quality claim follows
from the scripted analyzer. The prior normal-path run and its receipts remain intact.

A read-only inspection of that prior run's inbox validated all three batch IDs
and four source-message checksums with the repaired code. It did not rewrite the
old queue or claim recovery from an unfinished historical batch.

Four receipts are at `data/doppel/arrival-pg-audit-20261111-{stage}.json`; their
summary `data/doppel/arrival-pg-audit-20261111-summary.json` binds receipt hashes,
runner and arrival-recipe source hashes, and the read-only compatibility check.
