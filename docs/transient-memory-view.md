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

## Optional non-destructive event grouping

`group_transient_events(view)` returns `TransientEventGroup` objects for episode
claims in an already authorized, builder-produced view. It makes no model calls,
retrieval, Store writes or lifecycle decisions. The original view stays unchanged;
non-episode claims remain there. Each group retains complete per-detail claim
objects, including their separate evidence, observation/effective times and flags.
No synthesized summary or canonical sentence replaces those details.

```python
from doppel_memory import group_transient_events

groups = group_transient_events(view)
for group in groups:
    for detail in group.claims:
        print(detail.content, [e.evidence_id for e in detail.evidence])
```

Grouping partitions by exact view scope, actor, authority, subject and subject ID.
A shared non-empty declared event key groups details, following existing lowercased
event-key conventions; it does **not** verify that the key correctly identifies one
occurrence. Unkeyed claims stay separate, even if their text is similar. The utility
does not choose names, resolve aliases, infer missing identity or assert an exact
real-world event count. `semantic_identity_verified=False` and
`consolidation_applied=False` make this explicit. Group IDs are stable within that
namespace; input claim order does not change the result.

`temporal_metadata_consistent` reports only equality of supplied temporal statuses,
revision markers and effective bounds. Missing bounds may agree without being known.
Disagreement stays visible; no newest-wins or interval union. The default limit is
100 input claims; exceeding it, duplicate claim IDs or invalid limits fail instead
of truncating. Manually constructing a valid view does not authorize its content:
host authorization/source revalidation still precedes this utility.

This is an additive explicit projection, not new default Reader input or a repair of
the failed analyzer-enrichment controls. Their frozen 7/8 results stay unchanged.
