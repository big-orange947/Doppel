# Relation-path Planner V5 sealed V2 evaluation plan

Date: 2026-09-22. This document freezes the corpus, protocol, and gates before the
provider sees any V2 query. The corpus is provider-unseen rather than independently
third-party annotated: its gold was authored in-repository after the V5 architecture
was fixed, and the prompt/schema must not be changed after observing its result.

## Frozen inputs

- Dataset: `doppel-relation-path-planner-zh-v2`
- Dataset version: `2.0.0-sealed.1`
- Dataset fingerprint: `f27a04a7de38eb9346d80a8a579e17382e58ac92fdf07ebb3e7bb631156a0143`
- Dataset file SHA-256: `e02d2666b6c4f6f745999c2ca43ec6a8cd6a6c99180f3c4856cc16335b46934f`
- Relation catalog: `personal-relations-v1.json` (unchanged)
- Planner: `doppel.reference-personal-memory-relation-path-planner-v5`
- Protocol: `v5_model_observation_host_decision`
- Model: `deepseek-v4-flash`
- Provider mode: OpenAI-compatible `json_object`, temperature 0, thinking disabled
- Maximum provider calls: 48, with no retries
- Host executable bound: two relation edges
- Model execution authority: none
- Graph execution during scoring: disabled

The evaluation source is the first pushed commit containing this document and the
frozen V2 dataset. Its exact commit hash must be recorded by the generated report.

## Corpus composition

The V2 corpus contains 48 new Chinese queries and has no exact query overlap with V1:

| Category | Heldout | Adversarial | Total |
|---|---:|---:|---:|
| One hop | 12 | 4 | 16 |
| Two hop | 12 | 4 | 16 |
| No path | 12 | 4 | 16 |
| Total | 36 | 12 | 48 |

Coverage includes all 16 governed relation types, outbound/outbound,
inbound/outbound, outbound/inbound, and inbound/inbound two-step traversal, compact and
implicit compositions, shared-endpoint paths, nearby relation confusions, four exact
three-hop over-bound requests, four ambiguous requests, four unsupported predicates,
and four non-relation controls.

The corpus is frozen but not publication-ready. Forty-eight cases can validate this
protocol change; they cannot support a broad state-of-the-art claim.

## Pre-registered gates

The first run passes only if all conditions hold:

| Metric | Gate |
|---|---:|
| Complete valid execution | 48 / 48 |
| Exact path accuracy | >= 0.90 |
| Decision accuracy | >= 0.95 |
| Reason accuracy | >= 0.90 |
| Over-bound reason accuracy | 1.00 |
| Relation-type accuracy | >= 0.98 |
| Direction accuracy | >= 0.95 |
| Path recall | >= 0.95 |
| One-hop exact path accuracy | >= 0.90 |
| Two-hop exact path accuracy | >= 0.85 |
| No-path accuracy | 1.00 |
| Wrong execute count | 0 |
| Forbidden relation-type hits | 0 |
| Provider/planner errors | 0 |

Entity-string exactness remains diagnostic because equivalent mentions and omitted
trusted-owner anchors are not normalized by this draft scorer.

## First-run integrity

The runner must be invoked with `--sealed-first-run`. Before reading the API key or
opening a provider client it verifies:

1. `dataset.frozen` is true;
2. raw-output caching is enabled;
3. the dedicated cache directory contains no JSON output;
4. the explicit report path and SHA sidecar do not exist.

Any interruption after a provider sees the first query opens the corpus. A later run
must then be labeled regression evidence, even if the first report was incomplete.
Successful first-run output records that this run opened the corpus; subsequent cache
replays cannot be described as unseen evidence.

## Decision rule after opening

- Passing all gates permits a separate product-integration proposal; it does not by
  itself connect V5 to the default query engine.
- A direction/type/security failure is analyzed but does not permit prompt tuning on
  V2 followed by another “sealed” claim.
- Any V2-driven change creates an opened regression and requires a future V3 sealed
  corpus for new unseen evidence.
