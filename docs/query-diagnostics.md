# Personal query diagnostics (provisional)

`PersonalMemoryQueryEngine.query/execute` and
`DoppelClient.query_personal_memory` accept the keyword-only `trace_limit`.
Zero disables collection and returns `result.trace=None`. Values 1..10000 enable
a per-execution bounded trace. Non-integer values, including booleans, and values
outside the range fail before planning or reading. This option is host-owned;
it is not included in model prompts, plan IDs or ranking-config fingerprints.

`PersonalMemoryQueryTrace` and `PersonalMemoryQueryTraceEvent` are provisional root
exports. `PersonalMemoryQueryResult.trace` is an additive optional wire field.
Existing plans and ranking defaults remain unchanged. Consumers with strict result
schemas should allow the new optional field.

## Observed stages

| Stage | What it records |
| --- | --- |
| discovery | Returned Store/semantic/relation counts, reloaded source candidates and source outages |
| store_validation | Missing records, out-of-scope results, non-personal tags, authority/lifecycle eligibility |
| relation_gate | Reported lexical/type/reranker/adjacency match kind; effective relation/reranker score; threshold exclusion and nonrelation candidates excluded by the relation gate |
| structural_gate | Subject, subject ID, memory type, topic, temporal status, validity and interval checks |
| score_gate | Effective lexical/semantic/relation scores and threshold qualification |
| ranking | Selected hits versus matched records excluded by the final result limit |

Trace stages describe the existing algorithm, not additional checks. A `qualified`
event is not a proof that a fact entails the requested relationship. In particular,
lexical matching can independently qualify an edge even when its reranker score is
low. Inferred relation types remain suggestions; only host-required types are exact
constraints.

Coverage is explicitly `engine_boundary`. The trace does **not** observe candidates
discarded inside a Store query, a vector index, or Graphiti before returning to the
engine. Zero relation candidates cannot distinguish no graph edge, an anchor miss,
an index filter, or an internal read bound. It is not an exhaustive inventory of
all memories, nor a replacement for index-specific diagnostics. The `semantic`
source family does not assert a particular backend or per-component fusion source.
No additional Store/index/LLM calls are made to populate a trace.

## Bounds, ordering and privacy

- `events` retains at most `event_limit` events. `events_seen` and `dropped_events`
  expose truncation; counters continue after event storage reaches the limit.
- `counts` keys have shape `stage:source:reason`. Some events summarize a batch via
  `count`; others describe one record at one stage. Counts are not distinct-memory
  counts, and summing stages double-counts records by design.
- Concurrent index work may interleave discovery/validation events. Do not use event
  ordering as a stable ranking, deterministic fingerprint or timing measurement.
- Each execution owns its collector. Concurrent requests do not share trace state.
- Events copy no query text, memory content, relation facts, edge/episode text,
  arbitrary index source names or exception messages. Only fixed engine reason codes,
  numeric scores and identifiers of Store-returned records in authorized scopes are
  emitted. Missing/unbound/foreign candidates do not expose their candidate IDs.
- Scope-authorized IDs are still diagnostic data, including IDs of subsequently
  rejected records. Host applications should not automatically expose these traces
  to an end user, include them in model context, or log them without a retention policy.
- Exceptions that abort the query do not produce a partial result/trace. Source
  failures with an enabled existing fallback are observable in completed results.

## Evaluation

The retrieval ablation runner accepts `--query-trace-limit 200`, placing the optional
trace in each successfully executed case. Failed source drafts remain failures, not
empty successful retrievals. Trace-on/off comparisons must ignore diagnostic fields
and measured latency while comparing hits, scores, counts, warnings and quality gates.
Trace execution cost should not be compared with trace-disabled baseline latency as
though both runs used the same instrumentation.

This release adds visibility only. It does not implement the planned evidence-support
verifier or change the vector/relation qualification policy.
