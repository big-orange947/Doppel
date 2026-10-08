# Fifty-history expansion: first two histories ingested, no new QA score

The [selection and ingestion plan](public-memory-expansion-50-ingestion-plan-2026-10-08.md)
was committed as `d102094` before new provider calls. This first invocation stops
normally at its frozen94-chunk boundary: **94/94 new chunks complete**, comprising
two complete histories (`ceb54acb`,50 chunks; `3ba21379`,44 chunks). The completed
journal keys exactly match the first94 keys in the2,420-chunk plan. No failure,
retry, replacement history, budget increase or reserved-history execution occurs.

Overall status is **partial**, not successful fifty-history completion. There are
48 diagnostic histories /2,326 chunks left to ingest. Retrieval, Reader and Judge
on this new selection have not run; actual completed public QA coverage remains
thirteen distinct questions out of500, with487 still unmeasured. Ingestion must
not be reported as a recall, answer-accuracy or AML result.

## Stored data and qualifications

Real PostgreSQL/pgvector, production analyzer/Miner/consolidator, current evidence
gates and local BGE-small-zh512 execute in the dedicated schema
`public_memory_03134787d461`. Docker was already healthy; no automatic launch,
restart, volume operation or old-data migration executes. No Graphiti or natural
query Planner executes in this stage.

Final Store audit observes:

- **924 raw source records**, preserving both user and assistant messages.
- **393 derived personal-memory records**, including inactive records in the
  audit domain; all observed records currently have confirmed state.
- **4 governance/conflict records**; these are not extra unique personal facts.
- **1,404 provenance checks, zero failures**, checking identities, source
  attribution and conflict references; this is not semantic-truth verification.

All94 chunks have durable analysis observations. Their drafts reconcile:

| Stage | Count |
| --- | ---: |
| Analyzer drafts | 423 |
| Schema-valid drafts | 422 |
| Invalid draft rejected (`value_error`, chunk37) | 1 |
| Valid draft rejected for subject/source mismatch | 23 |
| Valid draft rejected for mixed source actors | 5 |
| Low-confidence valid draft excluded | 1 |
| Persisted proposals | 393 |

Thus422 =393 +28 +1. Invalid and quarantined drafts remain reported; they are not
silently omitted from a quality denominator. These gates constrain attribution,
not truth. A rejected third-party draft is not proved false, and preserving raw
evidence does not prove a derived summary retained every useful detail. Assistant
records are not upgraded to owner facts merely because both roles were ingested.

## Usage, lineage and verification

**94 new extraction calls**, all succeeded with complete usage, zero retries:
428,607 input +50,531 output = **479,138 reported tokens**. Input reports
84,224 cached and344,383 cache-miss tokens. The lifetime2,420-attempt cap and
canonical-byte cap remain within budget; neither is an exact billing/token cap.
No Reader/Judge calls occur in this block. Separately, the closed same-Reader
packing experiment used5 calls/30,759 tokens; together this turn uses99 new calls
and509,897 reported tokens, not just the extraction subtotal.

The selection remains fixed, including its single no-answer case and shared
session content. No old cache/database/journal/score or user-owned `uv.lock` is
modified. Dataset SHA matches the frozen source. Reserved groups stay unexecuted.
This block uses existing ingestion code; this turn's full regression before live
execution passes1,327 tests with33 skipped /3 subtests; whole-repository Ruff and
scoped Pyright pass. The new packing harness separately passes11 tests again.
These checks do not validate fifty-question intelligence or production latency.

Ignored report `data/doppel/longmemeval-expansion-50-ingestion-block01-v1.json`,
SHA-256:
`736b7f7f2fdf0ae30e0511443368768370ffe89f3a8c2289538397a238dc1cbf`.
Ingestion plan fingerprint:
`03134787d46171f0109d6e9770b68ed9f84f1d0a9d45d23aa4c9eaf32a0ba458`.
Manifest SHA-256:
`28dc31edbcfc119d5f952d9f0ab3ceeaa123a5e9a5bfef70f82f9febbc120721`.

Report execution metadata names `d102094` and also records dirty documentation
(`CHANGELOG.md`, `docs/public-memory-pilot.md`) and preexisting `uv.lock` at final
report generation. All four bound composition-source hashes still match the
committed source; documentation written during the run is not an algorithm change.
Do not rewrite the report's commit or dirty-path list after the final docs commit.

## Next bounded continuation

Continue the remaining fixed histories in an explicitly bounded block after
validating the completed journal prefix and source/index state. Keep the same
configuration, baseline packer and preserved failure accounting. Do not silently
spend the remaining2,326 extraction attempts or retry failures.

Before fifty-question QA calls, implement/freeze the three-channel comparison and
separate reference-answer correctness from context support and justified refusal.
Do not reopen the old prompt-calibration loop or promote the rank-fit null result.
The new50 have not been answered, independently judged, or scored as a completed
benchmark. No production Planner/Graphiti or AML model compliance is implied.
