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

## Completed full-history ingestion and restart verification

Live execution and completed restart replay both bind source commit
`024e859d699031b51bcab32fd421ce75639f22cc`; only pre-existing user-owned uv.lock
was dirty. The runtime source fingerprint was
`508a9787a13159bcba494f3a37f44dc3dac0b9850fad9312259d38a49fbe4ce7`.
The same source/manifest/profile processed every planned chunk in original order,
with no skipped predecessor, replacement source or changed threshold/prompt.

| Final observation | Count |
| --- | ---: |
| Completed / planned chunks | **147 / 147** |
| Diagnostic owners / supplied sessions | 3 / 145 |
| Original nonblank raw messages retained | 1513 |
| Schema-valid drafts | 618 |
| Accepted proposals / derived records including inactive | 599 |
| Explicit evidence rejections | 19 |
| Mixed-source / subject-source mismatch rejections | 15 / 4 |
| Invalid-schema / low-confidence / duplicate drops | 0 / 0 / 0 |
| Missing analysis observations | 0 |
| Separate governance records | 4 |
| Store raw + derived + governance records | 2116 |
| Store/source checks / failures | 2291 / 0 |
| New-profile live calls / reported tokens | 110 / 557,750 |
| Original plus new calls / reported tokens | 147 / 746,665 |
| Completed restart chunks replayed | 147 |
| Restart new calls / tokens | 0 / 0 |

All 110 new provider attempts succeeded with complete observed usage, no retry,
interrupted/reserved remainder or invalid raw-output cache entry. Attempt/byte
bounds held; reported token totals are not an exact-billing guarantee. Previous
37 provider responses were reused, not billed again.

The rejection partition reconciles as 618 = 599 accepted + 19 evidence-rejected.
Those 19 drafts were not repaired or promoted; their original source messages
remain available as attributed raw context. This is not extraction accuracy:
valid source binding cannot prove the semantic claim follows from that source,
and rejections can lose information that a later retrieval/reader needs.

Every diagnostic owner's complete history is now ingested and its index reconciled.
New-process zero-provider restart replay reproduces **exactly the same audit,
Store record counts and provider ledger**, including rejection observations and
governance records. Both reports have status complete. No checkpoint reset or
extra extraction was needed.

Preserved ignored reports:

- `longmemeval-memory-trusted-partition-live-v1.json`, SHA-256
  `f7d41141b2d34da9c41187a9122e9691946cc4d4dca7fde688028aa73d972e5e`.
- `longmemeval-memory-trusted-partition-complete-replay-v1.json`, SHA-256
  `3b899f08aa9dabbb15a89e455a2907046228a81abd776407eff0348c809b7d1c`.

This closes the complete-history **ingestion** pilot, not the complete benchmark.
The three opened questions are not a representative or blind quality sample;
reserved groups remain untouched. No graph, natural Planner, retrieved-evidence
ordering, answer-reader score or AML compliance is claimed by these results.

Next: freeze matched evidence/reader budgets and compare attributed raw context,
extracted memory and their combination on these same complete histories. Measure
evidence coverage, irrelevant evidence load and answer quality separately, including
whether the 19 rejected drafts leave recoverable information only in raw context.
Do not use answers/annotations in runtime selection or tune to these opened cases.
Validate the chosen general approach on reserved groups before broader claims.
