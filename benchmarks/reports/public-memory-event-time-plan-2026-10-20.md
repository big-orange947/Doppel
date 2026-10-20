# Opened-eight occurrence-time repair: frozen plan

This is a development repair and paired diagnostic, not an independent blind
test, complete LongMemEval score, AML score or default-promotion decision.

## Production change and limits

Add optional typed occurrence coordinates to episode drafts and bound metadata:
start/end, precision, explicit/resolved-relative/unresolved basis, exact source
expression and source ID. The miner verifies the exact quote and supporting
message and supplies its trusted observation clock. Normalization remains an
unverified model interpretation, not a confirmed owner fact. State validity and
occurrence time are separate. Arbitrary draft metadata cannot inject the field.

The query engine uses these coordinates for interval membership; unknown and
partially overlapping intervals stay candidates with uncertainty warnings and
cannot establish an exact count. Scope, observation horizon, actor, authority
and other eligibility checks still apply. Records without the new field retain
their old fallback. Point-in-time/current state validity is not redesigned.

Opt-in Analyzer V11 supplies occurrence coordinates; opt-in Planner V3 separates
reported totals and elapsed duration from counting distinct completed events.
Duration arithmetic stays in the answer layer. Defaults stay unchanged; there
are no question-ID, entity-name or benchmark-category branches.

## Fixed experiment

Reuse the previous frozen paired runner and the same eight opened cases at
ordinals 02,03,05,07,09,12,16,19. Preserve exactly the previously saved raw source
contexts, Reader V2, provisional task judge, alternating arm order, scope and
observation horizon. No protected histories, new retrieval, embedding, graph,
full-history extraction or persistent source writes. Keep all validated claims
and the full raw fallback; candidate interpretations cannot become citation IDs.

New structured arm uses actual V11 analyzer/miner/transient view and V3 planner/
QueryEngine in an ephemeral candidate Store. Rerun the raw arm contemporaneously.
Additionally execute a zero-provider counterfactual using the SAME proposals,
IDs and query plan, removing only event_time metadata. Compare actual accepted/
rejected candidates; this isolates engine membership, not downstream QA quality.
The main paired experiment changes both analyzer and planner and is not a causal
isolation of either prompt, nor a token-budget-matched comparison.

Report raw/structured task grades, changed answers, occurrence coordinate
coverage/precision, quote quarantine counts, actual planner routes and candidate
changes against the metadata-removed counterfactual. Preserve losses, uncertain
normalization, extraction omissions and provisional judge limitations. Global
history counts stay indeterminate regardless of ephemeral Store completeness.

## Boundaries and identities

DeepSeek flash, temperature=0, thinking disabled, json_object; unchanged caps:
analyzer8 x8192, planner8 x2048, Reader16 x2048, judge16 x1024 output tokens;
**48 new calls maximum**, no automatic retries or stage repairs. Frozen request
bindings, durable receipts/ledgers and content-addressed caches remain enforced.
Invalid stage stops and preserves the failure; do not silently drop or replace
cases, widen caps or reuse old answers as the control. Key-free cache-only replay
must have zero new calls and reproduce outputs byte-for-byte.

- Runner: doppel.opened-structured-pair.event-time.v2
- Run directory: data/doppel/structured-event-time-v2
- Frozen preflight: data/doppel/structured-event-time-preflight-frozen-v2.json
- File SHA-256: 639cceccf4670f15f72c8f0ba56990b0b4a92701c1ffe6b623cc288509748b6d
- Plan fingerprint: f83d1b368e99154f6046153f8cf0ecb71c7507a724a8314ab24511c3ede0522f
- Earlier draft preflight is not the frozen identity. Old v1 reports, caches and
  source snapshots are preserved; their original commit remains their replay pin.

Freeze this implementation and protocol in Git before any new paid invocation.

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_memory_structured_pair --event-time --run-dir data/doppel/structured-event-time-v2 --output data/doppel/structured-event-time-live-v2.json --frozen-preflight data/doppel/structured-event-time-preflight-frozen-v2.json --execute
```
