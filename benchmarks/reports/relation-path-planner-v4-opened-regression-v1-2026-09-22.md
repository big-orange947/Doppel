# Relation-path Planner V4 opened regression v1

Date: 2026-09-22. This run uses all 32 cases from the already opened V1 corpus. It is
regression evidence only, is not eligible as unseen evidence, and may be used to refine
V4 before a new corpus is created.

## Identity and budget

- Source commit: `ea038a04726b6305c438aeb7bc061df7f9e5dbf7`
- Planner: `doppel.reference-personal-memory-relation-path-planner-v4`
- Planner version: `1.87d56b20d5d08386`
- Provider: DeepSeek `deepseek-v4-flash`
- Selected cases: 32 (`dev`, opened `heldout`, opened `adversarial`)
- Provider calls: 32 / 32 maximum
- Cache hits/misses: 0 / 32
- Input/output/total tokens: 134,699 / 4,692 / 139,391
- Provider errors: 0
- Planner validation errors: 1
- Report SHA-256: `c021da2a6182ba037702feb8b753fce392c1507cf541aed688800cb6ea792d26`
- The only tracked dirty path was the pre-existing `uv.lock`.

## Result

| Metric | Gate | Result | Passed |
|---|---:|---:|---:|
| Exact path accuracy | >= 0.90 | 0.687500 | no |
| Decision accuracy | >= 0.95 | 0.687500 | no |
| Reason accuracy | >= 0.90 | 0.687500 | no |
| Over-bound reason accuracy | 1.00 | 1.000000 | yes |
| Wrong execute count | 0 | 0 | yes |

Additional diagnostics:

- execute-decision accuracy: 0.625000
- abstain-decision accuracy: 0.875000
- path recall: 0.625000
- false executable paths: 0
- forbidden relation-type hits: 0
- wrong abstentions: 9
- invalid decisions: 1

The overall regression gate failed. V4 v1 fixed the original three-hop problem: the
known over-bound request returned `abstain/over_bound` with empty steps. It also never
executed a request whose gold decision was abstain. This safety improvement came with
unacceptable over-abstention.

## Failure pattern

Eight of twelve exact two-hop questions were mislabeled `abstain/over_bound`, although
their complete path needs exactly two relationship edges. Four other two-hop questions
executed correctly. This indicates the model did not consistently count hops as graph
edges; it sometimes treated the start/intermediate/end structure or linguistic clauses
as exceeding the limit.

One exact inbound one-hop repair query was mislabeled `abstain/ambiguous`. The relation
definition uniquely identifies the requested predicate, but its evidence constraint
does not by itself prove completed repair. V4 v1 conflated relation-planning ambiguity
with downstream answer-evidence sufficiency.

One ambiguous no-path query correctly proposed `abstain/ambiguous` with empty steps but
also retained soft `relation_types`. V4 v1 prohibited all relation candidates during
abstention, so strict validation rejected an otherwise safe result. Soft V2 candidates
do not grant graph execution authority and can help ordinary recall.

## Decision

V4 v1 receives no execution authority. The opened regression justifies a V4 v2
protocol refinement, not a score reinterpretation:

1. count hops only as directed relationship edges;
2. state that start -> intermediate -> endpoint is exactly two hops;
3. reserve over-bound for a required third edge;
4. separate path ambiguity from final answer-evidence sufficiency;
5. allow non-executing soft relation candidates during abstention.

The same opened corpus may be rerun as regression after these changes. It cannot regain
held-out status. Passing regression would only authorize building a new V2 dev corpus
and independently unopened sealed corpus.
