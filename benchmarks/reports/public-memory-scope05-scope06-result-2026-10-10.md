# Fifth and sixth highest-config development results

Plans were committed before paid execution (`96555f0`, `4b8a7fd`). Algorithms,
Reader V2, question/reference text, caches, Store and reserved histories were not
modified. These are two more already-opened source-order development questions,
not independent LongMemEval/AML scores or evidence of general recall 1.0.
Earlier count/advice failures and judge disagreements remain unchanged.

## Results and attribution

| History | Task answer | Annotated turns/sessions | Legal citations | Execution |
| --- | --- | --- | ---: | --- |
| Fifth, `gpt4_d9af6064` | Correct: router before thermostat | 2/2, 2/2 | 4 | review_required |
| Sixth, `d52b4f67` | Correct: Grand Ballroom | 1/1, 1/1 | 2 | completed_within_contract |

Both source-anchored citation judges report supported answers and no citation
contradiction; quote checks pass. These same-model judgments are not independent
semantic verification. Both runs have zero source failures, no reranker input
truncation and unchanged authoritative Store/vector/selected graph snapshots.

Fifth: the original statements give router acquisition on January 15 and thermostat
setup on February 10. Reader explicitly distinguishes acquisition from setup and
uses the owner's improved Wi-Fi statement as an inference that the router was
operating. Task judge accepts the ordering; Reader reports a 26-day difference.
English question is answered in Chinese: language following still fails despite
the unchanged general instruction. This is a real limitation, not silently fixed.
One open governance marker on `internet.speed-issue` remains unclassified and
review-required; its semantic validity is not independently established.

Fifth's natural plan is unbounded lookup. The declared question reference stays
`2023-03-28T01:25:00Z`; host-authorized supplied-history horizon is
`2023-03-28T22:56:00Z` (534 turns, 485 later than reference). Relevant thermostat
knowledge was observed after the reference but before the horizon. This is the
declared noncausal provided-history evaluation, not causal future knowledge.
20 whole context items, 22737 UTF-8 bytes; memory/raw/backing candidates 20/20/19;
195 CUDA-scored pairs, none truncated.

One exploration promotes 20 paths and assembly retains 18 relation paths; no exact
typed-path searches. Graph participation is real, but the thermostat memory is
already base rank 1 and router memories base ranks 3/4. A high-ranking exploration
connects thermostat through the owner to an unrelated headphone purchase. Such
shared-owner connectivity is not task-specific multi-hop reasoning. The path
decision remains `abstain`, while paths are supplied as contextual evidence with
unassessed answer support. No isolated graph uplift is demonstrated by this answer.

Sixth: Reader answers in English and cites an extracted wedding fact and original
owner message. Question reference/horizon `2023-05-30T23:57:00Z`; latest supplied
observation `2023-05-29T17:49:00Z`, 479 turns all before reference. One typed-path
and one exploratory graph search yield zero promoted paths. Memory/vector/raw/
source evidence answers the question; no graph uplift or observation-clock uplift
claim. 20 whole items, 20323 UTF-8 bytes; memory/raw/backing candidates 20/20/21;
166 CUDA-scored pairs, none truncated. No unclassified execution warnings.

## Cost and source preparation

| Stage | Fifth calls/tokens | Sixth calls/tokens |
| --- | ---: | ---: |
| Source graph authoring | 862 / 3594348 | 683 / 2866914 |
| Source-name schema | 7 / 15308 | 5 / 9745 |
| Natural Planner | 2 / 25302 | 2 / 17472 |
| Reader | 1 / 6200 | 1 / 5515 |
| Task judge | 1 / 566 | 1 / 398 |
| Citation judge | 1 / 8236 | 1 / 7501 |
| Total | 874 / 3649960 | 693 / 2907545 |

Zero failed/interrupted requests or missing usage in these settled ledgers; no
retries. Tokens are provider-reported, not exact billing. Full-history graph
authoring dominates this workload's costs; highest configuration is not a
demonstration of cost efficiency. Fifth has 208 projections (133 rich/75 fallback),
216 distinct rich edges, 158 types and three missing-target warnings retained.
Sixth has 164 projections (100 rich/64 fallback), 182 per-projection rich links,
107 types. Sixth terminal output was truncated, so zero extractor warnings cannot
be certified. Completion/provenance is not proof of perfect semantic extraction.
Six complete history graphs contain 1206 projections; this is preparation coverage,
not six passed questions. Seventh authoring proceeds under its separate freeze.

## Immutable replay and receipts

Both empty-key replays use the existing retrieval checkpoint and hit three
downstream caches, with zero new requests. Plan, retrieval, context, packing,
Reader, both judgments and evidence scores are byte-equivalent after canonical
serialization. Not a fresh natural-planner/GPU or model-stability measurement.

- Fifth live: `data/doppel/public-memory-next-query-scope05-live-v1.json`, SHA-256
  `22a32f488c80983a179a57c3ada5d459bad2d80149a9e0e4ebb7a799ea537cd7`.
- Fifth replay: `data/doppel/public-memory-next-query-scope05-replay-v1.json`, SHA-256
  `9d31b44f51212b4bb77d3cc0fa04461e3c796dc7d205d38d2015889ca6668f8f`.
- Sixth live: `data/doppel/public-memory-next-query-scope06-live-v1.json`, SHA-256
  `1b7acbd9ac281bc90d48da8408f66afcf1a83ac72e3458099d937ef17a26dd04`.
- Sixth replay: `data/doppel/public-memory-next-query-scope06-replay-v1.json`, SHA-256
  `b0c590c639f108518bd628f85a9699057ba4b9395fe4b2c290a90bc9e2ddc1f0`.

No new production changes in this round. Full regression rerun: **1501 passed,
33 skipped, three subtests passed**, one existing Graphiti/Pydantic deprecation
warning, 169.14 seconds. Ruff passes. User-modified `uv.lock` remains unstaged.
Next development targets remain generic Reader task/inference behavior, language
following, governance relevance and graph incremental value; any changed profile
needs independent controls and a new freeze, not rules for these opened questions.
