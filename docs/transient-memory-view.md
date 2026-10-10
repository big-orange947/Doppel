# Optional read-only transient memory view

`TransientMemoryViewBuilder` projects a finite exact-scope source window and its
candidate analysis proposals into a temporal interpretation. It performs **no
model calls, Store writes, retrieval, authorization, state transitions or graph
updates**. It reuses the existing pure `DeterministicMemoryConsolidator` to attach
advisory merge/correction/conflict decisions. No decision is applied.

This is an additive explicit utility, not a new default ingestion or recall policy.
Persistent analysis/governance remains unchanged. A host can use it for bounded
query-time work, inspect an analysis batch, or present uncommitted proposals.
It is not a complete timeline inference engine or an automatic conflict resolver.

## Inputs and trust boundary

The host supplies an already authorized `PersonalMemoryAnalysisRequest` plus its
`MemoryProposal` outputs, for example from `PersonalMemoryMiner`. Source messages
and actor/sender bindings must come from trusted ingestion/Store revalidation.
`ChatMessage` has no scope credential: supplying a scope string does not prove
permission to see those messages. This builder does not replace that host boundary.

Only exact-scope **candidate** proposals with complete reference-analysis provenance
are accepted. Cross-scope promotion, manual summaries and incomplete evidence
require other explicit policies; they are rejected, not guessed. Builder checks
unique evidence IDs, original message/event/sender/actor/observation bindings,
subject identity, authority and the proposal's observation clock. A foreign,
confirmed, inconsistent or unresolved-source proposal fails the entire view.
Default bounds are 500 messages/100 claims; exceeding a bound fails, not truncates.
The source text projection is normalized `ChatMessage.text`. Original structured
parts, attachments and raw transport payloads remain host responsibilities; this
utility is not a multimedia resolver or a lossless transport exporter.

```python
from doppel_memory import (
    PersonalMemoryAnalysisRequest,
    TransientMemoryViewBuilder,
)

# scope and messages are authorized, source-revalidated host inputs.
# proposals are candidate outputs of the existing analyzer/miner pipeline.
request = PersonalMemoryAnalysisRequest(scope=scope, messages=messages)
view = await TransientMemoryViewBuilder().build(
    request,
    proposals,
    reference_time=question_time,
)
payload = view.model_dump(mode="json")
```

`TransientViewError` reports binding/clock/limit failures. Invalid Pydantic inputs
may separately raise validation errors. The operation does not persist a view or
alter its input proposals/messages.

## Two clocks, no invented effective intervals

Each claim carries first/last source observation, original source IDs/text and
explicit `valid_from`/`valid_to` when present. Missing effective dates stay missing:
the observation date is **never substituted**. The query-time assessment is:

| Assessment | Meaning |
| --- | --- |
| `unknown` | No explicit effective bound is supplied; not proof of validity or invalidity |
| `within_explicit_bounds` | The reference time satisfies the supplied bounds, inclusive; not verification that the claim is true |
| `outside_explicit_bounds` | The reference time falls outside a supplied bound; the claim is still included for historical context |

An elapsed plan remains a plan. Two claims marked `current` stay available even
when one was observed later. No automatic newest-wins, plan completion or expiry.

By default `observed_until` equals the question/reference time. If any source
observation follows that horizon, the builder raises instead of silently dropping
sources. For a retrospective supplied-history diagnostic, the host may explicitly
provide a later observation horizon; affected claims are marked
`observed_after_reference=True`. This is not causal/as-of replay and must not be
reported as prediction from evidence available at the earlier reference time.

## Advisory governance, not a retrieval veto

The existing conservative consolidator can flag different current values in the
same compatible slot as a potential conflict when it sees no explicit revision
marker. It can also suggest an explicit correction or duplicate merge. Those
decisions operate on analyzer interpretations and are **not independently
verified semantic conclusions about original text**. Compatible enrichments and
genuine changes may require a Reader or stronger interpretation step.

`consolidation_applied=False` and `semantic_evidence_verified=False` make this
boundary visible. All claims remain candidates, including suggested noncanonical
sources. `advisory_consolidation` IDs refer to stable transient claim IDs, not
persisted memories; retain original evidence IDs for citations.

Do not turn an advisory conflict into an automatic refusal, suppress raw evidence,
or assume the newest canonical suggestion authorizes a Store change. Actual
persistent governance still goes through its existing policies and audited runner.

The initial cache-derived diagnosis and its paid Reader contrast are recorded in
[the experiment plan](../benchmarks/reports/public-memory-transient-view-plan-2026-10-10.md).
Two opened cases cannot establish a general accuracy, recall or AML benefit.
The [initial result](../benchmarks/reports/public-memory-transient-view-result-2026-10-10.md)
finds no additional task success (both arms answer both cases), but preserves
retrospective-time caveats and original evidence despite advisory conflict. The
index adds 19.16% Reader input tokens on these cases; it is not a promoted default.
