# Hybrid path-candidate assembly V2: live opened-corpus result

Date: 2026-09-23

Runner: `doppel.hybrid-path-candidate-ablation.v2`

Dataset fingerprint: `dea12fa561160f72cb2d8fcc4b4e467ae2e6556096724125dbd943a5036b094a`

Canonical report hash: `647645558ec844c711ceceec1779fee58146495c8beeddc98306c64703c43ec5`

## Outcome

The corrected V2 development gate passed.

| profile | evidence recall | complete evidence | missing | hard forbidden | related/incomplete | recovery | average candidates | p50 | p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lexical + pgvector | 0.900 | 0.833 | 4 | 0 | 6 | 0.750 | 1.889 | 11.622 ms | 26.563 ms |
| typed path | 1.000 | 1.000 | 0 | 0 | 5 | 1.000 | 1.250 | 16.244 ms | 25.117 ms |
| assembled union | 1.000 | 1.000 | 0 | 0 | 6 | 1.000 | 2.000 | 34.090 ms | 53.322 ms |

Against independent lexical + pgvector retrieval, the assembled result gained:

- `+0.100` absolute evidence recall;
- `+0.166667` absolute complete-evidence rate;
- `+0.250` recovery rate on the eight ontology-drift cases.

It matched the typed-path structural ceiling while preserving independently retrieved
context. Related/incomplete candidates increased from five to six because the valid
orphan first-hop memory is now measured as context, not mislabeled as hard forbidden.
The answer layer still receives `answer_support=unassessed` and must decide whether any
candidate supports its conclusion.

## Integrity checks

- All 36 per-query candidate ID lists were identical between V1 and V2 for each of the
  three profiles. The pass came only from the pre-registered label-contract correction;
  retrieval and ranking output did not change.
- Scope leakage: `0` in all profiles.
- Hard temporal/authority/lifecycle/provenance forbidden hits: `0`.
- Base-hit Store revalidation rejections: `0`.
- Typed-path Store revalidation rejections: `0`.
- Context-budget path omissions: `0`.
- Truncated queries: `0`.
- Retained typed paths: `27`.
- Neo4j fixture residue: `0`; PostgreSQL benchmark schema reset succeeded.

The run used PostgreSQL as the authoritative Store, pgvector with local
`BAAI/bge-small-zh-v1.5` 512-dimensional embeddings, and live Neo4j through
`GraphitiRelationIndex`. It made zero paid LLM calls, zero provider-token calls, and
persisted no credentials.

## Interpretation

This result supports the architecture: typed paths should be an additive candidate
source alongside semantic retrieval, not a global gate and not a substitute for the
answer model. On this opened, oracle-topology corpus, paths recover second-hop evidence
that the independent branch misses without causing scope or temporal leakage.

It does **not** establish end-to-end natural-language quality. The topology inputs are
dataset supplied, and earlier model-generated candidate-path runs remain below their
two-hop gate. The next honest milestone is a new frozen combined corpus where model-
generated topologies, independent semantic retrieval, assembly, and answer/evidence
judgment are measured together without reopening these 36 development labels.
