# Opened LongMemEval ingestion: live prefix and first failure

This records the preregistered opened diagnostic's extraction/Store/vector stage,
not recall, answer quality, full-history completion or AML compliance. No query,
answer, evidence annotation or benchmark category was passed into extraction.
The three original diagnostic histories and all 147 planned chunks remain fixed.

## Actual execution

- Production ReferencePersonalMemoryAnalyzer/Miner, ProposalWriter,
  DeterministicMemoryConsolidator and IndexMaintainer; actual local PostgreSQL
  Store, pgvector and BGE-small-zh-v1.5 / FastEmbed 0.8.0 (512 dimensions).
- Real DeepSeek `deepseek-v4-flash`, json_object, temperature 0, thinking disabled,
  max_tokens 8,192; no automatic retries.
- New ignored profile-specific schema `public_memory_377b84f9e19a` and durable
  run directory `data/doppel/public-memory-ingestion-v1`. No old database/schema,
  benchmark source, report or Docker volume was reset/deleted.
- Plan fingerprint:
  `377b84f9e19a94accbabf06b682a7cf06e2f3ac94456821110452aac211d8dde`.
- First bounded invocation completed 3 chunks: 36 raw events, 25 proposals,
  65 provenance checks with zero failures, 3 provider calls / 17,743 tokens.
  Completed-prefix replay used no API key, made zero new calls/tokens, and kept
  the exact same durable audit/Store counts.
- Continuation completed chunks 4–7, then stopped at chunk 8. Across both paid
  invocations: **8 successful model responses / 44,474 reported tokens**, with
  no missing usage, timeout, retry or unresolved provider reservation. Successful
  HTTP/JSON responses do not imply successful proposal binding or ingestion.

## Final observed prefix

| Observation | Count |
| --- | ---: |
| Planned chunks in three complete histories | 147 |
| Completed chunks | 7 |
| Pending extraction chunk | 1 (chunk 8) |
| Raw messages in completed chunks | 78 |
| Raw messages persisted including pending chunk | 86 |
| Schema-valid drafts across eight model responses | 50 |
| Saved/persisted proposals from completed chunks | 48 |
| Separate conflict governance marker | 1 |
| Final Store raw + derived + governance records | 86 + 48 + 1 = 135 |
| Store/source provenance checks after diagnosis | 147 |
| Provenance failures in this observed prefix | 0 |

All eight analyzer observations are durable; none is missing. No invalid-schema,
low-confidence or exact-duplicate rejection was observed in the completed prefix.
This is not proof of zero semantic extraction errors. Historical assistant raw
text remains agent_output context, not owner authority. Source checks verify
identity/actor/authority, not claim truth or answer relevance. The prefix currently
belongs to only the first diagnostic owner; it is not an adversarial isolation test.

## Failure retained, not skipped

Chunk 8 has two schema-valid drafts and no saved proposal/consolidation plan.
Read-only inspection of its cached output against the query-free source map found:

- one draft binding evidence from both owner and agent;
- one draft whose subject mismatches its single bound evidence actor;
- three references to supplied evidence, zero unknown references.

The existing source-actor/subject gate rejects the response. A cache-only attempt
reproduced `stage=extraction`, `code=evidence-binding-rejected`, one raw-output cache
hit, **zero new calls/tokens**, and no additional proposals. We did not replace
the chunk, reclassify assistant output as owner facts, drop the failure, weaken
the evidence rules or score the seven-chunk prefix as complete histories.

The next design question is general multi-speaker attribution and explicit unsafe
draft quarantine/accounting, not benchmark-specific keyword/prompt exceptions.
Keep the original cached observation and failed run for regression. A protocol
change must be declared and tested generically before restarting full extraction.

## Two real diagnostic/replay fixes

1. The initial Store audit incorrectly treated a legitimate `memory_conflict`
   marker as an unknown record. It now counts governance separately, verifies its
   derived-summary authority and Store source links, and never counts it as an
   owner fact. The original audit-failure artifact remains unchanged. Reporting
   preserves a prior ingestion stop if a later audit also fails.
2. The ingestion host's pending-write check blocked already-completed predecessor
   replay when a later chunk was pending. It now permits an identical completed
   request to revalidate/repair indexes; new or unfinished other requests remain
   blocked. Changed request payloads still conflict before provider access. A
   synthetic regression tests all three cases. No evidence policy changed.

After these fixes, seven completed chunks replayed correctly, then the original
evidence-binding rejection reproduced from cache. Diagnostic edits bind actual
source hashes in reports; the first live artifacts were made on a dirty worktree
based on `ceeed84`, not falsely labeled as later clean-commit executions.

## Preserved local artifacts (ignored)

- `longmemeval-memory-ingestion-preflight-v1.json`: zero-provider/database plan.
- `longmemeval-memory-ingestion-live-v1.json`: first three chunks;
  SHA-256 `3544a2c72fccb0c9d1622225ca26b9efc80de1b4468c79871bbba91f67b6f02d`.
- `longmemeval-memory-ingestion-replay-v1.json`: exact initial audit/count replay;
  SHA-256 `8bec7e56d96b7df4c0695c4b4d1493327976a7013011355ab9e5541dacfebfa7`.
- `longmemeval-memory-ingestion-live-rest-v1.json`: original continuation/audit
  failure retained; SHA-256
  `d3eb14f6c0ba07733c264a5eee753bb9eeaddb643ff9150a2ca6b26672433666`.
- `longmemeval-memory-ingestion-failure-replay-v1.json`: pending-predecessor replay
  bug observation; retained.
- `longmemeval-memory-ingestion-failure-replay-v2.json`: corrected stage attribution,
  raw-output cache reproduction and explicit governance/source audit.

No graph, natural Planner, retrieved-evidence ranking or answer reader ran in this
stage. There is **no new recall/QA score** and no basis for publication readiness.

## Follow-up correction from production cache replay

The later opt-in quarantine replay corrects the manual classification above: chunk
8's first draft cites one owner and one agent message; the second cites one owner
message and has subject owner. The earlier "single bound evidence actor mismatch"
description was inaccurate. An exact production-analyzer/source-binding replay
finds **one** rejected mixed-source draft and **one** source-valid draft, not two
rejected drafts. The old fail-batch response still correctly stops at the first
unsafe draft. Original reports, failed journal and provider outputs remain intact.
See the separately preregistered quarantine profile and its result report; this
correction does not turn source validity into verified semantic truth.
