# Personal relation v2 Reference Planner retrieval — 2026-09-09

This is a development diagnostic over the unfrozen
`personal-relation-ablation-zh-v2.json` draft. It measures retrieval over a fixed
Reference Planner report; it is not a publication-ready claim and it does not
measure answer generation.

## Reproducibility

- runtime source commit: `563b008e3880aca133e099c2d51d83d37646a56e`
- dataset version: `2.0.0-draft.2`
- dataset fingerprint:
  `f62c9d21fb3d7a472eb9e6cc14d007654943afcede500dd1874f04f0c21b7d41`
- dataset: 72 memories, 240 queries, 12 exact owner scopes
- Planner: `doppel.reference-personal-memory-query-planner`
  version `12.3c3bac4f436d3ac4`
- Planner report SHA-256:
  `ba898a3682e8b0a1f6216e5ef6b4a07aba28ae6a1572d66f15c98bf3ea2f2ee9`
- PostgreSQL + pgvector: live
- vector provider: FastEmbed `BAAI/bge-small-zh-v1.5`, 512 dimensions
- Neo4j/Graphiti: live, 72 rich relation edges and 72 episodes preseeded
- candidate fusion: opt-in `union`
- retrieval replay provider calls: zero
- retrieval report SHA-256:
  `70b759945ca09590609bb270eaa357c7f4701890af3a3ba16a3d87c84f534bf9`
- retrieval canonical payload SHA-256:
  `68fe8ff673f18bff7b88641f3574011fd6326c16788e4b8a78fe07b1a4f34ff3`
- source-tree SHA-256:
  `c9f871e0640e915bc349fc80bef48cb21a6170b9c8cd1115d12383ad71985a03`

The only tracked dirty path during the final replay was the pre-existing user-owned
`uv.lock` modification. PostgreSQL was reset after the run and no Graphiti fixture
nodes remained.

## Fixed Planner report

All 240 cases were attempted. The report contains 230 valid drafts and 10 validation
errors. Those ten errors are all `temporal_boundary` cases in which the provider
selected `intent=as_of` but omitted the required `as_of` field. The explicit date in
the raw question could not reach Doppel's host calendar grounding because draft model
validation failed first.

| Planner metric | result |
| --- | ---: |
| exact / typed structure accuracy | 0.2042 |
| intent accuracy | 0.8708 |
| temporal plan accuracy | 0.9083 |
| subject binding accuracy | 0.9583 |
| entity recall | 0.5609 |
| open relation-hint recall | 0.4217 |
| canonical relation-type exact accuracy | 0.9125 |
| canonical relation-type recall / precision | 0.9522 / 0.9865 |

The paid Planner pass used 240 calls, 376,198 input tokens (365,184 reported as
cached input), 24,779 output tokens, and 400,977 total provider tokens. The retrieval
replays below reused that immutable report and made no provider call.

The low exact-structure score is dominated by missing exact entity spans and verbose
or different open-text relation hints. Canonical ontology classification is materially
stronger. Runtime tuning must therefore not treat the open-text exact metric as a
proxy for typed relation quality.

## Final candidate-union retrieval

All metrics keep failed Planner attempts in the declared denominator. Latency is one
local pass and is diagnostic, not a controlled warm-latency claim.

| profile | R@1 | R@5 | MRR | nDCG@5 | evidence recall | forbidden links | context R@5 | no-evidence abstention | p50 / p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lexical | 0.6250 | 0.8438 | 0.7344 | 0.786272 | 0.8438 | 23 | 0.9583 | 0.9167 | 6.471 / 8.560 |
| lexical + vector | 0.7812 | 0.9323 | 0.8568 | 0.882071 | 0.9323 | 27 | 1.0000 | 0.1250 | 15.617 / 18.509 |
| lexical + typed relation | 0.8281 | 0.9323 | 0.8802 | 0.877989 | 0.9323 | 23 | 0.9583 | 0.9167 | 21.627 / 32.860 |
| lexical + vector + typed relation | 0.8281 | 0.9323 | 0.8802 | 0.893367 | 0.9323 | 27 | 1.0000 | 0.1250 | 26.290 / 32.789 |

Relative to lexical + vector, the full profile gains 0.0469 Recall@1, 0.0234 MRR,
and 0.011296 nDCG@5 while preserving Recall@5, evidence recall, forbidden-link count,
and every safety gate. Its observed p50 cost is 10.673 ms.

## What changed after the first replay

The legacy `relation_gate` replay reduced the full profile to 0.1823 Recall@1 because
provider-selected relation types were suggestions, yet every result still had to pass
an open-text Graphiti relation threshold. A first union replay recovered 0.7917
Recall@1, but the adapter did not preserve whether an edge matched the suggested
canonical type. A type-conflicting edge whose fact shared an open hint could therefore
receive more relation score than the typed edge.

Commit `563b008` separates relevance from authority:

1. host `required_relation_types` remain the only hard relation-type filter;
2. default `relation_gate` caps provider type-only matches below its evidence gate;
3. opt-in union can use a matching canonical type as ranking evidence;
4. a type-conflicting lexical edge remains available at the adjacency floor;
5. an explicit relation reranker may still provide an independent semantic match.

Against the pre-fix union replay, seven Top-1 answers changed from wrong to correct and
none changed from correct to wrong. The full profile moved from 0.7917 to 0.8281
Recall@1. Relation attribution in the final report contains 98 correct links and two
incorrect links across the evaluated profiles.

## Safety and remaining failures

Every executed profile recorded zero exact-scope leakage, temporal violations,
provenance failures, and inactive-candidate acceptance. PostgreSQL Store reload remains
authoritative over both pgvector and Graphiti candidates.

The run intentionally remains a failed quality gate:

- ten source Planner drafts fail validation before host calendar grounding;
- the full profile has six queries with forbidden distractors in its returned window,
  concentrated in explicit negated-relation contrasts;
- vector-backed profiles return some candidate for 21 of 24 true no-evidence queries;
- the draft dataset has not received independent semantic review or been frozen.

These are not scope-security failures. They show that high-recall candidate retrieval
is not an answer-support decision. A downstream LLM may judge returned evidence, but
Doppel must continue reporting retrieval and answer/evidence qualification separately.

## Follow-up gate

The follow-up implementation now permits only `intent=as_of` with a missing `as_of`
coordinate to reach host-owned explicit-calendar grounding, then strictly revalidates
the complete draft. It adds no entity, relation, language-domain, or benchmark-case
vocabulary and does not change the Planner prompt, schema, version, or provider request.

The cache retains 230 valid drafts; the ten invalid first-pass outputs were not cached.
Therefore the next live verification needs at most ten provider calls, not 240. It must
demonstrate 230 cache hits, re-run exactly those ten cases, and report whether all ten
explicit dates become valid. A subsequent retrieval replay remains zero-paid and must
preserve scope, temporal, provenance, and inactive-candidate gates.

That follow-up exposed a benchmark-boundary limitation: the historical cache stored
processed final drafts, so its 230 hits bypassed newer Planner execution code. The
current runner supersedes that cache with a separate raw-provider-output namespace;
legacy final drafts remain historical artifacts and are never mixed into a fresh
current-implementation result.
