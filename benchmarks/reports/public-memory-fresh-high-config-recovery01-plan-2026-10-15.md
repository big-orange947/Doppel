# Frozen one-attempt source recovery

User explicitly authorized one separately accounted, unchanged-configuration
recovery after the transport failure. No question-dependent tuning or new sample.
This is an operational adapter only; all frozen core/config/prompt files stay
unchanged, including the original ingestion and continuation adapters.

- Failed stage receipt SHA-256:
  `a4d2ff95f6286f987caf26eb1af993b7594d6b1db8460fb61e0b3e694ed7e750`.
- Original continuation: 231 attempts, 230 successes, one transport failure.
  Completed source prefix 379, pending chunk 380 (12 raw messages already stored).
- Failed call 380, request SHA-256:
  `3fac1ceb923d8bf4aa07374bd5126a2f4eea8271356ed31a962046f27f670f67`.
- Frozen recovery plan fingerprint:
  `be9de12cf63bcf7cf9eef11db5c18bf7ad50bb05df5164798024339e98f990d9`.
- Preflight artifact SHA-256:
  `2c0d9ac136bb0c102a9019dbf3525201779375376a70493ad88bab330750295c`.
- New adapter SHA-256:
  `ea7f93540c44552596f6b80fd276465efba2207a5b7bb9867cc3fe79ce131dd4`.
- Same source-only plan, namespace, actors, V8 analyzer/V5 consolidation, provider,
  prompts, output caps, quarantine rules and local BGE vectors. No graph or QA.
- Exactly one new chunk and one new provider attempt. Technical ledger mechanism
  is a new `continuation-v1` identity to reuse per-scope completed-source
  revalidation; this document and receipt explicitly classify it as recovery.
- Preserve all prior ledger rows/failure metadata/cache, raw pending messages and
  the failed receipt. Verify successful recovery request hash equals the failed
  request hash. If it fails, stop; no second retry or automatic recovery loop.
- Known historical source tokens are 1,828,285; one call has missing usage, so
  cumulative exact token/billing accounting remains incomplete even if recovery
  succeeds. Unknown usage is not zero. No refund of the failed attempt.
- Success may authorize a **separately frozen** 119-chunk continuation to the
  original first-ten target 499. Do not allocate those calls in this recovery.
  Completing the original 350-chunk block would then consume 351 attempts,
  including the one additional recovery explicitly authorized by the user.

Pre-live offline checks: 25 tests pass across recovery/continuation/source
adapters; Ruff passes on the two new Python files. This adds no quality scores,
official LongMemEval/AML result, independent blind validation or publication gate.
