# Personal relation-path live Neo4j ablation — 2026-09-19

This is a development diagnostic over the unfrozen
`personal-relation-path-ablation-zh-v1.json` draft. It measures whether explicitly
typed one/two-hop paths recover all supporting memories without crossing scope, time,
or provenance boundaries. It does not measure natural-language path planning, answer
generation, or general graph-retrieval quality.

## Reproducibility

- source commit: `4b291838c0be1e04136c749ca0fe4d48a1a687ff`
- result schema version: `1`
- dataset version: `1.0.0-draft.1`
- dataset fingerprint:
  `7d67c725a023850b750777a306fda5d882086d54195d7c963d58c2ba2450af3e`
- dataset: 26 queries, 9 exact owner scopes, 17 authoritative Store memories,
  27 entities, and 18 Graphiti-compatible relation edges
- partitions: 9 dev, 9 heldout, 8 adversarial
- runtime: Windows `10.0.26200.0`, Python `3.12.7`
- Neo4j: `neo4j:5.26-community`, server `5.26.29`
- external HTTP requests, LLM calls, embedding calls, and provider tokens: zero
- raw local report SHA-256:
  `9aad09f0e4e702675d67d13e49ab916b9843e525b8894e79f114185aeac5504f`
- cleanup: zero matching fixture nodes remained after the run

The repository had the pre-existing tracked `uv.lock` modification during the run;
the benchmark implementation and dataset matched the source commit above. The raw
JSON is intentionally ignored under `data/doppel/`; this report preserves the measured
summary while the result schema preserves its machine-readable contract.

## Results

| profile | evidence recall | complete evidence | missing evidence | forbidden | scope leaks | path-count failures | endpoint failures | p50 ms | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| typed one-hop | 0.667 | 0.500 | 8 | 0 | 0 | — | — | 10.8 | 13.0 |
| typed bounded path | 1.000 | 1.000 | 0 | 0 | 0 | 0 | 0 | 10.3 | 13.7 |
| one-hop + path union | 1.000 | 1.000 | 0 | 0 | 0 | 0 | 0 | 20.0 | 26.0 |

The bounded path contributes `+0.333333` evidence recall and `+0.500000` complete-
evidence rate over the one-hop structural baseline. All eight answerable two-hop cases
returned both per-hop supporting memories. All eight one-hop controls remained valid.
All eight wrong-type path adversaries returned no path. The not-yet-valid second hop
and the orphan-provenance second hop also returned no path.

The union profile intentionally retains the ordinary one-hop candidate on wrong-type,
time-boundary, and orphan-path cases. That is related context, not a claimed path or
answer; therefore evidence completeness and forbidden evidence remain separate from
candidate presence. The pure typed-path profile demonstrates that the exact relation
constraints themselves reject those paths.

## Interpretation and next gate

This run validates the bounded traversal, per-hop provenance reload, exact-scope gate,
per-hop time gate, direction/type constraints, and cleanup on a live Neo4j backend. It
also demonstrates that two-hop retrieval can supply the second supporting memory that
a one-hop lookup cannot reach.

It is not yet evidence that a user question can be translated into the correct path.
Every query supplied oracle relation types and directions. The dataset remains
`frozen=false` and `publication_ready=false`; latency is one uncontrolled run and must
not be treated as a stable performance claim. The next product gate is an additive
Planner v3 path draft plus cached model evaluation on a larger, independently reviewed
corpus. Runtime code must not acquire benchmark phrases or domain-specific question
rules to pass that gate.
