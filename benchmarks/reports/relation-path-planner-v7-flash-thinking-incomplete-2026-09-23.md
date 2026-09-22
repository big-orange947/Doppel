# Relation-path Planner V7 Flash thinking incomplete runs

Date: 2026-09-23. These are infrastructure diagnostics on the opened V2 corpus, not
quality results. Neither run completed the corpus and neither is eligible as unseen
evidence.

## 4K generation ceiling

- Source commit: `01f3f522296429f5c7e59152b9643e5bf6bf0980`
- Model: `deepseek-flash`, thinking enabled
- Completed cases: 6 / 48
- Provider calls: 13 / 96
- Successful cached outputs: 12
- Stop: first pass of `v2-h07`, HTTP 200, `truncated`
- Input/output/reasoning/total tokens: 47,449 / 20,508 / 18,254 / 67,957
- Report SHA-256: `bb0db2971e48c9928795c19fef441e785d06f31a7d89f7fdc2b6461eff55a020`

All six completed prefix cases were exact, but that prefix is too small and
non-representative to score model quality.

## 8K generation ceiling

- Source commit: `01f3f522296429f5c7e59152b9643e5bf6bf0980`
- Model: `deepseek-flash`, thinking enabled
- Completed cases: 21 / 48
- Provider calls: 43 / 96
- Successful cached outputs: 42
- Stop: first pass of `v2-t06`, HTTP 200, `truncated`
- Input/output/reasoning/total tokens: 157,669 / 114,753 / 106,422 / 272,422
- Report SHA-256: `f3893149338ab1c817df6e4205a105193ce48956f0f0fe740299f233c4d5f72b`

The ordinary hard score divides by all 48 registered cases and therefore records
incompleteness as failure. For diagnosis only, the 21 completed prefix cases achieved:

| Metric | Completed-prefix value |
|---|---:|
| Exact path | 0.904762 |
| Decision | 0.952381 |
| Reason | 0.952381 |
| Relation type | 0.923077 |
| Direction | 0.961538 |
| Wrong execute | 0 |
| Wrong abstain | 1 |
| Forbidden type hits | 1 |

The two non-exact completed cases were an unjustified ambiguity for an explicit loan
query and the recurring `LOCATED_AT` versus `STORED_IN` confusion. No no-path cases had
run before truncation, so the most important over-eager execution controls were not
evaluated.

## Decision

Doubling the ceiling moved, but did not remove, a provider truncation. Do not keep
raising the online Planner allowance or retry truncated outputs until one happens to
fit. The token/latency variance and incomplete safety coverage make this thinking
configuration unsuitable as a default online path Planner.

V7 Flash non-thinking remains the best complete Planner result, but it is still below
the exact-path gate. Further work moves from exact-label prompt iteration to additive
retrieval design: exact paths and widened candidate paths feed a non-exclusive graph
branch, independent semantic retrieval remains mandatory, and downstream evidence
selection decides whether returned material supports an answer.
