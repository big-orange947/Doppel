# Explicit-calendar grounding live validation — 2026-09-08

This is a local regression comparison for the domain-neutral calendar grounding
layer. It is not a publication-ready benchmark or a final-answer quality claim.

## Fixed inputs

- Implementation commit: `50bf75bd329713f5fa38ce8bde1cac4aed45984d`
- Source/effective attribution follow-up: `f1b7275`
- Dataset: `personal-relation-ablation-zh-v1` v1.5, fingerprint
  `74b4ea6dd558cc113cef81272bb673eaeec64cb24187b84df2cd06e8279dd378`
- Planner input: the same hash-bound Reference Planner v12 cache used by the prior
  runtime-reranking validation; 64 valid drafts and one retained source failure
- Runtime: PostgreSQL authority, pgvector with FastEmbed
  `BAAI/bge-small-zh-v1.5` (512 dimensions), Neo4j/Graphiti rich relations, and
  local `BAAI/bge-reranker-v2-m3` relation plus memory reranking on CUDA
- Candidate fusion: `union`; memory reranking remains reorder-only after every
  authoritative engine gate
- External HTTP/LLM calls and paid tokens: zero

The before and after runs use the same dataset, source Planner report, model,
thresholds, databases, and retrieval profile. The intended product difference is the
calendar binder inserted before trusted plan construction.

## Retrieval result

| Metric | Before grounding | After grounding | Delta |
|---|---:|---:|---:|
| Recall@1 | 0.92 | 0.96 | +0.04 |
| Recall@5 | 0.94 | 0.98 | +0.04 |
| MRR | 0.93 | 0.97 | +0.04 |
| Required-evidence recall | 0.94 | 0.98 | +0.04 |
| Legacy forbidden anywhere in returned window | 24 | 24 | 0 |
| Legacy forbidden at rank 1 | 6 | 6 | 0 |
| Abstention accuracy | 0.7692 | 0.7692 | 0 |
| Ambiguity accuracy | 0.9846 | 0.9846 | 0 |
| Count accuracy | 0.9846 | 0.9846 | 0 |

Both previously time-gated misses were recovered:

- `rel-q45`: the immutable source draft supplied the correct June 2026 interval but
  contradictory `current` intent. The binder canonicalized the effective intent to
  `history`; `rel-a-violin-zhou-history` became rank 1 and the later current holder
  did not create a temporal violation.
- `rel-q54`: the immutable source draft supplied `current` and no coordinate for the
  explicit `8月20日`. Using the trusted query year produced
  `2026-08-20T12:00:00Z`; `rel-a-access-card-reception-history` became rank 1.

No object, person, relation, or benchmark query vocabulary participates in either
repair. Unit/property-style coverage uses unrelated placeholder entities and verifies
full dates, month/day, calendar months, calendar years, invalid dates, multiple-date
ambiguity, provider-coordinate preservation, historical count/list eligibility, and
relation interval forwarding.

The immutable source Planner remains responsible for its original mistakes. The
follow-up benchmark attribution change keeps `planner_failures` bound to that source
draft, evaluates `effective_plan_failures` on the plan actually used for retrieval,
and marks generic repairs with `time_grounding_recovered`. Therefore engine recovery
does not inflate reported source-LLM Planner quality.

## Safety, integrity, and cleanup

- Scope leakage: 0
- Temporal violations: 0
- Provenance failures: 0
- Inactive-record acceptance failures: 0
- Reported source LLM calls during replay: 0
- PostgreSQL public tables after cleanup: 0
- Neo4j benchmark-preseed nodes after cleanup: 0
- Both database containers remained healthy

The generated after report is
`data/doppel/relation-v12-v15-time-grounding-enabled-20260908.json`.
Its file SHA-256 is
`fe531288e751d7c0ccce90c42169dde22d0e4075f365ca0f0e94eae9a4cdb94d`;
the sidecar matches. The canonical payload hash is
`f7123eda8d1d53050e20e1647ef0febbdff5793d5c2dda72e5ad5f1381dabadf`.

Validation at the attribution follow-up commit completed with 531 tests passed, 31
skipped integration tests, and 3 subtests passed. Ruff passed over the full tree.

## Latency caveat and remaining limits

Do not use this run's p50/p95 latency as a product regression. During the run,
Windows GPU-engine counters showed `Client-Win64-Shipping` (`鸣潮`) consuming about
70% of the GPU; the device reached 99% utilization and 87°C. Two memory-reranker
requests (`rel-q02`, `rel-q06`) hit the configured 30-second timeout and correctly
fell back to baseline order. Consequently, measured latency was p50 4,429 ms and p95
30,418 ms, versus 205/939 ms in the prior uncontended treatment run. Quality on those
two cases remained correct, but a repeated warm run with an idle GPU is required for
new latency evidence.

The 65-query dataset is still draft and partly post-hoc; nDCG@5 remains unavailable
because graded relevance is incomplete. `rel-q25` remains a source Planner failure,
which caps evidence recall at 0.98 under the all-attempt denominator. Six questions
still put a legacy forbidden candidate at rank 1, and window-level forbidden evidence
is unchanged because reranking cannot delete candidates. The next evidence milestone
is a larger frozen blind held-out/adversarial set with explicit relevance judgments,
followed by repeated warm latency runs under recorded idle/concurrent load conditions.
