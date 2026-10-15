# First ten source histories complete; fourth graph interrupted

The approved recovery completed the identical pending request (6,383 tokens,
one successful call). The separately frozen continuation completed all 119
remaining chunks (119 successful calls, 625,695 tokens, no retries). All old
attempt rows, including the failed transport request with missing usage, remain.

| Source checkpoint | Result |
| --- | ---: |
| Fully ingested selected histories | 10 / 50 |
| Completed source chunks | 499 / 2,479 |
| Original raw messages | 5,016 |
| Derived records including inactive | 1,954 |
| Governance markers | 30 |
| Total Store records | 7,000 |
| Source provenance checks / failures | 7,494 / 0 |
| Historical source attempts / successes / failures | 500 / 499 / 1 |
| Known reported source tokens | 2,460,363 |
| Source calls without usage | 1 |

`partial` on the receipt means the **whole fifty-history cohort** remains partial;
the frozen first-ten target is fully complete and `stage_verified=true`.
Provenance checks verify bindings, not semantic truth. The original 350-chunk
continuation consumed 351 attempts including the authorized extra recovery, not
a falsely reported zero-failure first run. No new source-stage questions or gold
were opened. Observed provider balance 56.20 to 54.82 CNY includes concurrent
graph usage and is not exclusive source billing.

## Fourth graph checkpoint (not ready for QA)

Projection completed 126/162 eligible memories, with 141 rich edges in verified
records, then stopped on a new `transport_error` / connection-refused chain.
529 attempts: 528 successes and one failure, 2,203,888 known reported tokens,
one missing usage. No budget exhaustion, automatic retry or graph-slot repair.
All completed data is retained. Selected Store, vectors, source journal and other
cohort graph scopes are unchanged. No scope-04 schema, question, Reader or judge
execution; no new answer scores are available from these operational stages.

Task grading still covers three of fifty fixed questions: full 3/3, raw 2/3 in
the provisional reference-only task judge. The separate citation judge marks the
same third raw answer correct, so even that one-row difference is grade-sensitive,
not demonstrated retrieval/graph uplift. See the unchanged scope-03 report.

## Bound artifacts

- Successful recovery receipt:
  `cd66c62035656369cb793859b14b23b424ee02bf7cb7233dc3cec861e102b42c`.
- First-ten continuation receipt:
  `a577fc794e17b79ec9d07e1444f2522e09deac1c2937a5a370e39da50c6dcdf4`.
- Interrupted scope-04 graph receipt:
  `db3c5a7083247521f7c1bfd5a3bc9a077eca98b9b07b8a00045ae0b21b5f4b04`.
- Original failed source receipt remains:
  `a4d2ff95f6286f987caf26eb1af993b7594d6b1db8460fb61e0b3e694ed7e750`.

Verification: **1,852 passed, 33 skipped, three subtests passed**; Ruff repository
check passes. Twelve new operational tests, no core/model/prompt edits. `uv.lock`
remains the user's original unstaged change. These are not official LongMemEval,
independent blind or AML results, and no publication gate is granted.
