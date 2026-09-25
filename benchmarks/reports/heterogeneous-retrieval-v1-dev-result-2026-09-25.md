# Heterogeneous retrieval V1 — opened dev diagnostic

This is the first live result from the frozen V1 corpus and runner. It used only the
120 open dev queries. No sealed or adversarial query result was opened. The run used
the complete 9,216-memory, 48-scope index so the dev slice retained the frozen density
and cross-owner collision pressure.

- implementation commit: `5c31f662885d2bbb43957355d4a18ad32f8be39b`
- dataset fingerprint:
  `927763a1cb73163f7c494a80a2b9838af1cb558cb3a44e2a6816a97bbbd54e03`
- report payload hash:
  `f291684fbd34257d280cb47dedb94e19eef087955f4f3db51e6f429c5d9ba0ca`
- ignored raw file SHA-256:
  `3cbb1fe829a642067896f5d7a59f52e90345f79db3a269aeaaafeecd4d59ffd1`
- external HTTP / LLM calls / provider tokens: `0 / 0 / 0`

## Overall result

| profile | evidence recall@5 | complete evidence@10 | MRR | p50 / p95 ms |
| --- | ---: | ---: | ---: | ---: |
| independent lexical + pgvector | 0.636 | 0.667 | 0.727 | 81.1 / 103.5 |
| oracle Graphiti path only | 0.273 | 0.222 | 0.222 | 0.0 / 19.6 |
| Store-revalidated oracle hybrid | 0.720 | 0.769 | 0.727 | 162.0 / 252.8 |
| oracle hybrid + memory reranking | **0.811** | **0.880** | **0.847** | 294.5 / 438.1 |

The highest-quality profile improved all three headline quality metrics, but correctly
failed the complete preregistered gate. The selection was dev-only, evidence recall@5
was below 0.85, and the remaining category failures were not hidden.

All structural safety counters on the final profile were zero: scope leakage, subject
violations, exposed candidate/expired/superseded or agent-output records, temporal
violations, orphan provenance, Store reload failures, reranker membership changes, and
path-budget omissions. Neo4j and the dedicated PostgreSQL schema were cleaned.

## Diagnosis

Eight of the nine answerable non-count categories reached 1.000 evidence recall@10,
except two-hop relation retrieval at 0.958 (complete evidence@10 0.917). Current and
historical residence, corrected facts, one-hop relations, documents,
cross-conversation preferences, and owner subject correction all retrieved their
required evidence.

The three remaining issues have different causes:

1. All 12 episode-count queries returned no candidates. Doppel's exact count path
   deliberately avoids bounded semantic top-k and requires a Planner to narrow the
   exhaustive scan with an episode memory type/topic. The frozen oracle supplied the
   operation and time view but no type/topic, so query wording alone did not clear the
   lexical gate. This is a Planner-to-count-plan gap, not a reranker miss.
2. Related-but-insufficient buyer context reached 5/12 queries at rank 10. The next
   runner records independent pre-rerank window coverage to distinguish missing
   pgvector candidates from reranking errors.
3. The 12 hard-forbidden hits were all the same semantic labeling mistake: the owner's
   corrective fact and the superseded peer guess were both retrieved for a question
   explicitly asking about conflicting group claims. That peer claim is useful related
   context, not proof of the answer and not an absolute retrieval prohibition. The
   genuinely wrong-subject friend fact remained excluded.

The run also exposed two harness-only accounting defects: `not_run` was counted as a
reranker failure even when a query had zero candidates, and leading whitespace was
trimmed before parsing `git status`, rendering `uv.lock` as `v.lock`. Both are corrected
without changing retrieval behavior or any quality threshold.
