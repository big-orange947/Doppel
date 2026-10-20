# Candidate-aware quantity routing (experimental)

This is a module-only opt-in extension, not a default query policy or an answer
generator. It addresses a query-only planner's blind spot: a numerical question
may be answered by a reported total rather than by counting individual episodes.

```python
from doppel_memory.query_feedback import CandidateAwarePersonalMemoryQuery

# plan is an already host-bound V2/V3 plan from engine.plan(...).
audit = await CandidateAwarePersonalMemoryQuery(engine, model).execute(plan)
result = audit.result
```

For count plans only, execute the original query, then discover candidates with
operation=lookup and no planner-derived memory_type restriction. All scope,
subject, authority/lifecycle, observation horizon, temporal coordinates/status,
topic, entity, relation and relevance gates remain unchanged. The model receives
at most20 whole eligible hits/18KB, with actor/authority/state and time metadata.
Whole-item omissions are counted; this pool is never represented as complete
history. If no candidates fit, skip the model call.

One structured feedback call may choose a supported reported-quantity or temporal-
anchor route, or preserve enumeration/uncertainty. It cannot return a full plan,
rewrite dates, widen scopes, change subject or generate an answer. Support IDs
must belong to the supplied pool; invalid output fails, without automatic retry.
Low confidence preserves the original operation. Applied lookup is executed
again against the Store, including eligibility checks, so a revoked/deleted
candidate snapshot is not returned as if still current.

The audit retains original, discovery and final results, decision, supplied IDs
and omission counts. Reported quantities and conflicting/window-mismatched
assertions remain evidence for the host/Reader, not a certified total or a
confirmed fact. No model verdict overwrites source records or promotes a plan to
a completed event. Exact count semantics of ordinary engine queries are unchanged.

Tradeoffs: up to three Store query executions and one extra model request per
opted-in count query; ordinary lookup plans perform only their normal execution.
The host owns authorization, scheduling, model budget and durable caching. This
extension relaxes planner-derived type restrictions, so do not use it when a host
intends those types to be a separate mandatory authorization boundary. Subject and
scope permissions are never relaxed. Top-k discovery may miss a relevant total;
an empty/uncertain pool is not evidence that no such assertion exists.

This does not repair extraction entailment or date normalization. In particular,
"decided to do" is not "did", and a week range is not day precision. The previous
opened-eight diagnosis still records those defects. A source-bound candidate
interpretation is not independently verified truth.

The [first frozen four-plan diagnostic](../benchmarks/reports/public-memory-quantity-feedback-result-2026-10-20.md)
recovers two reported-total assertions previously blocked by episode filtering,
while preserving three enumeration plans/hits. Four feedback calls/6761 tokens,
no new QA score. This is an opened development result, not a promotion gate or
general quality claim.
