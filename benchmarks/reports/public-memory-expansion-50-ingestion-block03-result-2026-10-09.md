# Block03 complete: 331 of 2,420 chunks ingested

The frozen [block03 plan](public-memory-expansion-50-ingestion-block03-plan-2026-10-09.md)
first revalidated the recovered131-chunk prefix, then processed exactly200 new
chunks through chunk331. All200 calls succeeded; there were zero failed,
interrupted or retried calls. The process stopped at the predeclared block cap.

## Store and extraction observations

Across331 completed chunks, the authoritative PostgreSQL Store audit observes:

- **3,364 raw source records**.
- **1,375 derived personal-memory records**, including inactive records in the
  audit domain.
- **16 conflict/governance records**.
- **5,084 scope/source/provenance checks, zero failures**.
- Seven histories touched so far; six fully ingested, one currently partial.

The cumulative analyzer diagnostics reconcile as follows:

| Stage | Count |
| --- | ---: |
| Analyzer drafts | 1,445 |
| Schema-valid drafts | 1,444 |
| Schema-invalid drafts (`value_error`) | 1 |
| Attribution-gate rejected drafts | 67 |
| Low-confidence valid drafts | 2 |
| Persisted proposals | 1,375 |

The67 attribution rejections comprise52 subject/source mismatches and15 mixed
source-actor proposals. These classifications do not establish whether a
rejected claim is semantically true. Provenance checks confirm reference
integrity, not truth or retrieval quality.

## Usage and evidence boundary

Block03 uses **200 extraction calls / 992,534 reported tokens**:892,694 input,
including179,200 cached input, plus99,840 output. Usage is complete for all200
calls. The failed block02 transport attempt still has unknown usage.

Across ingestion so far,132 attempts occurred before block03 (94 block01,37
block02,1 recovery), and block03 adds200, for **332 total attempts** including
the single failed transport attempt. Known reported ingestion tokens total
1,669,110, plus unreported usage for that failed attempt. This is a usage ledger,
not an exact billing receipt.

There is **no new retrieval, Reader, Judge, recall or QA result**. The 50 selected
questions have not yet been evaluated. Overall status remains partial with
2,089 chunks left. The ingestion runner does not execute Graphiti or the
production natural query Planner.

Ignored report `data/doppel/longmemeval-expansion-50-ingestion-block03-v1.json`,
SHA-256:
`6e969585d41465798a66dfbedb057708370cdeda00d276addffe1ea75e1e4f06`.
Continuation plan fingerprint:
`035d36f05bd2a03c5268ac858ceeac61450bf38b70a52bea569452d4bbc550d3`.
Focused continuation/recovery/ingestion tests: **34 passed**; Ruff and scoped
Pyright pass. The previously completed full suite was1,333 passed /33 skipped /3
subtests; no code changed during the live extraction block.
