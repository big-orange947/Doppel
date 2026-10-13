# Prospective 50-case evaluation: first source history materialized

Frozen selection/protocol and source-stage adapter committed in `9eda4ea` before
paid execution. [Plan](public-memory-fresh-high-config-50-plan-2026-10-13.md).
No core/prompt/model/selection change after seeing this new history's outputs.
Original task question/reference/annotations are withheld from this source stage.

## Actual progress, not an answer score

- New cohort: 50 evaluation cases, ten reserved, 80 prior/opened/reserved groups
  excluded. Full source plan: 25,002 messages / 2,479 chunks.
- First frozen history `15745da0`: **49/49 chunks complete, 474 raw messages**.
- Overall ingestion remains **partial**, 49/2,479 chunks and 1/50 histories.
  That is the declared invocation boundary, not a failure or a completed cohort.
- Graph authoring: zero calls. Reader/task/citation scoring: zero calls.
  New answer accuracy, recall and full-500/AML score are **not available**.

## Source/Store observations

The new isolated schema `public_memory_3055ab766570` contains:

| Record class | Count |
| --- | ---: |
| Original messages | 474 |
| Structured personal memories | 216 |
| Conflict/governance records | 6 |
| Total | 696 |

All 696 records are confirmed under the frozen host acceptance policy; this is
not independent semantic verification. Source audit completes **747 checks / zero
failures**. Only the first new scope is materialized; the other 49 selected scopes
remain empty. Reserved scopes are not processed. Old schemas/journals/graphs are
not reset or relabeled.

The model returns 227 schema-valid drafts, zero invalid/low-confidence/duplicate
drafts. **Eleven evidence-rejected drafts are quarantined**:

- Mixed source actors: 9.
- Unknown evidence ID: 1.
- Subject/source mismatch: 1.

Raw sources remain stored; 216 accepted proposals survive. These are extraction
and binding observations, not eleven independently adjudicated semantic errors.
Some mixed-source proposals may include otherwise useful claims: do not assume
quarantine proves complete information preservation or excuse a later answer miss.
No rule/prompt is adjusted to repair these observations during this cohort.

A separate read-only vector audit reloads all authoritative new-scope records and
checks exact metadata/version/fingerprint inventory: **696/696 entries current**,
profile `dplv_3af0a004c18c2f78`, embedding `fastembed:BAAI/bge-small-zh-v1.5`,
version 0.8.0 / 512 dimensions. Vector metadata SHA
`3f4c425e452f5ca3976d19b9be74ceb5db6b705c2cc072aab4997808339e5a91`.
This verifies index inventory, not retrieval performance or graph readiness.

## Calls, usage and replay

Exactly **49 new calls**, 49 succeeded, zero failed/interrupted/retried attempts.
All calls have complete usage:

| Usage | Tokens |
| --- | ---: |
| Input | 218,747 |
| Output | 28,300 |
| Total | 247,047 |
| Provider-cached input, included in input | 43,904 |
| Cache-miss input, included in input | 174,843 |

Requested DeepSeek alias is not snapshot-pinned. No actual returned-model snapshot
claim is made by the existing ingestion runner. Observed balance CNY 4.65→4.44,
net decrease 0.21, is not a proven exclusive invoice or settled per-stage price.
Call/byte ceilings are enforced; exact monetary/token hard caps are not claimed.

Separate PowerShell replay removes the key and uses cache-only/zero-new-chunk mode.
**49 completed journal chunks replay/revalidate, zero new model calls**, stage,
chunk audit and Store/provenance audit exactly match. Provider cache hits are zero:
completed host operations validate without invoking generation. This is not 49 new
provider-cache responses and not a refund of the original 49 calls. Historical
calls remain in the stage continuation ledger.

## Artifacts and validation

- Live SHA `a4d28bbc56650aa620e29ff2c7d4b5cb567a5e4f80c8a21c87f4f602083c143a`.
- Key-removed replay SHA
  `ba3cf3d287df888bd98a7427d9311955c3eaf7dc46cccc502aeaa9fda092c634`.
- Local names: `data/doppel/longmemeval-fresh-high-config-50-ingestion-stage01-live-v1.json`,
  `...-replay-no-key-v1.json`, `...-source-vector-audit-v1.json`.
- Durable source/cache/usage directory:
  `data/doppel/public-memory-fresh-high-config-50-v1/ingestion/`.

Fifteen new offline tests pass. Final full suite: **1812 passed, 33 skipped,
3 subtests passed**, 178.63s. Ruff full repository and both new adapters' Pyright
checks pass. The earlier preparation-only collection was 1806 tests; the final
1812 run includes the six stage tests. Existing deprecation warning remains.
`uv.lock` is unchanged/unstaged. No API key is stored in reports/configuration.

## Continue the assessment, not another control loop

Advance remaining source histories with separately bound continuation budgets;
preserve this prefix and its failure accounting. Prepare graph inventories/budgets
for complete selected histories and then the two frozen query profiles, aiming to
report the first ten-question block promptly. Scope-level completion must be proved
without mislabeling the whole 50-history corpus complete. Actual graph/QA adapters
bind their sources and dependency/data receipts before paid calls. Do not return
to Reader/control prompt tuning or silently repair a new answer during this cohort.
