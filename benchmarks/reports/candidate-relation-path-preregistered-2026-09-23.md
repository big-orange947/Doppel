# Candidate relation-path live ablation: pre-registration

Date: 2026-09-23

Status: pre-registered, not yet executed

Repository commit at registration: `17737a1906ca9f3ddbf04b572c7cb95735d3181c`

First-live implementation lock after the pre-live amendment below:
`36fc84459a8592ec3c4529ecff90742273226eb4`

This document fixes the first live Neo4j interpretation before any v2 result exists.
It is not a quality report and contains no substituted mock result.

## Immutable first-run inputs

- Dataset: `benchmarks/datasets/candidate-relation-path-ablation-zh-v2.json`
- Suite version: `2.0.0-draft.1`
- Canonical Pydantic payload SHA-256:
  `dea12fa561160f72cb2d8fcc4b4e467ae2e6556096724125dbd943a5036b094a`
- Serialized dataset file SHA-256:
  `e7925498c55187eaac736e3f8ffb9f2b4a8e559e551938f5ced276c107bc9f99`
- Corpus: 36 queries, 9 exact owner scopes, 19 authoritative memories,
  29 entities, and 20 rich edges.
- Runtime under test: `GraphitiRelationIndex.search_relation_paths()` through
  `build_relation_path_retrieval_plan()` and `search_relation_path_routes()`.
- Profiles: `strict_path`, `candidate_path`, and `exact_candidate_union`.

After the first live result is opened, changing the dataset, labels, alternative type
groups, confidence values, compiler, fusion rule, route limit, RRF constant, or gates
creates a later regression run. It must not be described as the pre-registered first
run. A change made while no live result exists is an amendment only when this document
records its reason and exact implementation commit first.

## Pre-live amendment: fusion and subject hardening

No v2 output existed and Docker was still unavailable when this amendment was made.
The dataset, both fingerprints, profiles, primary hypotheses, hard gates, confidence
values, and first-live output path remain unchanged. The implementation lock advances
to `36fc84459a8592ec3c4529ecff90742273226eb4` for these generic corrections:

- relation-type list order now has set semantics for route deduplication;
- one path receives at most the best candidate-mode RRF contribution, preventing
  overlapping candidate supersets from manufacturing independent support;
- duplicate rows do not consume rank, and the highest underlying graph score is kept;
- Graphiti Store revalidation now enforces trusted `subject` and `subject_id` on both
  one-hop and path candidates; unlabeled legacy records are owner-only.

These changes were driven by code inspection and unit tests, not live v2 outcomes.
The hard gates were not weakened. The first live command must use this implementation
lock (or a descendant containing documentation-only changes) to retain the
pre-registered label.

## Primary hypotheses

1. `exact_candidate_union` recovers all required evidence in the eight labeled
   ontology-drift cases; its recovery rate must be `1.0`.
2. Union evidence recall and complete-evidence rate exceed `strict_path`. The exact
   size of the gain is measured, not predeclared.
3. Widening returns at least some labeled related-but-not-required candidate noise.
   This is an expected precision cost and must be reported, not hidden or called
   answer proof.
4. A correct path returned by exact and widened routes appears once after fusion and
   retains both route modes in attribution.
5. Disconnected and three-hop candidate observations are rejected by host compilation
   before any graph route query.

## Hard gates

The first live command must exit non-zero if any of these occur:

- union misses required evidence;
- ontology-drift recovery is below `1.0`;
- a temporal or orphan-provenance forbidden memory is accepted;
- a result leaks outside the authorized exact scope;
- a fused graph path is duplicated;
- an eligible exact/candidate shared path loses dual attribution;
- observed compilation accounting differs from its fixture label;
- fixture cleanup leaves a node in any run-specific group; or
- Neo4j is unavailable.

Candidate-noise count and latency are diagnostics, not security gates. No threshold is
chosen after seeing the first result. The draft is not publication-ready regardless of
whether these development gates pass: the ontology-drift alternatives are synthetic
and hand-labeled, and the corpus is too small to claim general relation understanding.

## Cost and isolation contract

The run must report zero LLM calls, zero external HTTP calls, zero provider tokens,
and `credentials_persisted=false`. It pre-seeds disposable rich edges under unique
scope groups, reloads every hit from the authoritative Store, and cleans the fixture in
`finally`. It does not run Graphiti extraction, embedding, BM25, or model inference.

## First-run command

```powershell
$env:DOPPEL_NEO4J_PASSWORD = "<local-only password>"
.\.venv\Scripts\python.exe -m benchmarks.candidate_relation_path_ablation `
  --dataset benchmarks/datasets/candidate-relation-path-ablation-zh-v2.json `
  --output data/doppel/candidate-relation-path-ablation-first-live.json
```

The output path is intentionally new. It must not overwrite a prior report.

## Environment blocker recorded before opening results

No v2 live result existed at registration time. Docker Desktop 4.69 failed before the
engine became available. Its backend log reported an inaccessible stale
`%LOCALAPPDATA%\Docker\run\dockerInference` socket and stopped the `docker-desktop`
WSL distribution. The exact stale reparse point could not be renamed while Docker was
stopped (`ERROR 1920`); it was not deleted, WSL was not shut down, and Docker data,
containers, and volumes were not reset. `check-ablation-runtime.ps1` now recognizes
this content-free failure signature and exits early without repair.
