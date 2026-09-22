# Relation-path Planner V5 opened regression v1

Date: 2026-09-22. This run evaluates the two-stage observation/host-decision
architecture on all 32 cases from the already opened V1 corpus. It is regression
evidence only and is not eligible as unseen evidence.

## Identity and budget

- Source commit: `0075dace975e22de9e464497bf47ea2f80525f2d`
- Planner: `doppel.reference-personal-memory-relation-path-planner-v5`
- Planner version: `1.87d56b20d5d08386`
- Protocol: `v5_model_observation_host_decision`
- Provider: DeepSeek `deepseek-v4-flash`
- Selected cases: 32 (`dev`, opened `heldout`, opened `adversarial`)
- Provider calls: 32 / 32 maximum
- Doppel cache hits/misses: 0 / 32
- Input/output/total tokens: 115,179 / 4,621 / 119,800
- Provider errors: 0
- Planner validation errors: 0
- Report SHA-256: `0fe1462f78dd8ec3c50e2611539c4f52edf65d1c1c692ad3c7234af709927ef8`
- The only tracked dirty path was the pre-existing `uv.lock`.

The provider reported 42,987 cache-miss input tokens and 72,192 provider-cached input
tokens. Those are provider prompt-cache accounting, distinct from Doppel's raw-output
cache, which had zero hits in this first V5 run.

## Result

| Metric | Gate | Result | Passed |
|---|---:|---:|---:|
| Exact path accuracy | >= 0.90 | 0.968750 | yes |
| Decision accuracy | >= 0.95 | 1.000000 | yes |
| Reason accuracy | >= 0.90 | 1.000000 | yes |
| Over-bound reason accuracy | 1.00 | 1.000000 | yes |
| Wrong execute count | 0 | 0 | yes |

Additional diagnostics:

- execute-decision accuracy: 1.000000
- abstain-decision accuracy: 1.000000
- one-hop exact path accuracy: 1.000000
- two-hop exact path accuracy: 0.916667
- no-path accuracy: 1.000000
- hop-count accuracy: 1.000000
- relation-type accuracy: 1.000000
- direction accuracy: 0.972222
- path recall: 1.000000
- false paths: 0
- missed paths: 0
- forbidden relation-type hits: 0
- wrong abstentions: 0
- invalid decisions: 0

Every registered gate passed. All seven V4 v2 failures recovered: the five exact
two-hop chains executed, the inbound repair query executed, and the hard/soft
`HELD_BY` duplication was normalized by the host. The three-hop request was observed
as three edges and deterministically mapped by the host to `abstain/over_bound`.

## Remaining error

One dev two-hop case selected the correct `HELD_BY -> LOCATED_AT` types and hop count
but emitted `HELD_BY/inbound` instead of outbound when starting from the camera and
traversing to its custodian. The same run correctly emitted outbound for the equivalent
one-hop passport-custody question. The catalog definition and gold direction are
consistent, so this is a model direction fluctuation, not a host-decision or dataset
label error. It would send an actual graph traversal the wrong way and therefore
remains a real path-planning failure even though the execute/abstain decision was safe.

No prompt change is made from this opened example. V5 remains outside the default
query engine.

## Decision

The two-stage architecture passes opened regression and is eligible for an independently
sealed evaluation. It does not yet receive product execution authority. Before opening
the new corpus:

1. freeze a larger V2 corpus with no repeated V1 queries;
2. pre-register exact path, decision, reason, over-bound, wrong-execute, type,
   direction, and completeness gates;
3. keep the V5 prompt, schema, host bound, provider settings, and relation catalog
   unchanged;
4. run every V2 case once with a fresh content-addressed cache namespace;
5. treat any subsequent rerun as opened regression rather than unseen evidence.
