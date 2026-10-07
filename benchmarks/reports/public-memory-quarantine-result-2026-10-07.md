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
- Schema/provider/storage/index and configured draft-bound errors still fail; no
  broad exception swallowing, citation repair or authority promotion is allowed.
- Generic synthetic tests cover valid+unsafe siblings, all-rejected batches, every
  closed rejection code, immutable input, default compatibility, changed-policy
  run binding, durable replay and invalid parent caches with no rebilling.
- Full regression run: 1109 passed, 33 skipped (plus one newly added plan-binding
  test subsequently verified in the 89-test targeted run). Ruff/type checks and an
  offline isolated wheel import/configuration smoke pass.

Preserved ignored artifact: `longmemeval-memory-quarantine-cache-v1.json`, SHA-256
`ae620559c459301a0cb7d9cc7a8d76260acf9ac257120a43a0edb56010edc274`.
This first replay ran on a dirty worktree based on cb1a0be with source fingerprints,
not a falsely claimed later clean commit. Raw parent caches and old failure artifacts
are not rewritten. A committed restart replay and bounded live continuation follow.
