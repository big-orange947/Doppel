# Fifth prospective pair: correct count, different evidence-turn coverage

Fixed case `d23cf73b` asks how many cuisines the owner learned to cook or tried
in recent months. Both frozen profiles identify Ethiopian, Korean, Indian and
vegan cuisine and answer four. Primary reference-only task judge and separate
citation judge agree both correct. These DeepSeek judgments remain provisional,
not independent verification or official LongMemEval/AML evaluation.

| Metric | Full high-config | Raw vector + reranker |
| --- | ---: | ---: |
| Primary task / citation correctness | Correct / correct | Correct / correct |
| Annotated turns covered | **3/4** | **4/4** |
| Annotated sessions covered | 4/4 | 4/4 |
| Declared citations legal / quotes anchored | Yes / yes | Yes / yes |
| Provisional citation support | Supported | Supported |
| Whole context items / canonical UTF-8 bytes | 20 / 20,736 | 15 / 23,760 |
| QA provider calls / tokens | 5 / 39,015 | 3 / 16,448 |

## Evidence difference is retained, not scored away

Deterministic source-position audit confirms full omits labelled turn `(47, 0)`:
the owner reports a vegan cooking class and inspiration toward plant-based eating.
Full includes the **same session's original turn `(47, 8)`**, which explicitly
describes that vegan class and learning to make vegan lasagna. Raw contains both.
Thus full's 0.75 labelled-turn recall is real, while an alternative original source
still supports the fourth cuisine. Do not rewrite either annotated-turn metric,
infer missing factual support solely from missing that annotation, or call this a
graph uplift. Raw packs fewer items because its unchanged whole-prefix byte cap
is reached; no truncation/answer-conditioned expansion is introduced.

Full follows the count branch: exhaustive scoped Store read, aggregation
`indeterminate`, graph path/exploration both zero, memory reranker not run and path
reranker not applicable. The production engine does **not** certify an exact
predicate count from relevance candidates. Reader v2 derives four from supplied
items and qualifies the possible omissions. Raw says at least four and similarly
qualifies scope/time completeness. Derivation fields are structurally valid, not
an independent entailment or arithmetic proof. Both answer in Chinese to English
questions: prior language drift persists unchanged.

The cited source set includes both original and derived versions of some claims;
these are not independent witnesses. Full's extra assistant kimchi advice is not
by itself proof the owner cooked kimchi; a separate owner bibimbap statement
supports Korean cuisine. The fermentation-workshop taxonomy discussion is Reader
interpretation, not a structured-engine certificate. Preserve fallible judgments.

## Runtime, accounting, replay

All 211 eligible graph records projected with 856 successful attempts / 3,660,896
tokens; zero failures/missing usage/retries/slot repairs. Actual snapshot has 214
distinct rich edges / 135 names (222 episode-edge associations are not unique
edges). Six source-name-only schema calls used 13,683 tokens. No observed
allowlisted endpoint warnings; semantic completeness is not certified.

QA used eight successful calls / **55,463 tokens**, complete usage. Full execution
is `completed_within_contract`, no failures/unclassified warnings. Scoped Store,
vectors, source journal and graph remained unchanged; source-only graph authoring
did not read question/gold. Scope-06 graph runs on a different scope concurrently.

Exact empty-key checkpoint replay: zero new attempts, six Reader/judge cache hits,
same semantic answers/grades/context, unchanged provider ledger and original live
receipts. It does not rerun retrieval or independently validate correctness.

## Bindings and checkpoint

- Graph receipt: `19d2a399c83aea9d3d66a283b4b7eb8c156f8076ed5a6af0f83f9a525e4aa914`.
- Schema receipt: `8fbed71a3a7a4e444a027b53a0756147da1f81302ae39f075fdb2276c21d4a30`.
- Live paired receipt: `927cdab7e966c4abb85afa802f8ef3e3e2fa535a75c148c8ef8d11e4bd243fa4`.
- Replay receipt: `fe378a2f86a0c47fc708cbd4bb6a9075a48d124ec6446fc48a0b7b41644d38f4`.

Five of fifty questions scored: provisional task counts full 5/5, raw 4/5; the
sole raw task failure (case 03) remains disputed by its own citation judge.
No new marginal graph gain, reliable population accuracy or unanswerable result
is established. Continue fixed ordinals 06 and 07 without tuning or resampling.
Targeted graph/query/replay tests: 21 pass; Ruff repository check passes. No new
Python/core/config/prompt/model edits in this run; prior full suite baseline is
1,852 passed / 33 skipped / three subtests passed, not rerun for these doc-only
stages. `uv.lock` remains the user's unstaged change.
