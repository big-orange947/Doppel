# Opt-in batch quarantine: cached production replay

This is a generic acceptance/observability change in the opened LongMemEval
ingestion diagnostic, not a prompt, question, answer or corpus change. The
[preregistered plan](public-memory-quarantine-plan-2026-10-07.md) retains all 147
chunks and source/authority gates. Default fail-batch behavior remains unchanged.

## Cached replay

- Exact old provider outputs reused through strict read-only parent envelopes;
  model/analyzer prompt/schema/input identity unchanged. Eight cache hits, zero
  invalid cache entries, **zero new provider calls/tokens**, no API key read.
- New bound directory `data/doppel/public-memory-ingestion-quarantine-v1` and
  PostgreSQL schema `public_memory_a0ac032f2ec3`; old failed profile preserved.
- Plan fingerprint:
  `a0ac032f2ec389e05dab32264c6985b3c89c9aa736db022679ac74ae116c49a4`.
- Default compatibility preflight reproduces old plan fingerprint exactly:
  `377b84f9e19a94accbabf06b682a7cf06e2f3ac94456821110452aac211d8dde`.

| Observation | Count |
| --- | ---: |
| Processed / planned chunks | 8 / 147 |
| Original raw messages retained | 86 |
| Schema-valid drafts | 50 |
| Accepted proposals / derived records including inactive | 49 |
| Explicit evidence rejections | 1 (mixed source actors) |
| Invalid-schema / low-confidence / duplicate drops | 0 / 0 / 0 |
| Separate conflict governance marker | 1 |
| Total raw + derived + governance Store records | 136 |
| Store/source provenance checks / failures | 148 / 0 |

The partition is 50 = 49 accepted + 1 evidence rejection. This is source-binding
accounting, **not 98% extraction correctness**. Semantic truth remains unverified.
The eight chunks are only a prefix of the first diagnostic owner, not complete
histories or a new adversarial-isolation result. Graph/Planner/search/reader did not
run; no recall/QA/AML score is emitted.

Chunk eight contains one owner-subject draft citing both owner and agent, and one
owner-subject draft citing only owner. Exact production replay corrects the prior
manual description of the second draft as a subject mismatch. The first is rejected
without editing citations or authority; the second passes the existing source gate.
The old fail-batch profile correctly still stops on the first violation.

## Policy and verification

- Only the batch Miner supports this explicit policy; online extraction and default
  fail-batch callers retain their behavior and old configuration fingerprints.
- Quarantine requires subject/source matching, including when a caller bypasses
  Pydantic validation via model_copy. It records closed first-failure reasons and
  schema-valid draft indices, not rejected text/IDs/exception payloads.
- Host audit validates rejection items, counts and the full proposal partition.
  All-rejected batches retain original raw sources and explicit zero proposals.
- Top-level schema/provider/storage/index and configured draft-bound errors still
  fail; existing reference per-draft schema rejection is unchanged. No
  broad exception swallowing, citation repair or authority promotion is allowed.
- Generic synthetic tests cover valid+unsafe siblings, all-rejected batches, every
  closed rejection code, immutable input, default compatibility, changed-policy
  run binding, durable replay and invalid parent caches with no rebilling.
- Final full regression run: **1110 passed, 33 skipped**, plus 3 subtests passed.
  Targeted run: 89 passed. Whole-repository Ruff lint/type checks, changed-file
  format checks and offline isolated wheel import/configuration smoke pass.
  Whole-repository format checking additionally finds 67 previously unformatted
  files outside this change; those unrelated files were not mechanically rewritten.

Preserved ignored artifact: `longmemeval-memory-quarantine-cache-v1.json`, SHA-256
`ae620559c459301a0cb7d9cc7a8d76260acf9ac257120a43a0edb56010edc274`.
This first replay ran on a dirty worktree based on cb1a0be with source fingerprints,
not a falsely claimed later clean commit. Raw parent caches and old failure artifacts
are not rewritten. A committed restart replay and bounded live continuation follow.

## Committed restart and live continuation

Execution source: `c3cbf930ed09603fdd15ddc4f35af2f037784107`; the only tracked
dirty path was the pre-existing user-owned `uv.lock`, which was not changed/staged.
Committed completed-prefix replay made zero calls/tokens and reproduced the exact
cached audit and Store counts. The old default profile was also reproduced from
cache: seven completed chunks followed by the same eighth-chunk evidence failure,
zero new calls/tokens. Quarantine did not conceal the original failure.

Twelve new live chunks completed, moving the prefix to 20/147. This used 12 new
calls / 59,946 reported tokens. A subsequent unchanged-profile continuation
completed chunks 21–36, then stopped at chunk 37's consolidation stage. It used
17 additional successful model responses / 84,495 reported tokens. The model
response for chunk 37 is cached and its proposal plan is saved; later chunks were
not skipped or run after the failure.

| Final observed opened prefix | Count |
| --- | ---: |
| Completed / planned chunks | 36 / 147 |
| Pending consolidation chunk | 1 (chunk 37) |
| Raw records including pending chunk | 392 |
| Schema-valid drafts across 37 responses | 176 |
| Accepted proposals from completed chunks | 164 |
| Accepted/persisted proposals in pending chunk | 11 |
| Explicit evidence rejection | 1 (mixed source actors) |
| Invalid-schema / low-confidence / duplicate drops | 0 / 0 / 0 |
| Derived records including pending/inactive | 175 |
| Separate governance records | 2 |
| Total Store raw + derived + governance records | 569 |
| Store/source checks / failures | 614 / 0 |
| New-profile paid responses / reported tokens | 29 / 144,441 |
| Original plus new responses / reported tokens | 37 / 188,915 |

No new-profile missing usage, retry, provider error or unresolved reservation was
observed. These are reported token totals, not a billing guarantee. The rejection
partition is 176 = 175 accepted + 1 evidence-rejected. All 37 analysis observations
are durable. Pending records must not be advertised as fully consolidated/indexed
or a completed searchable history. Source validity is not extraction correctness.

## New generic consolidation defect, retained

Read-only production `ConsolidationRunner.plan_once` reproduces
`ConsolidationPlanningError` at `_validate_source_compatibility`. Three proposed
decisions include one conflict group with two owner/human_self records whose
trusted kinds differ (`fact` versus `state`). The deterministic consolidator's
topic grouping omits trusted actor/authority/kind partitions, while the execution
gate correctly rejects cross-kind sources. No plan was executed during diagnosis,
and no additional model call was made.

Next: add generic trusted-identity partitioning to deterministic grouping, keep the
execution guard, and test actor/authority/kind variation on synthetic records.
Declare a new consolidator identity and fresh host profile rather than changing
this already-bound failed journal in place. Reuse both preserved raw-output cache
parents to replay the 37 observed responses without rebilling before continuing
the same remaining histories. Do not delete/skip chunk 37, relax the gate, or report
partial-history retrieval as full benchmark performance.

Additional preserved ignored artifacts:

- `longmemeval-memory-quarantine-committed-replay-v1.json`, SHA-256
  `5b4f434c7433d0678c14ed864acda3a1b9bcdfa39f6f40179b3298661303d86d`.
- `longmemeval-memory-default-failure-regression-v1.json`: old failure reproduced.
- `longmemeval-memory-quarantine-live-prefix-v1.json`, SHA-256
  `0e8e395b0195b3da74439fe1e11d011dcbdcff609ef01da2924b059c0ebb8a60`.
- `longmemeval-memory-quarantine-live-completion-v1.json`, SHA-256
  `ea7ae4f677f8ed8f1d11998a8180d6d079a994981e782ef30cbca600e77f9d1f`;
  despite its intended completion filename, its actual status is **failed**.

Reserved histories remain unrun. Graph, natural Planner, retrieved-evidence ranking
and answer reader were not executed. The model profile remains noncompliant with
the later AML academic rules. There is still no new recall/QA or release claim.
