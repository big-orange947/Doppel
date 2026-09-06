# Live paired candidate-union replay

## Scope and reproducibility

- Evaluated code: `6f316c3c0629ad2ad39bce4642d6862b61a4d44e`.
- Dataset: personal-relation-ablation-zh-v1, 28 memories / 65 queries / 5 owners.
  Development 20, inspected heldout 23, adversarial 22. This is not unseen evidence
  or a publication-ready quality claim. Dataset fingerprint:
  `00faec11ddb3ce5c84dcaeb0251cc6e118bbac8f1f1da5c42eaf5fcc503f1ffd`.
- Same cached Reference Planner v9 drafts in both runs: 64 valid plus one preserved
  failure (q41), no retry. Source SHA:
  `ae32e462277c92ff4385ef595f86dfc3e5b1abb7d7561eecc5d3ad4ea3c8ca2c`.
- Live PostgreSQL/pgvector and Neo4j/Graphiti; all six profiles execute in both
  runs. Same fastembed BGE-small-zh-v1.5 512D, local BGE-reranker-v2-m3, CUDA,
  batch 4, sigmoid normalization, threshold .90. Runtime metadata identical.
- Graph is preseeded (27 rich / 1 fallback episode), NOT live LLM extraction.
  Zero new paid LLM calls. Model-hub offline flags enabled.
- Only fusion mode differs: `relation_gate` vs `union`. Both use trace limit 300;
  no trace events dropped. No model/threshold/gold changes or evidence verifier.
- Recall/MRR denominator: 50 evidence-bearing queries including source failure.
  Empty/nonempty agreement uses all 65 attempts. No graded relevance annotations:
  nDCG remains unavailable. Metamorphic variants were not run.

## Results

| Mode | Profile | R@1 | R@5 | MRR | Evidence recall | Legacy forbidden | Empty-output agreement | p50 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gate | lexical | .760 | .780 | .772 | .800 | 18 | .7385 | 7.901 |
| gate | lexical_vector | .820 | .920 | .872 | .940 | 21 | .7385 | 22.285 |
| gate | lexical_relation | .640 | .660 | .650 | .660 | 1 | .7385 | 26.844 |
| gate | lexical_vector_relation | .640 | .660 | .650 | .660 | 1 | .7385 | 28.920 |
| gate | lexical_relation_reranked | .780 | .780 | .780 | .780 | 2 | .8154 | 39.447 |
| gate | lexical_vector_relation_reranked | .780 | .780 | .780 | .780 | 2 | .8154 | 57.015 |
| union | lexical | .760 | .780 | .772 | .800 | 18 | .7385 | 7.870 |
| union | lexical_vector | .820 | .920 | .872 | .940 | 21 | .7385 | 21.946 |
| union | lexical_relation | .880 | .900 | .890 | .900 | 18 | .8154 | 22.774 |
| union | lexical_vector_relation | .880 | .960 | .920 | .960 | 21 | .7538 | 27.605 |
| union | lexical_relation_reranked | .940 | .940 | .940 | .940 | 18 | .8462 | 38.146 |
| union | lexical_vector_relation_reranked | .920 | .960 | .940 | .960 | 21 | .7538 | 58.892 |

The gate run reproduces every hit list from the September 5 baseline. Lexical
and lexical_vector hit lists are identical across the two new runs. Latency is
one sequential local pass, excludes LLM planning and startup, includes diagnostic
collection, and is not a randomized steady-state performance claim.

## What changed and what did not

- Union vector+reranked-relation recovers 7 top-1 queries vs gate, loses none:
  q03/q07/q46/q48/q50/q54/q56. Evidence recall rises .78 -> .96.
- Against vector alone, it gains top-1 on q02/q09/q25/q33/q37, loses none;
  R@1 .82 -> .92, R@5 .92 -> .96, evidence .94 -> .96.
- Its legacy forbidden hit sets equal vector-only sets query by query (21 links).
  This is not evidence that irrelevant material disappeared. It returns 265 hits
  across attempts vs vector's 264. The old relation gate returned fewer contextual
  candidates; removing that restriction predictably restores legacy exclusions.
- No measured scope leakage, provenance, agent-output, inactive or retrieval-time
  violations in either run. Planner errors remain separately recorded.
- Both commands exit 1 honestly. Aggregate unique planner failures remain 46;
  retrieval failures 11 -> 8; security and fixture failures remain zero. These are
  labeled failure entries, not counts of independent failed queries.
- Source accounting now measures 249 vector-supported final hits in vector-only
  and union vector+relation profiles. Relation attribution is available in report
  mode; these counts are source support, not causal incremental benefit.

## Remaining diagnostic findings

1. q54's historical access-card memory is recovered and ranked first by union.
2. q60's correct memory is discovered by both semantic and relation paths, but
   trace records `temporal_status_mismatch` at the structural gate. Inspect the
   plan/fixture time-status semantics; do not loosen time filters to pass this ID.
3. q36 ranks the correct passport-location memory first in union relation-reranked,
   but second when vector is added, behind passport-issuer information. Independent
   candidate recovery is solved here; unified ranking remains an open issue.
4. q21 still returns the book-holder clue on a buyer question; q37 returns the
   correct repair person first but also the repair location. These remain legacy
   exclusions, not automatically security failures. No answer model was evaluated.
5. Full union's remaining required-evidence misses are q41 (original provider
   failure) and q60 (status filter). This small inspected set cannot establish a
   ceiling on production quality.

## Artifacts and operational notes

- `data/doppel/candidate-union-baseline-20260906.json`, SHA-256:
  `efa11e4d6a50314fb7b891db940c41003c04d448bd4788f45d97b76c4f9745bc`.
- `data/doppel/candidate-union-experiment-20260906.json`, SHA-256:
  `da807b42f1ee00db74f3fa58e1b62de76660db566c848fa5fb0db0f324d497aa`.
- Both JSON schemas and file-hash sidecars validated. Raw reports/logs stay in
  ignored local data; neither report is overwritten by this documentation commit.
- Docker normal startup failed with the recurring dockerInference socket access
  error. Only the two inspected runtime socket directories were renamed to dated
  backups with Docker stopped; no database volumes or factory reset. Both database
  containers restarted healthy; unrelated admission containers were untouched.
- An initial launch was stopped after detecting incorrect credential substring
  parsing; final runs used delimiter-based in-process extraction. No secrets were
  written into commands, artifacts or this report. No completed initial report.
- Post-run read-only checks: zero nodes in the five graph fixture scopes, zero
  public tables in the dedicated doppel_ablation database, both containers healthy.

## Decision

Keep union opt-in pending new-query validation. It is a promising retrieval
direction, not grounds for claiming a final default or adding an evidence judge.
Next: independently review relevance labels and time-status planning, then compare
uniform candidate reranking against the existing additive score on development
data, before freezing and testing genuinely unseen cases. Do not tune per-query
rules or thresholds against the inspected IDs above.
