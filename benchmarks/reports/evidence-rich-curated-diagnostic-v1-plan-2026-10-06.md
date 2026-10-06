# Evidence-rich diagnostic subset: preregistered selection

Date: 2026-10-06. No retrieval scores have been opened at registration.

The user chose preparation and testing of a diagnostic subset after additional
semantic audit found problems missed by the original reviewer. This is explicitly
**not independent blind-corpus acceptance**. The original rejected review remains
immutable and the official compiler still requires an accepted review.

## Fixed exclusions before scores

Parent: 240 query slots, 24 owners, 4,608 background memories. Retain **208 queries**,
all owners and **every background memory, entity and edge**. Retained query text,
gold, routes, time and identities remain unchanged. No easier background subset.

Prepared locally before retrieval: 456 entities and 240 edges retained.
Selection SHA-256: `d9ebc46634047ef4023c90f04dd3440a07e10003dbab5098433e34facc07f62a`.
Corpus SHA-256: `0ef79243695aafe2d9319d94846c35a5cfe08733d526bed7b5d8af1ce0244d26`.
Corpus fingerprint: `d609b1a8ed09614c0e6915d3f0ea95027e27ee06454cf054ef49a2a1bc4b2528`.

| Query IDs | Reason |
| --- | --- |
| `case-blind-04-08` | Full label number requested, value absent in evidence |
| `case-blind-06-07`, `16-07`, `22-07`, `24-07` (same prefix) | Whole account requested, only account prefix present |
| `case-blind-14-06`, `16-06`, `22-06` (same prefix) | First relation hop already supplied in question, two-hop gold contract inappropriate |
| `case-blind-01-04` through `case-blind-24-04` | Whole-history count completeness and event identity audit pending |

Eight exclusions are concrete query/evidence-contract issues. Twenty-four count
queries are **unverified**, not twenty-four proven product or corpus failures.
Completed-trip claims occur in text-only background records outside the two gold
episodes. Counting only typed gold episodes would conceal this uncertainty.
Count accuracy therefore remains **not measured**, not 100%.

The remaining 208 are provisional assistant-curated diagnostics, not independently
certified semantic ground truth. All parent artifacts and repair hashes are bound
by the generated selection artifact. Texts and answers remain local; this document
publishes membership/rationale only.

## Unchanged algorithms and configuration

Primary comparison: V7 semantic-path exploration plus memory reranking versus V8
semantic-path-family exploration plus memory reranking. The existing live runner
also computes its other profiles as auxiliary observations; its V9 gate is NOT
the acceptance rule for this subset. No algorithm tuning or best-run selection.

- PostgreSQL authoritative store + pgvector, Neo4j typed graph paths.
- Cached `BAAI/bge-small-zh-v1.5`, 512 dimensions, embedding batch 32.
- Cached local `bge-reranker-v2-m3`, CUDA, sigmoid logits, batch 16, window 64.
- Oracle intent/time/subject/entity anchor planner. V7/V8 do not receive gold
  relation routes, but this still does not measure natural-language planning,
  extraction or final answer generation.
- All 208 queries, all partitions, first diagnostic execution, zero paid LLM calls.
- Weight loading is offline. No backend secrets in selection/report/git.

Compare evidence recall @5/@10, complete evidence @10, related-only evidence @10,
MRR, per-category and partition outcomes. These are observations, not a release
promotion threshold. Zero safety violations remain required for scope, subject,
authority, time, provenance, forbidden hits and Store revalidation; candidate
budget 20, no path omissions/membership changes, accounted reranking and cleanup.

The only shared-runner change is reporting correctness: absent count population
has a null score, and missing categories fail the original full-corpus gate rather
than crashing. Its requirements have not been relaxed. Production code is intact.

The dedicated `doppel-ablation-pgvector` container/database is verified before its
benchmark schema is reset. Neo4j cleanup targets generated scope groups only.
Existing unrelated nodes and Docker volumes must not be removed.

## Execution and interpretation

```powershell
.\.venv\Scripts\python.exe -m benchmarks.evidence_rich_blind_diagnostic prepare
D:\project\.doppel-eval-cu128\Scripts\python.exe -m benchmarks.evidence_rich_blind_diagnostic run
```

No DeepSeek API key is needed. Backend credentials are obtained only in memory
from the two named local benchmark containers. Preparation and successful result
output refuse overwrite. Source/code/config/selection hashes are verified before
retrieval. Do not modify the frozen selection after observing scores; subsequent
changes require a separately declared diagnostic experiment.

This opening means the diagnostic population is no longer untouched blind data.
The complete corpus remains unaccepted. Do not compare its 208-query scores with
older 480-query scores as an isolated algorithm improvement, and do not infer
real-user, extraction, natural-planner or whole-history count quality from them.

## Harness-only amendment before any complete scores

The first attempt under `9ea2e3b` failed with
`RelationPathCandidateOntologyError`. The auxiliary exact-path oracle still used
the old corpus's hardcoded `HELD_BY` / `LIVES_IN` allowlist, whereas the new host
declares 17 relation types. The normal exploration path already used the declared
ontology. Both benchmark backends cleaned up; no complete result was emitted.

The fix passes the declared host ontology to the oracle-control builder. This is
not a V7/V8 algorithm, scoring, membership or gold change. All 208 queries and
all background records remain byte-identical. The original selection is retained;
an explicitly chained `selection-v2` binds the harness correction. No complete
quality results were available when amending; this is not a best-run selection.
Amended selection SHA-256:
`67b6e7d5fd654bbfa130cab6e5eee1143d556da4e2e0333e39b00e01507d9647`.
The corpus should now be called **first completed diagnostic execution**, not an
uninterrupted first attempted execution. The partial attempt already opened some
queries; independent blind-corpus claims remain prohibited.

The ordinary project `.venv` lacks CUDA PyTorch; use the existing previously used
`.doppel-eval-cu128` environment above. No package installation or lockfile change
is required. Fixed-HEAD full regression before the amendment: 949 passed,
33 skipped, three subtests passed, one existing Graphiti deprecation warning.
