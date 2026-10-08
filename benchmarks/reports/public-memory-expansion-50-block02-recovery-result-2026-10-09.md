# One unchanged-request recovery succeeded; ingestion remains partial

The frozen [recovery plan](public-memory-expansion-50-block02-recovery-plan-2026-10-09.md)
is executed in a fresh child checkpoint. The transport-failed pending chunk is
retried exactly once under a separate one-call budget, with unchanged model and
prompt. The request succeeds; the result is `observed-success`.

The child replays and validates all **130** completed source chunks from its
read-only parent, then completes chunk131 with one successful call. Final Store
audit: **1,312 raw records, 572 derived records, 5 governance records and 2,003
provenance checks with zero failures**. Semantic truth is not evaluated. The
original failed attempt and all old reports, cache and journal remain preserved.

Recovery call usage: **6,815 reported tokens** (5,802 input, 1,013 output), complete
usage available. The original failed request had unknown usage. Across the three
ingestion stages, 132 attempts are now recorded: 94 in block01, 37 in block02
(36 successes plus the transport failure) and one successful recovery. Known
token usage is 479,138 +190,623 +6,815 = **676,576**, plus unknown usage from the
failed transport attempt. These are reported provider counts, not an exact invoice.

The fifty-history ingestion remains **partial**: 131/2,420 chunks complete and
2,289 remain. No retrieval, Reader, Judge or QA score is produced. The recovered
checkpoint now supplies a validated parent for a new bounded continuation; it
must preserve the cloned prefix's lineage and count its isolated recovery ledger.

Ignored report `data/doppel/longmemeval-expansion-50-block02-recovery-live-v1.json`,
SHA-256:
`4326244c9f8e5935073d632369f9c395caf25ddccf7c652ab0bf9ab95921f306`.
Recovery plan fingerprint:
`39c5e63976c8d48f5a19c70ad12d6fb078ec9c196b4893c81d8e15d50547580d`.
The report's local aggregate38 calls covers its immediate failed parent budget37
plus recovery1; the full fifty-history lineage additionally includes the earlier
94-call block01 as stated above.

The continuation runner now accepts a successful recovery-observation report,
binds its inherited completed prefix separately from its local call ledger, and
validates SQLite/WAL/budget/plan files plus the cache inventory before continuing.
Focused ingestion/recovery/continuation tests: **33 passed**; Ruff and scoped
Pyright pass. This does not change extraction policy or retrieval scoring.
