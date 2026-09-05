# Natural Planner replay: relation candidates and BGE reranking

Date: 2026-09-05. This is a development diagnostic, not a publication-ready
benchmark or a claim about unseen-query generalization.

## Reproduction and boundaries

- Evaluated code: `e46ffbf4b4f92ae71ac32e85e2b4a06883b51aed`.
- Dataset: `personal-relation-ablation-zh-v1.json`, version `1.2.0-draft`;
  28 fixtures, 65 queries, 5 owners. Partitions: dev 20 / heldout 23 /
  adversarial 22. These partitions have already been inspected repeatedly.
- Dataset fingerprint:
  `00faec11ddb3ce5c84dcaeb0251cc6e118bbac8f1f1da5c42eaf5fcc503f1ffd`.
- Source drafts: `data/doppel/catalog-ablation/20260903T083605Z-a794943e/definitions.json`.
  SHA-256: `ae32e462277c92ff4385ef595f86dfc3e5b1abb7d7561eecc5d3ad4ea3c8ca2c`.
  These were generated with Reference Planner v9, not the current v10 prompt.
- Replay binds inferred relation types as candidates, not host hard constraints.
  No oracle relation labels are supplied to the replay planner.
- Each profile retains 65 attempts: 64 valid drafts and the original failure
  `rel-q41`. This is one failed source attempt replayed six times, not six new
  provider failures. Recall/MRR use 50 evidence-bearing queries, including failure.
- PostgreSQL is authoritative; pgvector uses local BGE-small-zh-v1.5 (512D).
  Neo4j/Graphiti uses 28 preseeded episodes, 27 rich edges and one fallback edge.
  This does not evaluate live LLM extraction or graph construction quality.
- Local BGE-reranker-v2-m3 uses SentenceTransformers 6.0.1, Torch 2.7.1+cu128,
  RTX 4070 Laptop GPU, batch 4, raw-logit sigmoid, threshold 0.90, no query prefix.
  Configuration and weights are unchanged from the previous reranker experiment.
- Zero new paid LLM calls: drafts are replayed and Graphiti uses the benchmark's
  LLM-disabled client. Model hub offline flags were enabled. No new threshold was
  selected from this run's heldout/adversarial results.
- All six profiles executed with live-backend/all-profile requirements. Quality
  exit status remains **1**, with Planner failures, forbidden hits and missing
  evidence preserved. Metamorphic variants were not run in this replay.

## Results

| Profile | Recall@1 | Recall@5 | MRR | Evidence recall | Forbidden hits | Abstention accuracy | p50 ms | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lexical | .760 | .780 | .772 | .800 | 18 | .7385 | 7.585 | 8.687 |
| lexical_vector | .820 | .920 | .872 | .940 | 21 | .7385 | 21.120 | 35.190 |
| lexical_relation | .640 | .660 | .650 | .660 | 1 | .7385 | 21.059 | 175.326 |
| lexical_vector_relation | .640 | .660 | .650 | .660 | 1 | .7385 | 25.874 | 30.847 |
| lexical_relation_reranked | .780 | .780 | .780 | .780 | 2 | .8154 | 42.495 | 53.165 |
| lexical_vector_relation_reranked | .780 | .780 | .780 | .780 | 2 | .8154 | 56.947 | 74.562 |

Latency measures successful local query executions, not LLM planning, model startup,
fixture preparation or a production load test. The first relation profile has a
cold-path tail; profile order is not randomized and these are not steady-state SLAs.

The relation gate sharply reduces false acceptance but loses recall. BGE recovers
7 top-1 successes (32 -> 39 out of 50), improves evidence recall by 12 percentage
points, and introduces one additional forbidden hit. Relative to lexical, the
reranked relation path has 16 fewer forbidden hits, but not higher evidence recall.
The strongest-recall vector path is not the safest path.

Scope leakage, invalid provenance, inactive acceptance, agent-output acceptance and
retrieval-attributed temporal violations are zero in this sample. This does not
erase Planner temporal misses or establish safety across arbitrary inputs.

## Confirmed findings

1. **Similarity is not evidence of the requested relationship.** `rel-q21` asks who
   purchased a book. BGE scores a `HELD_BY` fact at `0.985680`, promoting it despite
   no purchase evidence. A higher similarity threshold is not a general solution.
2. **Surface predicate matching can accept the wrong role.** `rel-q37` asks who
   repairs a laptop. A `LOCATED_AT` repair-shop fact survives lexical relation
   matching. Reranking places the correct `REPAIRED_BY` hit first, but the wrong
   location remains accepted even with reranker score `0.812067`, below 0.90,
   because lexical matching independently qualifies it. The reranker currently
   promotes candidates; it is not a universal veto or entailment verifier.
3. **Adding vector search cannot bypass the current relation qualification gate.**
   In `PersonalMemoryQueryEngine.execute`, an available relation index with requested
   relation semantics restricts final records to accepted relation keys. Both
   relation/vector combinations consequently have identical quality here. This
   does not prove vector retrieval is useless; it identifies the current bottleneck.
4. **Correct query planning is not sufficient.** `rel-q54` has an accepted day
   interval and entity anchor; the historical access-card evidence appears in the
   vector profile but not either relation profile. Stage-by-stage candidate/rejection
   tracing is needed before assigning the miss to discovery, scoring or filtering.
5. **Planner imperfections remain separate.** The source still includes an invalid
   draft, temporal differences and entity/surface-hint differences. Surface exact
   mismatch is not automatically proof of a semantic failure. Do not equate the
   earlier relation-type exact-match percentage with end-to-end retrieval recall.

## Evaluation correction and reporting limitations

The original run at `971b1f6` reported one temporal violation in `rel-q10`.
The query asks about 2025; the accepted Planner interval spans that year. The
evaluator incorrectly checked a September record against the fixture's representative
June as-of point. Commit `e46ffbf` instead checks overlap with an explicitly accepted
interval; point queries and out-of-interval records remain checked. Regression tests
also verify that forbidden evidence remains forbidden despite temporal overlap.
The September bicycle-repair record is still irrelevant to the employment question;
correcting its time classification does not make it useful evidence.

Both original and corrected raw reports remain intact. Re-running changed no
recall/MRR/forbidden-hit result. No fixture, expected answer, production retrieval
algorithm, model configuration or Planner output was changed in this correction.

Current report limitations must not be hidden:

- `relation_final_hit_attribution` is oracle-only and reports unavailable in replay
  mode. Per-hit reasons still show actual relation matches; an unavailable summary
  must not be interpreted as an unexecuted relation path.
- The vector contribution counter expects named semantic-source reasons that the
  direct vector adapter does not supply here. Its zero counter is not proof of zero
  vector work: positive semantic scores and changed vector-profile hits are visible.
- Forbidden-ID lists are not exhaustive relevance annotations; forbidden-hit counts
  can undercount irrelevant accepted memories. Abstention accuracy checks empty vs
  nonempty output, not whether a nonempty answer is correct.

## Next development sequence

1. Add general stage-level retrieval traces: candidate source, discovery, exact
   scope/provenance/time eligibility, predicate/role qualification, rejection reason,
   and final promotion. Repair replay/source attribution without changing scores.
2. Introduce an independently evaluated evidence-support verifier: can this fact
   answer the requested relationship and role, as opposed to merely sharing entities
   or wording? Keep lexical/vector/BGE scores as candidate/ranking signals. Compare
   optional verifier configurations; do not promote inferred labels to hard filters.
3. Route candidates from vector and relation discovery through the same support
   checks, so useful vector-only evidence can be recovered without bypassing scope,
   authority, provenance or time gates. Add generic entity-alias resolution tests.
4. Freeze decisions on dev only, then build genuinely unseen queries with new
   entities and relationship combinations. Require no new forbidden/security/time
   failures and report recall, answerability, calibration, latency and cost together.

Do not add query-ID/fixture-keyword special cases, simply loosen the relation gate,
or switch BGE models solely to raise this inspected dataset's pass rate.

## Artifacts and cleanup

- Original: `data/doppel/relation-candidate-replay-live-20260905-971b1f6.json`.
- Corrected: `data/doppel/relation-candidate-replay-live-20260905-v2.json`.
- Corrected file SHA-256:
  `56a053de02575e72af1cccab3ba07ceef8b4fcae2b61d0f89ed7f935687eef09`.
- Corrected report schema and SHA-256 sidecar verified.
- Post-run read-only checks: zero graph nodes in the five fixture scopes; zero
  public tables in the dedicated ablation database after runner cleanup. Existing
  Neo4j/PostgreSQL containers and volumes remain, both healthy.
- Full regression: 454 passed, 31 skipped, 3 subtests passed; Ruff and Pyright clean.
  The pre-existing user modification to `uv.lock` was not touched or staged.
