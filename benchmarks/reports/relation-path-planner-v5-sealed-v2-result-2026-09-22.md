# Relation-path Planner V5 sealed V2 result

Date: 2026-09-22. This is the immutable first provider run over the frozen V2 corpus.
The corpus was eligible as unseen evidence before the run and is opened by this result.
All later V2 runs are regression evidence only.

## Integrity and budget

- Source commit: `2b8e2281bf93b8fa0aadb4b50a1e831c5af1cddc`
- Dataset fingerprint: `f27a04a7de38eb9346d80a8a579e17382e58ac92fdf07ebb3e7bb631156a0143`
- Planner: `doppel.reference-personal-memory-relation-path-planner-v5`
- Planner version: `1.87d56b20d5d08386`
- Provider: DeepSeek `deepseek-v4-flash`
- Provider calls: 48 / 48 maximum
- Doppel cache hits/misses: 0 / 48
- Dedicated raw-output cache entries: 48
- Input/output/total tokens: 172,727 / 6,626 / 179,353
- Provider errors: 0
- Planner validation errors: 0
- Complete cases: 48 / 48
- Report SHA-256: `ae74533e7411e479371dbe2badfffc6c0e343c057a7d47048d7239138d6a7b05`
- The only tracked dirty path was the pre-existing `uv.lock`.

The report dataset identity, source commit, cache count, report sidecar, and the
pre-registered plan all agree. The result is a valid failed sealed evaluation, not an
incomplete run or cache replay.

## Pre-registered result

| Metric | Gate | Result | Passed |
|---|---:|---:|---:|
| Complete valid execution | 48 / 48 | 48 / 48 | yes |
| Exact path accuracy | >= 0.90 | 0.750000 | no |
| Decision accuracy | >= 0.95 | 0.854167 | no |
| Reason accuracy | >= 0.90 | 0.854167 | no |
| Over-bound reason accuracy | 1.00 | 1.000000 | yes |
| Relation-type accuracy | >= 0.98 | 0.604167 | no |
| Direction accuracy | >= 0.95 | 0.645833 | no |
| Path recall | >= 0.95 | 0.781250 | no |
| One-hop exact path accuracy | >= 0.90 | 0.937500 | yes |
| Two-hop exact path accuracy | >= 0.85 | 0.312500 | no |
| No-path accuracy | 1.00 | 1.000000 | yes |
| Wrong execute count | 0 | 0 | yes |
| Forbidden relation-type hits | 0 | 1 | no |
| Provider/planner errors | 0 | 0 | yes |

The gate failed. V5 receives no default-query-engine execution authority.

## What remained safe

All 16 no-path controls were handled correctly, including all four three-hop requests,
four ambiguous requests, four unsupported predicates, and four non-relation requests.
There was no execution on a gold-abstain case, no false path on a no-path case, and no
invalid provider output. The model/host split therefore preserved the security bound.

This does not mean every executed path was correct. `wrong_execute_count` measures
execute versus abstain classification; incorrect types, order, directions, or missing
edges on answerable cases are caught by the independent path gates.

## Failure anatomy

Twelve cases missed exact path gold:

- Seven answerable cases were over-abstained: one location enumeration was called
  nonrelation and six implicit/inbound two-hop paths were called ambiguous.
- One repair query selected `REPAIRED_AT` instead of `REPAIRED_BY`, producing the sole
  forbidden-type hit.
- One shared-purchase path reversed both directions.
- One shared-birthplace path omitted the second inverse edge.
- One double-inbound path emitted both correct types in sentence order rather than
  traversal order.
- One location-to-custodian composition omitted its location edge.

The concentration is clear: one-hop exact path was 0.9375, while two-hop exact path was
0.3125. Inbound-trait exact accuracy was 0.3077, shared-endpoint accuracy 0.25, and
double-inbound accuracy 0.0. The V1 opened corpus overrepresented explicit sequential
chains and materially overstated generalization.

One gold contract deserves separate follow-up: “储物间里目前有哪些物品？” can be
modeled as `LOCATED_AT/inbound`, but the V5 instructions also allow ordinary enumeration
without an explicit relation traversal to be nonrelation. That is a protocol ambiguity,
not justification to change the sealed score. The original failure remains recorded.

## Architectural conclusion

Separating model observation from host execute/abstain was necessary but insufficient.
V5 still asks the model to serialize a path in traversal order and assign a direction
at every step. New syntax exposed four recurring errors: sentence order versus traversal
order, shared-endpoint reversal, omitted implicit edges, and excessive ambiguity.

The next experiment must not add V2 sentence-specific prompt rules. Instead it should
change representation:

1. the model emits declarative relation atoms with named endpoint references;
2. each atom binds a relation definition's source role to one reference and target role
   to another, without an ordered direction field;
3. fixed `anchor` and `answer` references plus shared intermediate references describe
   topology;
4. host code validates the atom graph, finds the unique anchor-to-answer path, orders
   its edges, and derives inbound/outbound deterministically;
5. the existing two-edge execution bound and V4 safe draft remain unchanged.

V2 is now an opened regression corpus and may be used to develop that representation.
Any later claim of unseen improvement requires a new frozen V3 corpus.
