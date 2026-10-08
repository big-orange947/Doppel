# Same-Reader rank-fit comparison: no demonstrated answer gain

The [plan](public-memory-packing-reader-plan-2026-10-08.md) and implementation
were committed as `41019ac` before the five new calls. The Reader, schema, model,
generation settings and original thirty logical question/channel rows are
unchanged. Only five request contexts differ; twenty-five exact outputs are
reused from a validated, read-only original cache. No retrieval, extraction,
Judge or Store/index write executes.

## Observations, not an accuracy score

All thirty rows complete with valid output structure and legal citation IDs.
Five changed contexts produce four changed answer strings. More context and
changed wording do not establish an answer-quality improvement.

| Logical row | Case/channel | Before versus after |
| --- | --- | --- |
| 9 | `0e5e2d1a`, raw | Both deliver 38 subjects; wording changes. |
| 11 | `0e5e2d1a`, combined | Identical answer delivering 38 subjects. |
| 12 | `86f00804`, raw | Both name The Seven Husbands of Evelyn Hugo with a qualification about subsequent reading updates; wording changes. |
| 26 | `gpt4_2f91af09`, combined | Both refuse a definite writing total. The new answer mentions a tentative sum of 23 but does not commit to it; `abstained=true`. |
| 27 | `7a8d0b71`, raw | Both deliver the $2,000 budget. The new wording adds a campaign timeline; this is not counted as an independently verified QA gain. |

This is a bounded reading of the changed answers, not an exhaustive independent
semantic audit. No new correctness labels are produced (`answer_correct=null`,
`qa_metrics_available=false`). In particular, merely mentioning an arithmetic
value while refusing the requested total is not automatically a successful
answer. The previous Judge labels and failures remain untouched. Language drift
also remains: four changed-context outputs are Chinese despite English questions.

The previous zero-provider result still holds: annotated-turn provenance coverage
is raw95% / derived80% / combined100%, unchanged by rank-fit packing. Source links
do not prove retained answer-bearing facts. Together these experiments demonstrate
neither better coverage nor a clear answer benefit. Keep the baseline/default;
leave rank-fit opt-in and close this same-ten-history tuning experiment.

## Usage and replay

Five new Reader attempts succeed, zero failures/retries, zero Judge calls:
30,039 input +720 output = **30,759 reported tokens**. Input usage reports
27,136 cached and 2,903 cache-miss tokens; every attempt has complete usage.
The durable lifetime cap is five attempts, not a guaranteed token/billing cap.

A separate key-free cache-only process completes all thirty rows with **zero
new calls**. Output/check/request/answer-change projections match exactly, and
cumulative usage is unchanged. Original input hashes and the parent cache inventory
remain unchanged. No old results, prompts, databases or `uv.lock` are rewritten.

Full regression: **1,327 passed /33 skipped /3 subtests**, with one existing
Graphiti Pydantic warning. Targeted Reader/experiment tests:34 passed. Whole-repo
Ruff, changed-file formatting and scoped Pyright pass. Eleven new test cases
check exact baseline binding, unchanged-cache validation before calls, durable
failure budgets, gold-blind requests and zero-call replay; they are engineering
checks rather than model-intelligence evidence.

## Artifact binding and next stage

Ignored live report `data/doppel/longmemeval-packing-reader-live-v1.json` SHA-256:
`784bf2b2937fc074df8bf94575314bcc17ca523ccc34d253ef3dae7f80bda553`.
Replay report `data/doppel/longmemeval-packing-reader-replay-v1.json` SHA-256:
`0b6adbfdd76738909daa240716c13639587f6c5094d03d966ebda87863016c7a`.
Plan fingerprint:
`907fbfc93547396b0b4502387629f283d2e83cf3ea1239b9406819ba6203fa2b`.
Parent and packing hashes are specified in the frozen plan.

Next is the separately frozen fifty-new-history expansion, not more prompt
adjustments on these opened questions. Completed public QA coverage remains
thirteen distinct questions out of500; new ingestion alone cannot increase this
denominator. This is small public diagnostic work, not independently blind,
full LongMemEval, production Planner/Graphiti or AML evaluation.
