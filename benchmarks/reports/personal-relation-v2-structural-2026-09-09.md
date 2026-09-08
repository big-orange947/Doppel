# Personal relation v2 structural retrieval — 2026-09-09

This is a development diagnostic over the unfrozen
`personal-relation-ablation-zh-v2.json` draft. It is not a publication-ready quality
claim and it does not measure answer generation.

## Reproducibility

- source commit: `293ed78d8eb4e81218cfe269ba30f7f34f415f7e`
- dataset version: `2.0.0-draft.2`
- dataset fingerprint:
  `f62c9d21fb3d7a472eb9e6cc14d007654943afcede500dd1874f04f0c21b7d41`
- dataset: 72 memories, 240 queries, 12 exact owner scopes
- PostgreSQL + pgvector: live
- vector provider: FastEmbed `BAAI/bge-small-zh-v1.5`, 512 dimensions
- Neo4j/Graphiti: live, 72 rich relation edges and 72 episodes preseeded
- external HTTP, paid LLM calls, and provider tokens: zero
- scope, temporal, provenance, and inactive-record violations: zero in every
  executed profile
- main report SHA-256:
  `cd023e6c62eed41a1fbab14bdca0cedf16aa8df6b9769e7a7e968f52669ff24a`
- explicit-union diagnostic SHA-256:
  `6e3280ea5ce15243021179e400799b6d3a136dac240897bec372319750b80ba9`

The repository had the pre-existing tracked `uv.lock` modification during the run;
the report records it as dirty. No benchmark source or runtime source was dirty.
Latency was observed only incidentally in one pass and is deliberately not reported
here; controlled repeated warm-latency measurement remains deferred.

## Structural ceiling with typed oracle planning

The typed oracle supplies only the gold intent/time/entity/relation type. It never
supplies a memory ID, target entity, topic key, or answer. This is a retrieval ceiling,
not production Planner quality.

| profile | R@1 | R@5 | MRR | nDCG@5 | forbidden | context R@5 | no-evidence abstention |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lexical | 0.573 | 0.682 | 0.628 | 0.595 | 12 | 0.750 | 0.917 |
| lexical + vector | 0.917 | 1.000 | 0.958 | 0.910 | 24 | 1.000 | 0.000 |
| lexical + typed relation | 1.000 | 1.000 | 1.000 | 0.732 | 0 | 0.000 | 1.000 |
| lexical + vector + typed relation | 1.000 | 1.000 | 1.000 | 0.732 | 0 | 0.000 | 1.000 |

The vector path finds every grade-1 related-context case, but it also returns a result
for every truly unknown entity and hits all 24 explicitly negated-relation distractors.
The typed relation path does the inverse: it identifies every direct answer at rank 1,
returns no forbidden relation, and cleanly abstains for unknown entities, but returns
none of the useful context when the requested predicate has no direct edge.

The lower relation nDCG is therefore not a contradiction with perfect direct-answer
Recall. nDCG rewards both grade-2 answer evidence and grade-1 supporting context; the
current hard relation result contains the former and intentionally filters the latter.

## Deterministic planning path

| profile | R@1 | R@5 | MRR | nDCG@5 | forbidden | context R@5 | no-evidence abstention |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lexical | 0.594 | 0.755 | 0.673 | 0.670 | 28 | 0.750 | 0.958 |
| lexical + vector | 0.740 | 0.906 | 0.823 | 0.830 | 36 | 1.000 | 0.000 |
| lexical + relation | 0.594 | 0.755 | 0.673 | 0.670 | 28 | 0.750 | 0.958 |
| lexical + vector + relation | 0.740 | 0.906 | 0.823 | 0.830 | 36 | 1.000 | 0.000 |

The deterministic Planner has 41 intent-structure failures and produces no accepted
relation contribution on this dataset. Both relation profiles are numerically
identical to their non-relation controls. This local Planner is deliberately small;
adding entity- or predicate-specific Chinese vocabulary to make the benchmark pass is
not an acceptable fix.

## Candidate-fusion diagnostic

Repeating `lexical_vector_relation` with `candidate_fusion=union` and typed oracle
planning produced the same direct/context/empty results as the default relation gate.
That is expected from the current contract: an explicit `relation_types` value remains
a hard evidence constraint in union discovery mode. Union can preserve independently
discovered candidates when the relation is suggestive, but it does not weaken an
explicit relation constraint.

## Conclusions and next gates

1. The Graphiti relation index, exact-scope Store reload, time filtering, and relation
   type gate work correctly when the requested type is known.
2. Natural-language relation typing is now the primary unmeasured dependency. Run the
   Reference Planner once over draft.2, cache every successful draft, and replay that
   fixed report through the same four profiles.
3. Direct answer evidence and useful non-answer context need distinct result channels.
   A future additive design may retain hard-constrained `hits` and expose separately
   labeled `context_hits`, both behind the same scope, authority, lifecycle, temporal,
   provenance, and Store-revalidation gates. Simply weakening relation constraints
   would erase the measured precision benefit.
4. Dataset wording and judgments still require independent semantic review before
   freezing. All tuning must use `dev`; held-out/adversarial results must not become
   an iterative target.

