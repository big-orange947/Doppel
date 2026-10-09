# Independent observation clock diagnostic: no answer uplift claim

Code/protocol frozen in `2d77ae6` before five calls. One already-opened source-order
second history, not an independent sample or full LongMemEval/AML score. Old causal
receipts and the third count failure remain unchanged.

## Live result

The explicit supplied-history cutoff is `2023-06-01T17:50:00Z`, while relative-date
planning/current validity uses the question reference `2023-06-01T05:09:00Z`.
It is derived from all 431 supplied turns (70 after the question reference),
not selected annotations. Production binds plan V3, not a modified V2 payload.

The answer is reference-correct (Ford F-150), with 2/2 annotated turns/sessions
and four legal, source-supported anchored quotations. No contradictions reported
by the citation judge; semantic truth is not independently verified. Reader still
answers in Chinese to an English question.

| Returned channel | Records | After reference | After observation cutoff |
| --- | ---: | ---: | ---: |
| Base candidates | 57 | 5 | 0 |
| Hybrid candidates | 20 | 2 | 0 |
| Raw dialogue | 20 | 0 | 0 |
| Backing sources | 26 | 2 | 0 |

Thus the new policy actually admits some later observations, without silently
changing the fact-validity reference or disabling the finite knowledge gate.
The fixed 20-item/22783-byte packed IDs are unchanged from the earlier strict
development replay: this particular answer did not require the newly admitted
records. Both protocols answer correctly; no accuracy improvement is claimed.

One WORKS_ON path is consumed, but its supporting record was already discoverable
in the base candidates. This is not evidence of graph uplift. CUDA scores 136
pairs with no truncation. No Store, vector or graph writes; snapshots unchanged.
Source failures remain zero. Execution stays `review_required` because the
unclassified `unresolved current/as-of conflict in topic <unkeyed>` warning
remains. Correct answers do not turn an unresolved product warning into a pass.

## Calls and replay

| Stage | Calls | Tokens |
| --- | ---: | ---: |
| Planner | 2 | 23627 |
| Reader | 1 | 6113 |
| Task judge | 1 | 601 |
| Citation judge | 1 | 8537 |
| Total | 5 | 38878 |

Zero failures/retries/missing usage. Empty-key replay reuses the immutable
retrieval checkpoint and hits the three downstream caches, adds zero requests,
and preserves plan/retrieval/Reader/judges/context/packing/evidence scores exactly.
This is not a fresh planner/GPU execution.

- Live: `data/doppel/public-memory-provided-clock-scope02-live-v1.json`, SHA-256
  `241f3c82cde0c531fefdf671d1a4eef4ab9de3f2cdd624e0d65510c46ec40209`.
- Replay: `data/doppel/public-memory-provided-clock-scope02-replay-v1.json`, SHA-256
  `976a05571ae8395eedf42a24925271f0fe37c6f7e92ce53a7aa16fd6fea5392f`.
- Frozen plan: `255cd61cb9691c573f415cb8d5d4a50cf738e80b866ffc0bfe58f2127c22e5c4`.

Validation for the clock change: 1475 passed, 33 skipped, 3 subtests; Ruff passes.
The one Graphiti dependency deprecation warning is retained. `uv.lock` remains
user-modified and unstaged. Further questions must remain source-order selected,
with all clock policies and model/context identities frozen separately.
