# Transient view: frozen cache-derived interpretation and four-call contrast

Starting HEAD `4741162`. Add the optional read-only `TransientMemoryViewBuilder`,
with no new default policies. Reuse the existing deterministic consolidator only
for unapplied advisory decisions. Preserve original sources, all candidate claims,
unknown effective dates and separate observation/reference clocks. No newest-wins.

## Cache-derived input, zero new extraction

Parent `data/doppel/lazy-proposal-live-v1.json` SHA-256
`76220e823d707cb9a96f72c9a5eb71910ecc130cb57ffd29d23496e227b4167b`.
Two opened cases, same saved S raw contexts and 16 prior proposals. Read original
completed analysis receipts, reconstruct the exact analyzer requests and pass the
unchanged cached outputs through the real reference analyzer/miner gates. Verify
projected proposals/checkpoints match the parent. No provider is constructed for
this replay and no parent cache/receipt is rewritten. No new graph/retrieval/Store.

The derived view has no effective interval for all 16 claims. Both old and new
project claims remain `current` candidates. Existing governance emits one
**advisory conflict**, with no canonical source, for `project.current-model`;
this is not a semantically verified contradiction or a completed update timeline.
No claim is removed and the Reader must retain ordinary access to original text.

## Fresh paired Reader contrast

- `plain_proposals`: all old raw evidence plus unchanged old proposal projection.
- `temporal_view`: same raw/proposals plus compact observation/validity/governance
  index. `proposal_index` links claims back to the common proposal list; the view
  is not an additional source. Cite original raw memory IDs, not transient IDs.

Same instructions/schema/config in both arms, including the same generic view
decoder. Both arms are fresh; do not compare to old answers as a clean regression,
since this common decoder changes from the preceding experiment. The whole
representation and added input length are confounded, not isolated causal effects.
No gold, question category, profile, old answer or rubric enters either request.

Question dates and supplied-history observation horizons stay unchanged. The
temporal case has ten same-day observations after the question clock; this remains
**provided-history evaluation, not causal/as-of replay**. Reserved cases remain
unopened; no outcome-based selection, corpus expansion or parameter tuning.

Four Reader attempts maximum, zero new analyzer and zero Judge. Requested alias
`deepseek-v4-flash`; actual returned model is recorded separately. json_object,
thinking disabled, temperature zero, 1,024 max output tokens. Alternate arm order.
Source/proposal/request fingerprints, new run directory, immutable receipts and
durable attempt budget. Fail-stop, no retry/repair; preserve failed/interrupted
receipts. Stop on failed/empty balance observation or observed CNY 1 decrease;
this is not an exact invoice cap. Every request below frozen 100KB byte limit.

| Case | Plain request bytes | Temporal-view bytes |
| --- | ---: | ---: |
| `gpt4_d9af6064` | 31,326 | 34,897 |
| `3ba21379` | 33,017 | 36,846 |

Before interpreting outcomes, do a separate key-removed cache-only replay with
exact rows/requests/views and zero new calls. Manual semantic review is explicitly
non-independent and quote-anchored; support-date ambiguity, refusal regression,
language drift and any misleading conflict interpretation must remain visible.
No default promotion, official score or recall-gain claim from these two cases.

## Frozen artifacts and offline verification

Preflight file: `data/doppel/transient-view-preflight-frozen-v1.json`.
SHA-256: `03e8efc10a3384b52206a5645706537a962a88560ca1e20b8be7352a8b639dc3`.
Plan fingerprint: `19e782fb619ea4cbf18fb31f13fe980c33eeda2d777de7a6a53d73f29d93356f`.
Runner: `doppel.public-memory-transient-view-diagnostic.v1`.
Fresh run directory: `data/doppel/transient-view-diagnostic-v1`.
Freeze and commit before paid execution.

New tests: 26 component tests and five cache-derived harness tests, **31 passed**.
Related consolidator/lazy tests previously pass (82 tests before harness additions).
Repository Ruff passes; new component/harness Pyright reports zero errors.
Core tests cover temporal boundaries, unbounded unknowns, explicit horizons,
scope/provenance/authority/subject failures, source preservation, unapplied
correction/conflict, plan noncompletion, stable IDs and no input mutation.
