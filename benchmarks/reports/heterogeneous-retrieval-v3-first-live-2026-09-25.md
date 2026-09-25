# Heterogeneous retrieval V3 — first all-partition live result

This is the first and immutable `--partition all --sealed-first-run` result for the
frozen V3 heterogeneous personal-memory corpus. It includes 120 previously open dev
queries, 280 sealed queries, and 80 adversarial queries. Owners are disjoint between
those partitions. The runner, thresholds, retrieval profiles, graph-exploration
contract, local models, candidate limits, and V3 dataset were committed before this
result was opened.

The complete gate passed. This is strong internal generalization evidence, but not a
publication benchmark: the deterministic synthetic corpus is author-known and remains
`publication_ready=false`; graph routes are oracle structural labels, not output from
a natural-language Planner; answer sufficiency remains `unassessed`.

## Reproducibility

- dataset: `doppel-heterogeneous-retrieval-zh-v3` (`3.0.0`)
- dataset fingerprint:
  `ead91761f9da403c31c8b759d427c4551709daf7d29f35d26d786f94ec167f88`
- corpus: 48 owner scopes, 9,216 memories, 480 unique Chinese queries
- selection: dev 120, sealed 280, adversarial 80
- execution HEAD recorded by the runner:
  `866868058f98a7d4b1be472aa93864dbc4283758`
- frozen executable revision: `45a7b9c7a95c01e8c0c8017817610a6b25e90315`
  (the intervening commit records only the dev report and documentation)
- report payload hash:
  `91c809b392bc6915f00bfddacb236d9aabb68ede2a2efb52a276e3fe91002e6c`
- raw JSON file SHA-256:
  `eba5f30ad3469dfeb8dcd7aff82e926e8cd34f66240c473f466c0f19efa3797e`
- raw local result: `data/doppel/heterogeneous-retrieval-v3-first-live.json`
- authoritative Store: PostgreSQL
- semantic index: pgvector, 512-dimensional cosine search with
  `BAAI/bge-small-zh-v1.5`
- relation index: local Neo4j/Graphiti exact paths and bounded exploration
- local reranker: `bge-reranker-v2-m3`, CUDA, 64-record window
- final context bound: 20 memories
- external HTTP calls / paid LLM calls / provider tokens: 0 / 0 / 0
- tracked dirty path disclosed by the runner: the pre-existing user-owned `uv.lock`

## Gate result

`gate.ok=true`, `status=complete`, with no failed check. Selection completeness,
overall and per-category evidence thresholds, related-context coverage, MRR
non-regression, exact episode counts, candidate bound, reranker accounting, Store
revalidation, Neo4j cleanup, and PostgreSQL cleanup all passed.

The final profile recorded zero hard-forbidden hits, scope leakage, subject violations,
ineligible-state hits, temporal violations, orphan provenance, path-budget omissions,
Store revalidation failures, and reranker membership violations. All 480 reranker
outcomes were accounted for: 432 completed and 48 legitimately `not_run`.

## Retrieval ablation

| Profile | Evidence recall@5 | Complete evidence@10 | Related context@10 | MRR | p50 / p95 ms |
|---|---:|---:|---:|---:|---:|
| independent lexical + vector | 0.871 | 0.843 | 0.646 | 0.898 | 77.6 / 92.2 |
| exact oracle graph path | 0.273 | 0.222 | 0.000 | 0.222 | 0.0 / 14.8 |
| bounded graph exploration | 0.273 | 0.222 | 1.000 | 0.222 | 0.0 / 15.5 |
| assembled exact hybrid | 0.920 | 0.903 | 0.646 | 0.898 | 175.6 / 226.3 |
| assembled exploration hybrid | 0.962 | 0.954 | 1.000 | 0.898 | 184.8 / 240.0 |
| exploration hybrid + memory reranking | **0.998** | **1.000** | **1.000** | **0.933** | 347.8 / 450.6 |

The result supports all three high-quality components rather than a single-source
story. Exact relation paths raise recall over independent lexical/vector retrieval.
Bounded exploration adds a further 4.17 percentage points of recall@5 to assembled
retrieval and takes related-context coverage to 1.000. Reorder-only memory reranking
then raises recall@5 by another 3.60 points, makes complete evidence@10 perfect, and
improves MRR by 0.034. Exploration still does not label adjacent context as answer
proof.

## Generalization by partition

| Partition | Queries | Required evidence | Recall@5 | Complete@10 | Related@10 | MRR |
|---|---:|---:|---:|---:|---:|---:|
| dev | 120 | 132 | 1.000 | 1.000 | 1.000 | 0.958 |
| sealed | 280 | 308 | 1.000 | 1.000 | 1.000 | 0.944 |
| adversarial | 80 | 88 | 0.989 | 1.000 | 1.000 | 0.853 |
| all | 480 | 528 | **0.998** | **1.000** | **1.000** | **0.933** |

The unseen sealed owners match dev recall and lose only 0.014 MRR. The adversarial
partition is harder in ordering, but still retrieves every required item by rank 10.
This makes a simple dev-only memorization explanation less plausible. It does not rule
out synthetic-template bias; future evidence still needs independently authored and
real replay corpora.

There is exactly one rank-5 miss among 528 required evidence items:
`q-u46-corrected-role`, an adversarial elliptical corrected-career query. Its confirmed
new-role memory is present at rank 10, so the query passes complete evidence@10 but
not recall@5. No parameter is changed in response to this sealed observation.

## Category observations

All ten categories reach 1.000 complete evidence@10. Nine categories also reach 1.000
recall@5; corrected facts reach 0.979 because of the single adversarial miss above.
Current residence, document facts, cross-conversation preferences, one-hop relations,
two-hop relations, exact episode counts, and related-but-insufficient no-answer cases
all have 1.000 MRR under their metric semantics. Temporary residence as-of queries
reach 1.000 recall@5 with MRR 0.927.

Subject correction remains the clearest ranking weakness: recall@5 is 1.000, but MRR
is only 0.531 because the owner's correction and a related peer claim both enter the
bounded context and the answer-bearing correction is often not first. This is not a
retrieval or isolation failure, but it is relevant to downstream token use and answer
reliability. It should be improved only on a new development corpus, not by tuning this
sealed suite.

## Interpretation and next evidence

This result validates the highest-quality retrieval stack under the frozen synthetic
contract: PostgreSQL authority, lexical and pgvector candidate discovery, typed and
bounded Graphiti relations, Store revalidation, and local whole-memory reranking. It
does not validate natural-language Planner accuracy, extraction quality, final answer
faithfulness, real-user distribution shift, concurrent multi-instance behavior, or
long-duration index consistency.

The next legitimate steps are therefore new evidence tracks rather than another tuned
run of this suite: an independently authored frozen corpus, end-to-end
message-to-memory-to-answer evaluation, and multi-instance reliability/latency tests.
This first all-partition result must remain unchanged and must not be reclassified as a
new sealed result after future code changes.
