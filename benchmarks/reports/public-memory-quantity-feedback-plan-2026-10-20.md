# Opened quantity routing: frozen four-call plan

Freeze implementation/protocol before paid execution. This is a routing and
candidate-inclusion diagnostic, not new answer accuracy, independent validation,
full LongMemEval or AML scoring. Do not rerun eager extraction or build a graph.

## Fixed inputs and selection

Replay all8 source-bound candidate views and original query results from the
previous event-time trial using its completed analyzer/planner receipts. Verify
provider identities, exact source request hashes, entire transient views and
original query results against the parent report before any new call. No gold,
old QA answer or grade enters feedback requests. Extraction and original planning
are replayed locally; no external requests for either stage.

Select all and only frozen plans with operation=count: ordinals03,05,12,19.
This selects by operation, not failure/answer correctness. The two temporal
lookup plans and other non-count plans are checked but not billed. The refiner
uses actual CandidateAwarePersonalMemoryQuery with the unchanged engine/store
gates; no case-specific operation or type override.

Parent report: data/doppel/structured-event-time-live-v2.json

SHA-256: 288809840186943057b82e9aa50dd31fb49719676cfb73b619afa396e7e49b6d

## Outcomes, limits and cost

Report baseline/discovery/final hit IDs and content, routing decision, support IDs,
operation changes, unchanged authority/time/subject boundaries, omissions and
actual calls/tokens. The reported-total case should expose whether candidate
feedback can recover assertions excluded by episode filtering; do not claim it
correct unless actual final hits show that. Preserve all other route outcomes,
uncertainty and false classifications. Model support binding is not semantic
verification, and original/unverified claims must not be promoted to facts.

No new Reader/judge calls. No new QA score or replacement of37/50 or prior6/8–7/8.
No new embeddings, graph writes, persistent source writes or reserved histories.
No automatic retries, replacement cases, cap expansion or output repair.

DeepSeek flash/json_object, thinking disabled, temperature0. Four new feedback
calls maximum,2048 output tokens/request,30KB request cap,120KB cumulative
request bound. Durable budget/cache and exact frozen requests; retain any failure.
Separate key-free cache-only replay must produce byte-identical outputs and zero
new calls. Provider token usage is not exact currency billing.

## Frozen identity

- Runner: doppel.opened-quantity-feedback.v1
- Preflight: data/doppel/quantity-feedback-preflight-final-v1.json
- File SHA: 2e5e0e5d0db0505a18d4a9b96e0b802239fe682476a4c8fd205df34c8173ba6a
- Plan: ec718e9b3890a0c47ec361da21909db54a39713068f129f9f552a9d16b0bed89
- Run directory: data/doppel/quantity-feedback-v1
- Earlier preflight drafts are not the frozen input.

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_memory_quantity_feedback --run-dir data/doppel/quantity-feedback-v1 --output data/doppel/quantity-feedback-live-v1.json --frozen-preflight data/doppel/quantity-feedback-preflight-final-v1.json --execute
```
