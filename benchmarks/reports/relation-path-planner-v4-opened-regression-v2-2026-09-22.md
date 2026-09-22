# Relation-path Planner V4 opened regression v2

Date: 2026-09-22. This run uses all 32 cases from the already opened V1 corpus. It is
regression evidence only and is not eligible as unseen evidence.

## Identity and run accounting

- Source commit: `9ef6cf96b34689257aab72e253ee2fefe05096c3`
- Planner: `doppel.reference-personal-memory-relation-path-planner-v4`
- Planner version: `2.87d56b20d5d08386`
- Provider: DeepSeek `deepseek-v4-flash`
- Selected cases: 32 (`dev`, opened `heldout`, opened `adversarial`)
- Final report cache hits/misses: 32 / 0
- Final report provider calls: 0
- Provider errors: 0
- Planner validation errors: 1
- Report SHA-256: `3e145e888f5f8a7f4a440d4dca041f1ffe7d00cda281c09d2d6be0f1e1b69a5b`
- The only tracked dirty path was the pre-existing `uv.lock`.

The V2 request fingerprints differ from V1. Thirty-two new content-addressed cache
entries were created between 20:03:52 and 20:04:25, so V2 did receive a fresh model
output for every case. The preserved report was produced by a later cache-only replay
at 20:13:36. Consequently its zero-call ledger is correct for that replay, while the
token ledger from the preceding cache-populating pass was not preserved and must not be
reconstructed or guessed.

## Result

| Metric | Gate | Result | Passed |
|---|---:|---:|---:|
| Exact path accuracy | >= 0.90 | 0.781250 | no |
| Decision accuracy | >= 0.95 | 0.781250 | no |
| Reason accuracy | >= 0.90 | 0.781250 | no |
| Over-bound reason accuracy | 1.00 | 1.000000 | yes |
| Wrong execute count | 0 | 0 | yes |

Additional diagnostics:

- execute-decision accuracy: 0.708333
- abstain-decision accuracy: 1.000000
- path recall: 0.708333
- false executable paths: 0
- forbidden relation-type hits: 0
- wrong abstentions: 6
- invalid decisions: 1
- heldout exact path accuracy: 0.916667
- two-hop exact path accuracy: 0.583333

V2 improved exact path and decision accuracy by 9.375 percentage points over V1 and
reduced wrong abstentions from nine to six. It preserved the important safety boundary:
the known three-hop request remained `abstain/over_bound`, every gold abstention was
honored, and no false executable path was emitted. The reliability gates still failed.

## Failure pattern

Three previously rejected two-hop chains recovered. Five other exact two-hop chains
were still labeled `abstain/over_bound`, including explicit outbound and inbound chains.
Several raw explanations explicitly described two relationships while simultaneously
calling the request over-bound. This is not missing prompt wording; the model is
inconsistently combining semantic path extraction, edge counting, and the safety
decision in one output.

The exact inbound one-hop repair query remained `abstain/ambiguous`. One different
one-hop query selected the correct `HELD_BY` path but also populated the soft
`relation_types` field. Strict host validation correctly rejected the contradictory
hard/soft representation. Allowing that contradiction to execute would weaken the
protocol merely to improve a benchmark score.

## Decision

V4 v2 receives no execution authority. Prompt-only tuning on the opened corpus stops
here. The next protocol separates responsibilities:

1. the model emits a non-authoritative, complete ordered path observation with no
   execute/abstain field and no knowledge of the two-hop execution bound;
2. the host validates all observed ontology labels and directions;
3. trusted deterministic code executes exact one/two-edge observations, rejects longer
   observations as `over_bound`, and maps ambiguous/unsupported/nonrelation states to
   structured abstention;
4. a soft `relation_types` suggestion can never override or become the exact path.

This two-stage design addresses the measured failure mechanism without adding
case-specific rules. It must first pass this opened regression and then be evaluated on
a newly authored, independently sealed corpus before any integration with the default
query engine.
