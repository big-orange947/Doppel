# Independent clocks: product contract and opened-history diagnostic

Freeze before new paid calls. This is an opened development regression, not a
blind sample, complete LongMemEval score, independent judge validation or AML
result. Existing causal-replay receipts, answers, caches and failures remain.

## General API change

Question-reference time and observation cutoff are independent. An explicit
host `observed_until` binds plan V3 with an operation/time V2 draft. No override
retains V1/V2 wire shapes. The planner receives the question reference but cannot
grant observation access. Current/as-of/interval validity still uses the question
coordinates; Store, graph support, raw and backing channels share the cutoff.
Both clocks are integrity-bound. Scope/subject/authority gates are unchanged.

This does not add version-history reconstruction or use administrative updates
as observation time. Mixed merged provenance and retrospective governance still
require a revision/source-history design for strict historical reconstruction.

## Declared diagnostic policy

`provided-history-v1` binds `observed_until = max(question_reference,
all supplied source-turn timestamps)`, uniformly, without answer/evidence labels.
`strict-reference-v1` keeps the causal default. Results from the two protocols
must not be pooled. No date is patched based on an annotation, case ID or gold.
The source-order second history is already opened and graph-complete. It is a
diagnostic clock contrast, not independent evidence of generalization.

The new consecutive query runner has a V2 identity and binds this policy,
implementation hashes, graph snapshot, schema, Store/vector fingerprints and
unchanged context/model settings before calls. All old receipts remain immutable.

## Frozen second-history preflight

- Path: `data/doppel/public-memory-provided-clock-scope02-preflight-v1.json`
- SHA-256: `7152a4f96a494510edfc5ee1b0ec288a03b803a01514bb6a3e91642e57bfd0d0`
- Plan: `255cd61cb9691c573f415cb8d5d4a50cf738e80b866ffc0bfe58f2127c22e5c4`
- Reference: `2023-06-01T05:09:00Z`; observation horizon: `2023-06-01T17:50:00Z`.
- Provided turns: 431; later than question reference: 70. These are input counts,
  not gold-evidence counts. Cutoff remains finite and source-derived.
- Run dir: `data/doppel/public-memory-provided-clock-scope02-v1`.
- Live output: `data/doppel/public-memory-provided-clock-scope02-live-v1.json`.

Maximum new requests: Planner 2 + Reader 1 + task judge 1 + citation judge 1 = 5.
No retries. Existing BGE embedding, CUDA reranker, complete real graph, source
resolver, 20 whole items / 24000 UTF-8 bytes, Reader V2 and judges stay unchanged.
No re-extraction, graph authoring, Store/vector writes or reserved histories.
On failure preserve checkpoint and spent usage; do not edit the expectation.
After success attempt an empty-key checkpoint/content-cache replay, separately
from genuinely live planner/reranker execution.

Report answer, evidence coverage, citations, unknown/degraded execution warnings,
observations admitted under each declared cutoff, graph contribution and language
drift separately. A correct answer is not proof of graph uplift or future-data
safety. The third opened count question's Reader failure remains a separate
failure even though both relevant original statements now reach context.
