# Evidence-bundle judgment V1 — opened delta diagnostic plan

Date: 2026-09-28

Status: post-hoc case selection frozen before provider judgment

The first 12-case development replay produced perfect judgments for both V7 and V8,
but all 12 top-10 bundles had identical membership. It validated the evaluator and
model boundary, not the policy difference. This follow-up deliberately selects opened
cases where the frozen retrieval reports differ. It is a diagnostic and is never
eligible as unseen or publication evidence.

The exact selection is bound by
[`evidence-bundle-diagnostic-selection-v1.json`](../datasets/evidence-bundle-diagnostic-selection-v1.json)
to heterogeneous V4 fingerprint
`0b0d0c8ab8aaf35350e465325540acc3b8c81f00496ed0d02901bc9f10e6a771`
and retrieval report hash
`5f44ac144ca1d266945dac5df7a27ba6ad1c29d671618198f698198ac92acce9`.
Its own pre-result SHA-256 is
`9387461e37df5ec205de0eb1fbd4c4d8488a419df5a84a7ba0be114031cbb75a`.

## Frozen strata

1. Five two-hop cases where V7 lacks one required memory at rank 10 and V8 contains
   the complete support set.
2. Three one-hop cases where V8 moves the first required memory from rank 2 to rank 3.
3. Eight matched no-answer buyer questions containing related relation context but no
   direct purchase evidence.

The 16 cases cover eight owner scopes and 32 logical profile judgments. The same
opaque-ID information boundary, scoring, cache, call budget, and V7/V8 comparison
rules from the V1 preregistration remain unchanged. No prompt, threshold, context
limit, gold label, or retrieval output may change after the result is opened.

## Interpretation

- A V8 gain on the five recovered-path cases shows that additional complete evidence
  can improve downstream evidence selection.
- A V8 loss on the three one-hop shifts measures the cost of moving a correct item by
  one rank while keeping it inside the same ten-item bundle.
- False support on the eight controls shows that extra graph context can mislead the
  downstream model even when retrieval safety itself remains intact.
- Aggregate success alone is insufficient; all three strata must be reported.

Because selection used already-opened V7/V8 failures, a pass may support an engineering
choice but cannot establish generalization. A new owner-disjoint blind corpus remains
mandatory before publication-quality claims.

```powershell
.venv\Scripts\python.exe -m benchmarks.evidence_bundle_judgment `
  --live `
  --selection-file benchmarks/datasets/evidence-bundle-diagnostic-selection-v1.json `
  --max-calls 32 `
  --output data/doppel/evidence-bundle-judgment-v1-delta-diagnostic-first-live.json
```
