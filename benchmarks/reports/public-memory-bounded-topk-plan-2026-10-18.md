# Up-to-20: remaining-two diagnostic, frozen before new calls

2026-10-18. Preserve both previous failed exact-cardinality runs. Do not reinterpret
their cached outputs, retry their requests or change old labels. This is a new
general **upper-bound** contract, not a topic-specific exception.

Only `gpt4_ec93e27f` (transport) and `gpt4_2f8be40d` (event count) are evaluated.
They are the two remaining cases from the original opened-three plan, selected
before any bounded-selector output. Omit the first case whose source smoke failed;
do not report this as a full three-case score or untouched validation. Baselines
are exact immutable content-only passage results for these same cases (1/2).

One profile `metadata_up_to20_selected_unranked`. Same scoped BM25/vector80 pools,
same source text, speaker/authority/time metadata, lossless1200/160 spans,
round-robin80 fragment pool, skip-to-fit24KB/20 packing, Reader v2 and provisional
DeepSeek task judge. No speaker quotas, scenario rules, gold in ranking requests,
MMR, source writes, graph authoring, reserved/new-case access or default promotion.

`BoundedTopKSelector` implements the existing Reranker protocol: select0..20 unique
input IDs, only selected originals returned, all remainder explicitly unranked.
No fabricated scores, appended tail or lower-bound quota. Prompt retains potentially
useful partial/complementary evidence; it does not make final answerability or
truth judgments. Schema hints are followed by exact ID/subset/maximum validation.
Empty output is permitted, but will be visible as an empty source/context, not a
claim that the correct answer is unavailable. Other malformed outputs fail.

Preflight: `data/doppel/bounded-topk-diagnostic-preflight-v1.json`, zero provider
calls; fingerprint:
`f083ccf0b3c34108e4a757418962c8db20d4e9f48cccf3f6be5e73105ab5477d`.
Authorized source pools80 each; canonical requests105,688 and123,254 bytes. Source
text not truncated. Source/input/implementation hashes are frozen in the plan.

At most **8 new calls**:4 selection,2 Reader,2 judge. Together with this turn's
failed exact-k call, at most9 calls (below the original12-call allowance). Earlier
full-permutation1 call/19,290 tokens is additional historical spend. Exact-k
1 call/19,378 tokens is preserved and bound in the new plan, not erased/refunded.

DeepSeek flash JSON-object/temperature0/thinking disabled; completion caps
selector1024, Reader2048, judge1024. Per-call canonical byte caps500KB selection,
100KB QA/judge; cumulative caps1.5MB selection/300KB each QA and judge. Durable
ledger and exact-output cache in `data/doppel/bounded-topk-diagnostic-20261018-v1`;
new cache only, key environment-only, no automatic retries. Stop on first
runtime/validation failure and preserve spent/unknown usage. Byte/output caps
are not exact billing guarantees. Commit implementation/plan before execution.

Report paired primary grades and actual evidence/answers; do not recalibrate
judges or tune prompts post-result. Examine source→fragment→packing loss separately
from Reader failure. If promising, next validate on a separately frozen untouched
small continuation; two opened cases are not a generalization or release claim.
