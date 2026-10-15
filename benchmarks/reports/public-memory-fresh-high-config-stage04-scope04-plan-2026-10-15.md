# Frozen source continuation and fourth-scope graph

The explicit one-call recovery completed chunk 380 with the **identical request
hash**, one successful call and 6,383 reported tokens. All old attempts and the
failed call remain unchanged. Recovery receipt SHA-256:
`cd66c62035656369cb793859b14b23b424ee02bf7cb7233dc3cec861e102b42c`.
Observed balance was 56.20 CNY before and after; this is not exclusive billing.
The original failed call still lacks usage; cumulative billing is not exact.

## Source continuation, frozen before calls

- Same first ten histories and source-only projection; no question/gold access.
- Start at 380 completed chunks. **119** additional chunks/provider attempts,
  ending at 499. Never allocate a new 499-call allowance or auto-retry failures.
- Stage fingerprint:
  `324f69c70e02a111c044a3690b9ed9d836d2a7c76f52cd46b175d22a036b5f55`.
- Preflight SHA-256:
  `9d6af4cb1a5c7f5e583afa5414d9b1f1c2c9c8e2315785a01e372301178a9f10`.
- Adapter stays byte-identical to the recovery plan. Resume requires its exact
  verified post-checkpoint and preserved failed ledger row. One recovery is the
  only authorized attempt-cap addendum; the failed original attempt is not erased.
- Store/vector writes are confined to later source scopes; closed scopes 01–07
  revalidate rather than re-extract. No source-stage graph/QA calls.

## Fourth fixed graph scope, frozen before calls

Continue `7e00a6cb` (ordinal 04), without opening its query or gold. Its source
history is already complete: 63 chunks / 564 original messages, 162 eligible
confirmed personal memories and 726 current vector entries. Project **all 162**
eligible records in existing creation-time/memory-ID order, no selected evidence
subset. Source receipt is the successful recovery receipt above.

- Preflight SHA-256:
  `ea5b29e49374f0942102f195e097fe33b1324e81c2f048a8bd408372d69bf28f`.
- Scoped source journal SHA-256:
  `0151ddd022ce5ef03c20d46f5885b84d34154e384d963acdedfcf4096706a0a6`.
- Scoped vector metadata SHA-256:
  `a87d92dcd58e321f6d752ca17499478e0ce6cf1a46bb705f84929bec091dd83b`.
- Same production graph adapter/writer, 1,500-attempt ceiling, 500,000 canonical
  bytes/call and 32,000,000 total bytes. DeepSeek flash/json_object/temp 0/thinking
  disabled/8,192 output cap; same local 512-dimensional BGE. No automatic retry,
  graph-slot repairs, core/prompt/model changes or silent degraded retrieval.
- Read-only selected Store/vector; verify unchanged scoped journal and other
  cohort graph scopes. Source continuation can add later scopes concurrently;
  it does not write Neo4j or change this closed scope.
- Completion means selected-scope projection, not semantic extraction completeness
  or coverage of all fifty histories. Preserve endpoint warnings and failures.
- Freeze actual schema-name inventory/budget after graph completion, then freeze
  paired QA plans. Fourth question order stays raw first/full second, at most
  eight QA attempts. No after-score retuning or new live calibration controls.

These are operational stages of the existing prospective evaluation, not new
retrieval algorithms. Three questions are scored so far; no new score is claimed
here, and no official/independent/AML/publication acceptance is granted.
