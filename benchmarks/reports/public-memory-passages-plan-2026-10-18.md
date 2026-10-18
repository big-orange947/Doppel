# Frozen opt-in passage implementation and bounded opened-case diagnostic

Implement generic query-independent lossless text spans in the package and a
repository reference composition over attributed raw retrieval. No default API,
Store schema, source content, authority, graph or existing model changes. Defaults:
1200 Unicode code points /160 overlap, source limit20, round-robin max80 passage
candidates, return20. Revalidate scope/source/state both before and after optional
neural ordering; retain original offsets/hash and resolve the original on demand.

Forty-two new splitter/guarded-passage/diagnostic-budget tests pass. The long-tail
control uses a deliberately synthetic stub, not a claimed real-model improvement.
The test fixture initially tried to overwrite an idempotent raw write; it was
corrected to create a separate source, without changing production write semantics.
Ruff passes. This implementation is opt-in, not a replacement for Agent context
management. The core splitter ships in the wheel; the AML reference is repo-only.

## Context preparation (zero paid LLM)

Fixed opened cases `e9327a54`, `gpt4_ec93e27f`, `gpt4_2f8be40d`, selected because
they expose the preceding candidate/ordering/budget failures. This is diagnostic,
not fresh independent accuracy. Reuse each saved hybrid-reranked top20 source
window, not a new lexical/vector search. Whole-message baseline is exactly
reproduced including its serialized hash. Passage candidates are source-bound and
reranked with the same local CUDA BGE CrossEncoder (8192 cap/batch1), with at most80
additional scored passage pairs per question. This is additional local model work,
not a cost-free reranking ablation. Both arms use the same24KB whole-item fit budget.
No gold/labels enter splitting, passage ranking or packing. Do not score a fragment
as answer support merely because it belongs to an annotated source turn.

Use read-only existing schema and verify inventory hashes before/after. Save six
contexts and exact provenance. No source/index writes, graph or paid provider.
No reconfiguration/retry on an observed failure; keep receipts. No idle-GPU claim.

Context preflight SHA-256:
`88c2026f6f50583d24d507df8f83a419c331ff4e90f59b244c3f0a688c8c5a2a`.
Plan fingerprint:
`2e9fac905ae39d09e87c971773af7bc086647bdf9f6f38def444596e98fd262a`.

## Subsequent bounded QA (freeze context binding before paid calls)

After contexts complete, freeze their exact report hash in a distinct QA plan.
Six Reader calls maximum and six task-judge calls maximum, no automatic retries;
existing content-addressed caches and durable budget ledgers. DeepSeek flash,
json_object/thinking disabled/temperature0, Reader2048 output cap, task judge1024.
Existing Reader instructions/schema unchanged. Both arms include full available
source/excerpt metadata in the data payload; no profile or gold in Reader input.
Task judge sees only question/reference/answer and uses the existing task criterion.
Stop on a failed stage, preserve partial rows and unknown usage rather than zero.

Report actual answers/citations and inspect whether supplied spans suffice. Legal
IDs do not establish support; DeepSeek task grades are provisional and are not an
independent entailment audit. Do not repair the judge or tune on these three cases.
Do not present this as LongMemEval500, blind validation, AML or release acceptance.

## Contexts complete; QA binding frozen before paid execution

Contexts completed at implementation commit6cd3c30, with28/44/62 candidate spans,
no candidate truncation/budget exhaustion. Whole-message rows reproduce exactly.
Output SHA-256:
`1a868e90f303e76a3555563bde610f10abe67b4a7a53cd1b415180ad9e223b7d`.
Do not turn the increased item count into a quality score.

After context completion, a fail-closed raw-item `None` guard/type narrowing was
added to the diagnostic wrapper (no splitting/ranking/packing change). Pyright
reports zero errors on the new implementation/diagnostic files. Original context
execution bytes remain preserved at6cd3c30; there is no context rerun.

QA preflight SHA-256:
`ebfadd661b3c0169959e7d36ae71cbe549ed11c9d4eb07d54b311b2f06da43cc`.
QA plan fingerprint:
`c3ec94880ef72f63180049b5445b9dbd5e44bdb463fad80a8181b56f3ec5478a`.
The six frozen contexts use23997/23401/23607 bytes for passage arms and
22475/23549/23631 bytes for whole-message arms, paired in the listed case order.
No byte-budget enlargement or Reader-instruction change. Execution remains capped
at6 Reader plus6 task-judge calls, preserving failures and stopping at the first.
