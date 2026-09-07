# Offline whole-candidate reranking replay

Date: 2026-09-07. Development diagnostic only; not publication-ready.

## Inputs and boundary

- Source: live union profile `lexical_vector_relation_reranked` from commit
  `6f316c3`, 65 attempts / 50 evidence-bearing queries. Source SHA-256:
  `da807b42f1ee00db74f3fa58e1b62de76660db566c848fa5fb0db0f324d497aa`.
- Exact historical dataset v1.2 loaded read-only from that Git revision, fingerprint
  `00faec11ddb3ce5c84dcaeb0251cc6e118bbac8f1f1da5c42eaf5fcc503f1ffd`.
  Current v1.3 intent-label changes do not alter query text, candidate text, required
  IDs, or legacy forbidden IDs, but this replay deliberately does not mix fingerprints.
- Same local BGE-reranker-v2-m3, SentenceTransformers 6.0.1, sigmoid raw logits,
  CUDA, batch 16. Model-hub offline. External LLM calls and paid tokens: zero.
- The replay sees only candidates already returned by the source engine (maximum
  result limit), after Store/scope/authority/time/score gates. It reorders the set
  and cannot recover candidates absent from that source list. Candidate IDs exposed
  to the model are opaque batch aliases; report IDs are for local evaluation.
- No new threshold, filtering, answer generation, dataset labels, or runtime code.
  Legacy forbidden top-1 is an exclusion diagnostic, not automatically a security
  failure. Graded relevance/nDCG remains unavailable.

## Results

| Input to reranker | R@1 | R@5 | MRR | Legacy forbidden top-1 | Gains | Losses |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Existing additive order | .920 | .960 | .940 | 9 | — | — |
| Raw question + candidate type/fact | **.940** | .960 | **.950** | 6 | q36, q38 | q39 |
| Raw question + v9 Planner context + candidate type/fact | .900 | .960 | .930 | 4 | q36, q38 | q39, q53, q54 |

Candidate membership changed in zero cases. Raw-question reranking fixes passport
storage vs issuer (q36) and repairer vs repair location paraphrase (q38). It regresses
q39: the question explicitly says “where, not who repairs”, but the cross-encoder
scores the repair-person fact .551 vs the repair-location fact .498. The model does
not reliably honor negation/role exclusion.

Adding v9 Planner context does not fix q39 and loses q53/q54. It lowers R@1 by two
points from the existing order despite reducing legacy forbidden top-1. This confirms
that inferred Planner fields are useful candidate-generation hints but should not be
promoted uncritically into ranking authority.

The first raw arm reports 12.6 seconds including model cold load; the subsequent
Planner-context arm reports 1.6 seconds. Arm latency therefore is not an A/B speed
comparison or production SLA.

## Decision

Do not add a product-level memory reranker or make union default from this inspected
sample alone. Preserve the benchmark tool and use it after fresh v11 Planner results
and reviewed graded relevance are available. A future ranking experiment should:

1. keep the raw question as the primary semantic input;
2. treat Planner relation types as bounded features, never unquestioned truth;
3. explicitly evaluate negation and requested endpoint role on new examples;
4. combine base retrieval and cross-encoder scores on development data rather than
   replacing order wholesale, then freeze before unseen testing;
5. report correct-evidence ranking, useful contextual clues, irrelevant displacement,
   latency and GPU cost separately.

Raw local artifact:
`data/doppel/personal-candidate-rerank-replay-20260907.json`, SHA-256
`3b9735622282dec6f7a627987038b27fc30aa51eb48b9ca569d368e7b9dad830`.
The sidecar matches. Artifacts remain ignored and are not committed.
