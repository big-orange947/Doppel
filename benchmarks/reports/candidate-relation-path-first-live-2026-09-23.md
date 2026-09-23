# Candidate relation-path ablation: first live Neo4j run

Date: 2026-09-23

Status: development result; all pre-registered hard gates passed

This is the first live run of the [pre-registered v2 experiment](candidate-relation-path-preregistered-2026-09-23.md).
It used the implementation at `85ae104390673acb7200310ad18fb0abf684eda3`, a
documentation-only descendant of the locked implementation `36fc84459a8592ec3c4529ecff90742273226eb4`.
The dataset and gates were not changed after opening the result.

## Reproducibility

- Dataset: `benchmarks/datasets/candidate-relation-path-ablation-zh-v2.json`
- Suite version: `2.0.0-draft.1`; `frozen=false`; `publication_ready=false`
- Canonical dataset fingerprint:
  `dea12fa561160f72cb2d8fcc4b4e467ae2e6556096724125dbd943a5036b094a`
- Local result: `data/doppel/candidate-relation-path-ablation-first-live.json`
- Result file SHA-256:
  `1cdf8111a32b925afe134e2b1d94c8b16e5a736fa66361cb40867bd15b074276`
- Docker Engine 29.4.0; existing `memo-echo-neo4j` container healthy when run.
- CLI exit code: 0; `gate.ok=true`; `gate.failures=[]`.
- 36 queries, nine exact owner scopes, 19 authoritative memories, 29 entities, 20
  pre-seeded rich edges. The runner made zero model calls, external HTTP requests,
  and provider-token calls.
- Unique run-specific Neo4j groups were removed in `finally`:
  `fixture_cleanup_performed=true`; `cleanup_errors=[]`.

## Result

| Profile | Evidence recall | Complete evidence | Drift recovery | Forbidden | Candidate noise | Scope leakage | p50 / p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Strict path | 0.600 | 0.667 | 0/8 | 0 | 0 | 0 | 12.045 / 27.663 |
| Candidate path | 1.000 | 1.000 | 8/8 | 0 | 5 | 0 | 15.023 / 24.811 |
| Exact + candidate union | 1.000 | 1.000 | 8/8 | 0 | 5 | 0 | 14.992 / 45.895 |

Union added 0.400 absolute evidence recall and 0.333333 complete-evidence rate
relative to strict paths. It returned 0.583333 more memory IDs per query on average.
The eight drift cases account for all 16 memory IDs missing under the strict profile.
The candidate profile alone also reached 1.000 on this generated dataset because its
alternative sets intentionally include the exact stored type. This is a structural
ceiling for the supplied candidate topology, not a measured natural-language
candidate generator.

All five candidate-noise occurrences come from one deliberately widened camera
branch across three queries. They represent two distinct memory IDs repeated across
queries: two in `q-camera-a-two-hop`, one in `q-camera-a-one-hop`, and two in
`q-camera-a-ontology-drift`. They are related graph context and were neither required
evidence nor forbidden security/temporal evidence. This experiment does not measure
whether an answer model would select the correct support among those candidates.

The union had 16 eligible cases with both exact and candidate path support and zero
dual-attribution failures. It had zero duplicate fused paths. Compilation accounted
for 36 observations: 34 compiled, one disconnected observation rejected as ambiguous,
and one three-hop observation rejected as over-bound. The four adversarial controls
for not-yet-valid time, orphan provenance, disconnected topology, and over-bound
topology returned no memory IDs. No scope leakage or forbidden hit was observed.

The union executed 68 graph route queries across 36 questions, versus 34 for each
single-route profile. Its p95 was higher than either individual profile despite
concurrent route execution. These single-run warm timings are diagnostics, not a
stable latency claim; no repeated idle/competitive performance measurement was made.

## Interpretation and next test

The live result confirms that bounded candidate-type widening can recover evidence
when an otherwise valid relation path uses a nearby but different stored edge type.
It also confirms the expected recall/precision trade-off in this small synthetic
fixture. Scope, subject, temporal, provenance, and Store checks remained active.

The next unknown is whether a model can generate useful candidate topology from
question wording and host ontology without seeing the fixture labels. That needs a
separate dataset and evaluation of topology generation before the candidate route is
connected to `PersonalMemoryQueryEngine`. The present 36-query dataset was opened for
retrieval development and must not be reused as sealed generator gold. A later
highest-configuration benchmark should also test lexical, pgvector, Graphiti semantic,
and relation-path candidates together while recording context size and answer support.
