# Consolidation v4 trusted partition: opened production regression

This follows the [preregistered plan](public-memory-trusted-partition-plan-2026-10-07.md).
Only generic deterministic source grouping changes; the analyzer prompt, source,
questions, labels, confidence threshold, authority policy and runner guards do not.
The old v3 chunk-37 failure and both old journals/caches/reports are preserved.

## Generic correction and synthetic regression

Both topic-keyed and unkeyed grouping now include exact trusted actor, authority
and kind before existing semantic and time/revision rules. Matching semantic
metadata cannot grant permission to mix incompatible trusted sources. Compatible
merge/conflict/correction behavior remains; incompatible sibling records remain
untouched. No kind aliases, special topics, question matching, authority promotion
or exception swallowing are introduced. Runner compatibility checks are unchanged.

Fifteen new synthetic variations reproduced the original error before the fix:
three trusted attributes across keyed/unkeyed duplicates, conflicts, corrections
and historical revisions. All pass after partitioning. Three forced cross-identity
plans continue to be rejected before writes. An additional run-binding test proves
that a changed consolidator version cannot reuse an old profile, while chunks,
provider configuration, analyzer and Miner policy remain identical.

The component identity is v4; its public signatures/wire shape are unchanged.
Version-bound host checkpoints require a fresh profile or explicit migration,
not an edited saved plan or silent in-place version change.

## Real cached production execution

New run: `data/doppel/public-memory-ingestion-quarantine-v2`; new PostgreSQL schema
`public_memory_7c9e31e426b2`; actual local PostgreSQL/pgvector/BGE profile unchanged.
Plan fingerprint:
`7c9e31e426b273fc761795fb5b4946bcd0c4e2892e8c5e63939df571e7974d64`.

| Observation | Count |
| --- | ---: |
| Completed / planned chunks | 37 / 147 |
| Strict read-only old-output cache hits | 37 |
| New model calls / tokens | 0 / 0 |
| New writable cache files | 0 |
| Raw messages retained | 392 |
| Schema-valid drafts | 176 |
| Accepted proposals / derived records including inactive | 175 |
| Explicit mixed-source rejection | 1 |
| Invalid-schema / low-confidence / duplicate drops | 0 / 0 / 0 |
| Separate governance records | 2 |
| Store raw + derived + governance records | 569 |
| Store/source checks / failures | 614 / 0 |

Chunk 37 now has persisted/completed consolidation and verified index reconciliation.
All 175 accepted proposals survive; raw records and the rejection partition are
unchanged. Zero new paid calls and no key read during this cache-only execution.
Missing/invalid cache entries would fail closed rather than call a provider.

This is **not extraction correctness** or a retrieval result. It is source-binding
and stage-completion evidence on a partial prefix of the first diagnostic owner.
Semantic truth is unverified; graph, Planner, ranking and reader have not run here.
Reserved histories remain untouched, and the model profile is not AML academic
compliant. No publication readiness follows from this stage.

Ignored artifact: `longmemeval-memory-trusted-partition-cache-v1.json`, SHA-256
`f13b9cbba4c85edbbabeb4094280c4c29b0dac273d594211689aff14a72270ae`.
This cache regression ran on a dirty worktree based on b6a02d2 with actual runtime
source hashes, not mislabeled as a later clean-commit execution.

Verification: **1129 passed, 33 skipped**, plus 3 subtests passed. Targeted run:
86 passed. Whole-repository Ruff lint/type checks, changed-file formatting, wheel
build and offline isolated wheel import/identity smoke passed. Unrelated pre-existing
format differences were not bulk rewritten. User-owned uv.lock was not modified or
staged. Committed unchanged-profile live continuation is recorded after it finishes.
