# Candidate path generation: first sealed model run

Date: 2026-09-23

Status: development gate failed; corpus opened by this run

This was the first provider run over the independently frozen 18-case candidate-path
generation corpus. The implementation, dataset, thresholds, and provider limits were
committed before any result was opened. It measured topology generation only and did
not query Neo4j or claim evidence/answer quality.

## Reproducibility

- Implementation commit: `6e1e4d412cc7dae6d5d11b5cc9a74b761da91e97`
- Dataset: `benchmarks/datasets/candidate-path-generation-zh-v1.json`
- Dataset SHA-256:
  `6e961c9bc6ee2b4e96baf31a0814bfd9b9cbd8975a58db2aeb6b6e1f20f3058f`
- Relation catalog SHA-256:
  `d3d514bdf7bf30998e138083ba582b49c5796f3fa00cbcac46d6ccc3d0c3b07a`
- Local result: `data/doppel/candidate-path-generation-first-live.json`
- Result SHA-256:
  `f401e58adb4ecb10a928d66658035f2be90f9748c715b81efa4682d43ed16002`
- Provider profile: `deepseek-v4-flash`, `json_object`, thinking disabled,
  temperature zero, 1,024 maximum completion tokens, no automatic retry.
- 18 provider calls, zero cache hits, 18 cache misses, zero provider/validation
  errors. Usage was 32,025 input, 1,400 output, and 33,425 total tokens; 8,704 input
  tokens were provider-reported cached input.

## Result

| Metric | Result | Pre-registered gate | Pass |
| --- | ---: | ---: | :---: |
| Required-route recall | 0.733 | >= 0.80 | No |
| One-hop route recall | 0.818 (9/11) | >= 0.80 | Yes |
| Two-hop route recall | 0.500 (2/4) | >= 0.75 | No |
| No-path false-candidate rate | 0.000 (0/4) | <= 0.25 | Yes |
| Extra routes per case | 1.222 (22/18) | <= 0.50 | No |
| Extra types per generated route | 0.818 (27/33) | <= 1.00 | Yes |
| Invalid topology compilations | 3 | 0 | No |
| Provider/validation errors | 0 | 0 | Yes |

The overall development gate correctly failed on required-route recall, two-hop
recall, excess routes, and invalid topology compilation.

| Partition | Required recall | One-hop | Two-hop | Extra routes/case | Invalid |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dev | 1.000 (6/6) | 1.000 | n/a | 1.000 | 0 |
| Heldout | 0.667 (4/6) | 1.000 | 0.500 | 2.167 | 2 |
| Adversarial | 0.333 (1/3) | 0.333 | n/a | 0.500 | 1 |

## Diagnosis

The model reliably found the requested relation for direct one-hop wording, but often
emitted separate neighboring relations as additional routes. Examples include care
plus holding/ownership/location, purchase plus ownership/holding, and purchase venue
plus purchaser/location. These alternatives preserve recall but unnecessarily expand
the graph workload and context candidates.

The two missed two-hop cases had structural errors rather than missing ontology
labels. The borrower-anchored loan traversal bound the anchor to the wrong endpoint,
and the adoption-origin query returned only the first hop instead of completing the
path to the requested owner. Three other observations were disconnected or otherwise
ambiguous and were rejected by unchanged host compilation.

All four no-path controls returned no topology, including preference, reminder,
unsupported authorship, and an unspecified relationship. This is useful evidence that
the protocol does not indiscriminately turn every personal-memory question into a graph
walk. It does not offset the failed recall/noise gates.

## Next experiment

This corpus is now opened regression data. It may be used to diagnose and iterate on
generic protocol behavior, but later improvements need a new frozen corpus for unseen
evidence. The next changes should retain raw non-authoritative topology observations in
the local report, merge same-shape alternatives, emphasize minimal complete paths, and
re-score from the existing content-addressed cache with zero paid calls. No scenario
word list or query-specific mapping should be introduced. A real Neo4j run with
model-generated paths is deferred until topology quality clears a development gate.
