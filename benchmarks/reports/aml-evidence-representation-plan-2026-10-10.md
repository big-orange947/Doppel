# Evidence representation paired diagnostic: frozen before paid execution

Starting implementation: `2f51e93`. Nine **already opened synthetic development
controls**, both fresh arms, maximum **18 Reader attempts**, zero Judge attempts.
No LongMemEval cases, reserved histories, retrieval calls or graph/miner writes.
This is not AML's answer model, an independent blind validation or a competition
score. The previously failed grounded Reader V2 candidate is not promoted.

## Exact contrast

`existing_structured` retains the complete existing Reader input projection,
including role, authority, original text, observation time and null temporal
fields. It is not an attribution-free straw baseline.

`attributed_content` uses the actual `AttributedEvidenceExporter.historical`
output, with stable outer citation IDs and the compact JSON document in content.
Fixture source actor/authority is explicitly bound in a temporary InMemory Store.
Sources, observation clocks, item identities, selection and order are unchanged.
Transport role alone is not used as a production identity policy.

Both receive the same question/reference clock, output schema and
`grounded_advice_v1` instructions plus an identical generic representation decoder.
The decoder explains the two input shapes but does not contain control topics,
expected answers, rubrics, old results or query-specific speaker fixes. Both arms
are generated fresh, not compared to old cached answers from a different prompt.

The contrast changes JSON shape, explicit speaker labels, source IDs and input
length. It therefore tests the **whole representation**, not the isolated causal
effect of actor tags. The common decoder differs from the previous control run;
old and new control scores are not a clean A/B. There is one dedicated speaker
inversion control, too few to estimate a general attribution-error rate.

## Execution discipline

- Preregistered sequential alternating arm order across controls.
- Requested provider alias `deepseek-v4-flash`, json_object, thinking disabled,
  temperature zero, 1,024 max output tokens, 120-second timeout. Record returned
  model and finish reason separately; alias is not a pinned model snapshot.
- Shared durable 18-attempt ledger; failure/interruption counts. Fail-stop,
  no automatic repair or retry. Input bytes bounded at 100,000 per call.
- Observe balance; stop when empty or observed decrease reaches CNY 1. This is
  post-spend observation, **not** an exact invoice/token/CNY hard cap.
- Separate immutable plan, receipts, output cache and provider metadata receipts.
  No credential/header/raw HTTP response persistence. Environment key only.
- New report path per invocation. A separate key-removed child-process cache-only
  replay must reproduce plan and rows with zero new attempts/cache misses.

Output-schema/citation/derivation checks are structural, not semantic evidence.
Manual review must cover all 18 rows with exact answer/source quote anchors,
unchanged control rubrics and separate speaker attribution, language, plan-to-fact
and abstention-consistency fields. Report review as non-independent; quote
validation proves provenance, not the correctness of semantic decisions.
No automatic yes/no QA Judge or benchmark answer text enters this experiment.

## Entry points and frozen artifacts

```powershell
.\.venv\Scripts\python.exe -m benchmarks.aml_evidence_representation --run-dir data/doppel/aml-evidence-representation-v1 --output data/doppel/aml-evidence-representation-preflight-v1.json

.\.venv\Scripts\python.exe -m benchmarks.aml_evidence_representation --live --frozen-preflight data/doppel/aml-evidence-representation-preflight-v1.json --run-dir data/doppel/aml-evidence-representation-v1 --output data/doppel/aml-evidence-representation-live-v1.json
```

Preflight file SHA-256:
`24380ed7889dee37ceae80a505e9794a7521ee96fbc8ee07122eb6b8021d4f7d`.
The plan binds exact controls, all 18 request hashes, configuration, exporter and
runner/dependency source hashes, and the core runtime source hash. Preflight
produces no provider or semantic result. Model/cache/rubric and failure safeguards
are covered by **19 new offline tests**; with exporter tests, **52 passed**.
