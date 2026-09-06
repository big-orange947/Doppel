# Optional candidate union experiment

`PersonalMemoryQueryConfig(candidate_fusion="union")` enables an experimental
alternative to the default `relation_gate` behavior. It is not enabled by default.
Default configuration fingerprints remain compatible with existing plans; union
has its own fingerprint, so plans must be rebound for the selected configuration.

Union merges independent lexical/semantic candidates with relation candidates,
deduplicating by scope and memory ID. All candidates still undergo the existing
Store, authority, subject, lifecycle, time and score checks. No evidence verifier
is required. Scores, weights and candidate limits remain unchanged. This is
candidate-pool fusion, not a new universal reranker or an exhaustive retrieval API.

Planner-inferred relation hints/types guide discovery and ranking, but do not
remove independent vector candidates in union mode. Host `required_relation_types`
remain hard constraints even if `relation_hints_require_match=False`. An absent
or unavailable relation index cannot satisfy them: union raises rather than
returning unconstrained hits. Hard relation-constrained counts are unsupported.
Soft relation queries retain the configured fallback behavior on index failure.

```python
from doppel_memory import PersonalMemoryQueryConfig

result = await client.query_personal_memory(
    question, scopes, planner=planner,
    config=PersonalMemoryQueryConfig(candidate_fusion="union"),
    semantic_index=vector_index, relation_index=relation_index,
    trace_limit=200,
)
```

The benchmark CLI accepts `--candidate-fusion union` (default `relation_gate`)
and records `candidate_fusion` at report top level. Run identical datasets,
planner drafts, index/model configuration and profiles with each value, writing
separate reports. Existing source planner drafts are rebound; do not use a plan
fingerprint from the other fusion configuration. Metamorphic lexical-only checks
remain lexical-only and do not validate union; report that limitation.

Offline tests demonstrate independent vector recovery, deduplication, scope/
orphan/inactive/time rejection and explicit relation constraint behavior. They
do not establish real Graphiti/pgvector quality improvement. Next validation is
paired live replay: vector baseline, relation gate, and union, tracking recall,
ranking, independent source benefit, legacy exclusions, safety and latency.
Preserve inspected development-set limitations and unavailable graded metrics.
