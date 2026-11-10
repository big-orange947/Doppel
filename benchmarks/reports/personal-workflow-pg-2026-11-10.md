# Personal workflow: real PG/pgvector integration, 2026-11-10

This is an integration/restart check, not extraction quality, a retrieval benchmark
or a production multi-instance acceptance. FixtureAnalyzer supplies synthetic
drafts. No paid LLM calls, graph construction or model downloads occurred.

## Execution

Existing healthy `doppel-ablation-pgvector` was used after the user manually opened
Docker. No restart, volume deletion, schema reset or modification of old datasets.

- New dedicated schema: `doppel_workflow_live_20261110`.
- New journal directory: `data/examples/real-workflow-20261110`.
- Actual Store and index: PostgreSQLStore + PostgreSQLVectorIndex.
- Existing local PyTorch BAAI/bge-small-zh-v1.5, SentenceTransformer CPU,
  normalized embeddings, 512 dimensions, offline loading and length checks.
- Independent index identity: `pgvector:dplv_bd356b4301164b5d`.
- The old temporary FastEmbed ONNX cache was absent. This PyTorch profile is
  distinct and does not establish equivalence with old benchmark embeddings.

Three independent child processes ran:

| Phase | Result | Local embedding calls | Manifest checks |
|---|---|---:|---:|
| Initial | Batch committed; deliberately stop before consolidation | 2 | 0 |
| Restart | Saved stage resumed; consolidation and index cycle completed | 5 | 5 |
| Replay | Already complete; same final hit ID, no new records | 2 | 5 |

Final Store has five records: two raw events, two superseded proposals and one
active canonical candidate. Active fingerprints match the index; inactive entries
are absent. Both completed runs returned the same canonical memory ID. Cross-owner
query returned zero hits in every phase. Query calls still encode queries, including
after workflow completion; completion does not mean zero embedding work.

All fixtures and journals are retained. These are synthetic theme preferences;
the fixed expected text is a smoke assertion, never a runtime query rewrite.

## Local receipts (ignored artifacts)

| File under `data/doppel/` | SHA-256 |
|---|---|
| `personal-workflow-pg-20261110-initial.json` | `1b380bb7c120e54b4bf79286abe8c6015842888fee6fbacaf790df85e4ec0468` |
| `personal-workflow-pg-20261110-replay.json` | `4f8282e588bd9aac7539574607c2a6eb36d64730bb659334f719bed9615c881e` |
| `personal-workflow-pg-20261110-restart.json` | `53ab603ff3ce412d466fd417f2d86db16a11363235bfe0b7175fdd07dc5371cd` |

Credentials were supplied only to child process environment, not persisted in
receipts or journals. The user-facing CLI only emits exception types on failure.

## Additional validation

Storage identity now binds the host recipe to a specific database/schema. Tests
reject storage drift, ambiguous DSN hosts, model/index drift and pending-window
changes. A fake-HTTP integration test exercises the actual compatible structured
output adapter and ReferencePersonalMemoryAnalyzer through the workflow. That
test does not call a real remote model or validate its semantic accuracy.

100 related tests passed; 19 of them cover the workflow and PG-smoke configuration.
Full-repository Ruff and type checks for the entry points passed. No full-suite
rerun this round; core Store/vector algorithms and package dependencies unchanged.

Next: configure a real analyzer, run a small explicitly budgeted sample, then
evaluate extraction/update quality on real offline messages. Continuous ingestion
still needs host handling for late events and an exclusive job owner.
