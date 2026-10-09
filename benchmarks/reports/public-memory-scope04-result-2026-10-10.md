# Fourth highest-config question: evidence found, personalized answer refused

Graph/schema/QA were frozen before their calls (`8f05d06`, `b3a8307`, `bee7a4d`).
This is the fourth opened source-order development history, not a blind sample,
formal LongMemEval/AML result or statistically comparable aggregate accuracy.
Earlier failed answers and their immutable receipts remain.

## Outcome and attribution

Case `38146c39` requests advice about improving chocolate-chip cookies. The memory
of the owner's prior sugar experiments is available as both an extracted fact
(`mem-d22465b3e3ef4d18907d6a8ce4bd3a5b`) and its original owner message
(`mem-33cd0206f6934e688f135f36877993e4`). The Reader even cites both while refusing
because no explicit cookie advice appears in the supplied items.

Annotated turn/session coverage is **1/1**; 20 whole packed items/20902 UTF-8 bytes.
The question is personalized advice, not a request to recover a prior recipe.
The reference-only task judge marks refusal incorrect. The citation judge, however,
calls the absence claim supported and also calls the refusal correct. Preserve
this disagreement; do not take its answer-correct field as the task score or call
quote anchoring a proof that the answer fulfilled the user's request.

Primary attribution: **Reader task/personalization behavior**, not absence of the
required preference memory. It treats relevant preference evidence as insufficient
unless a ready-made answer exists. This is not repaired by more graph authoring.
The Reader follows the English question's language here; earlier language drift
remains in its other immutable runs. Nineteen citations are legal/unique, nineteen
judge quotations are anchored; that verifies IDs/text, not whole-answer adequacy.

## Retrieval and remaining product limitations

Natural Planner chooses lookup/unbounded, an entity mention from the question and
no requested relation types. One graph exploration returns no promoted paths;
no exact typed-path searches. Do not claim graph contribution or uplift. The
memory/vector/raw/source composition still supplies the relevant preference.
CUDA reranker scores 180 pairs, no truncation. Raw/backing channels have 20/31
candidates; source failures zero, Store/vector/fourth-graph snapshots unchanged.

Execution remains `review_required`. Two explicit governance conflict markers
appear on bedroom-lighting and camping-packing topics because broad candidates
matched those topics; neither is used to repair the task answer. Their semantic
validity/relevance is not independently established. The generic empty-topic
repair does not suppress actual markers. Candidate relevance and conflict
precision still need development; this report is not a clean hard-gate pass.

Both observation horizon and query reference are `2023-05-30T20:02:00Z`; all 538
supplied turns precede it. This question offers no independent test of a later
knowledge horizon. No expected values, source timestamps or Store data were patched.

## Cost, graph coverage and replay

| Stage | New calls | Reported tokens |
| --- | ---: | ---: |
| Real graph authoring | 918 | 3821098 |
| Source-name schema | 8 | 16668 |
| Natural Planner | 2 | 26717 |
| Reader | 1 | 6595 |
| Reference-only task judge | 1 | 946 |
| Citation judge | 1 | 10490 |
| Fourth-history total | 931 | 3882514 |

No request failures/retries/missing usage. Graph completion: 219 projections,
154 rich/65 fallback-only, 256 distinct rich edges and 169 types. Two missing-target
warnings (HAS_ROUTINE, TRIES_TO_REDUCE) remain extraction losses, not erased by
successful fallback/provenance. Ready graph histories: 4/50, 834 projections.

Empty-key replay adds zero requests, hits three downstream caches, reuses the
retrieval checkpoint and exactly preserves plan/retrieval/Reader/judges/context/
packing/evidence score. It is not a fresh natural-planner/GPU execution.

- Live QA: `data/doppel/public-memory-next-query-scope04-live-v1.json`, SHA-256
  `cd9a48c2cfe4cad0b2b0d23d2a0afeda5a6a966ec5d5b25f40a6fd7df216a01f`.
- Replay: `data/doppel/public-memory-next-query-scope04-replay-v1.json`, SHA-256
  `17ff470c8c4bc96d968d0f6aa0fbbf2a406daa95fff8517058297507d2060933`.
- Frozen plan: `95d24b2ae584849516b027a827586f0166021173556a7b13d351fd2e09c3c8b1`.

Code validation remains 1501 passed/33 skipped/3 subtests; Ruff passes. No new code
after the frozen query. `uv.lock` stays user-modified and unstaged. The fifth
source-only graph run proceeds independently under its already frozen plan and
will keep the unchanged Reader/QA protocol; any future Reader change needs a
separate gold-free contract/control profile, not cookie-specific guidance or
retroactively improved scoring of this failed run.
