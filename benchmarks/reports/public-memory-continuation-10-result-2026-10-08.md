# Ten-history continuation: completed retrieval and answer diagnostic

## Outcome and scope

The plan frozen in `3be1764` completed all **482 source chunks across ten new
public LongMemEval-S histories**, then ran all thirty raw/derived/combined
reranked Reader/Judge rows. This is the first completed comparison on these ten
histories, not a selected completed prefix. No prompt, algorithm, fixture, expected
answer or generation setting was changed after inspecting the results.

The combined channel retains all annotated source-turn provenance in its packed
contexts and improves two opened answers over raw-only. However, **the auxiliary
Judge's nine correct labels out of ten are not a validated 90% QA accuracy**:
one label accepts a refusal on an answerable question. Memory-only has two such
labels. These defects remain visible without rewriting frozen outputs or scores.

This is a small public development diagnostic, not full LongMemEval, independent
blind validation or an AML score. No production natural Planner or Graphiti
retrieval executes here. The earlier failed Judge calibration gates remain failed;
these same-model auxiliary judgments do not supersede them.

## Corpus, composition and qualification

The same ten histories selected before execution contain 5,037 raw turns. Sampling
excluded all six old exact-history groups. The three reserved histories remain
unexecuted. There are no abstention-labeled cases in this sample, so it cannot
measure unanswerable-question accuracy. Full histories are supplied; this is not
an arrival-time-cutoff experiment. Exact-history exclusion is not proof of complete
session/content independence.

The Store audit counts 1,860 derived records including two superseded records,
26 governance records, 6,921 confirmed records and two superseded records overall.
Retrieval admits 1,858 derived memories and all 5,037 raw turns. There are
**7,450 provenance checks and zero failures**, but semantic truth is not certified.
The completed extraction audit preserves 102 quarantined drafts (69
subject/source mismatches, 33 mixed-source-actor rejections) and one schema-invalid
draft. Quarantine is an authority boundary, not proof that the rejected claims
are false. Raw assistant messages remain available as `agent_output`, without
being promoted to owner facts.

All profiles use local BGE-small-zh-v1.5 (512 dimensions), local
bge-reranker-v2-m3 on CUDA, candidate cap 80, final-item cap 20 and one shared
24,000-byte serialized-context cap. Combined does not receive double the budget.
The reranker scored 2,400 pairs over thirty calls, with zero truncated pairs;
the longest pair was 2,632 tokens against the 8,192-token cap. This is not a
warm-latency or large-scale ANN benchmark. The English corpus versus Chinese
embedding model remains a confound; byte parity is not Reader-token parity.

## Retrieval measurements

Macro-averages below measure **coverage of annotated source-turn provenance**,
not independently verified answer-bearing fact recall. A derived summary may link
to a source while omitting an important detail from its text.

| Channel | Candidate @80 | Top 5 | Packed context | Questions with all annotated turns packed |
| --- | ---: | ---: | ---: | ---: |
| Raw + vector + reranker | 100.0% | 76.7% | 95.0% | 9/10 |
| Derived memory + vector + reranker | 80.0% | 80.0% | 80.0% | 8/10 |
| Combined + vector + reranker | 100.0% | 96.7% | 100.0% | 10/10 |

All thirty contexts are nonempty. Final Store revalidation performs 160 raw-only,
414 memory-only and 207 combined source checks. Candidate/index fingerprint,
scope, state and source consistency checks complete without a stopping failure.
These checks prove source binding, not relevance, semantic entailment or full
multi-tenant security coverage.

## Answers: retain the auxiliary labels, expose their defects

All thirty Reader outputs and thirty Judge outputs completed. Identical requests
deduplicated into 29 Reader calls and 29 Judge calls. All Reader outputs are
structurally valid and all citation-ID checks are legal. Quote anchoring fails on
one memory-only judgment, leaving that row unscored under the frozen contract.

| Channel | Original provisional correct labels | Unscored | Answerable refusals incorrectly labeled correct |
| --- | ---: | ---: | ---: |
| Raw | 7/10 | 0 | 0 explicitly identified in this bounded inspection |
| Derived memory | 8/9 anchored judgments | 1 | 2 |
| Combined | 9/10 | 0 | 1 |

This table is **not a corrected accuracy table**. No independent exhaustive
semantic audit has been completed. Merely subtracting the identified refusal
labels gives 6/9 for memory and 8/10 for combined, but does not validate the other
labels or resolve the ambiguous writing-count answer in the memory channel.
Text anchoring proves a quote's location, not correctness of the Judge's reasoning.

### Bounded inspection of opened failures and differences

- `gpt4_2312f94c`, device order: raw has both arrival dates in its packed context,
  but the Reader contradicts itself and declares them conflicting. Memory and
  combined correctly select the phone acquired February 20 over the laptop
  arriving February 25. This is a Reader/composition difference, not a raw
  retrieval miss. The raw Judge's `citation_contradiction=false` does not certify
  the contradictory conclusion as faithful.
- `3a704032`, plants acquired: raw packs only one of two annotated turns (50%
  turn coverage), answers one plant and misses the reference count of three.
  Memory and combined pack both annotated turns and name the three plants and
  their acquisition timing. The raw Judge's explanation uses rose pruning and a
  fern pest issue to suggest acquisition; that reasoning is not accepted as
  evidence. A full source-level temporal/count audit is still needed.
- `0e5e2d1a` and `7a8d0b71`, previous assistant information: raw and combined
  supply the requested study subject count (38) and campaign budget ($2,000).
  Memory-only lacks that assistant information and refuses. The Judge explicitly
  acknowledges the answerable gold but incorrectly treats context-justified
  refusal as QA correctness. These are channel-coverage losses, not memory wins;
  keeping raw assistant material with its original authority is useful.
- `gpt4_2f91af09`, writing count: raw mentions the possible sum 23 but hedges;
  memory does not state the requested total; combined explicitly refuses to
  calculate it. All three receive correct labels. In particular, combined's
  refusal cannot be presented as delivery of the reference answer 23. The items
  contain five short stories, seventeen poems and a named challenge piece;
  completeness, overlap and the exact three-week window need source-level audit.
  This exposes both Reader conservatism and Judge criterion conflation.
- `07741c45`, sneakers: all three disagree with the gold shoe-rack location.
  Selected sources distinguish an older under-bed fact from a later intention
  to use the closet shoe rack. No completed move is established in the inspected
  contexts. This is an unresolved reference/evidence interpretation issue, not
  sufficient justification to turn plans into current facts or add a case rule.
- `86f00804`, reading: the memory answer names the reference book. One Judge quote
  cites an `observed_at` timestamp located in metadata rather than item text;
  the frozen text-only quote contract rejects it. Preserve the unscored row.
  This is a metadata-anchoring contract issue, not a proven retrieval/answer error.

English questions still frequently receive Chinese answers despite generic
language instructions. Structural citation legality does not check this behavior,
answer/abstention consistency, arithmetic or semantic entailment.

## Execution accounting

| Stage | New calls | Input tokens | Output tokens | Total reported tokens |
| --- | ---: | ---: | ---: | ---: |
| Remaining extraction | 249 | 1,127,062 | 117,089 | 1,244,151 |
| Reader | 29 | 124,146 | 7,382 | 131,528 |
| Auxiliary Judge | 29 | 170,685 | 13,859 | 184,544 |
| This continuation | **307** | **1,421,893** | **138,330** | **1,560,223** |

The previous original failure and explicit recovery remain in lineage:
**541 calls / 2,778,634 reported tokens** overall. This continuation has no failed
provider attempt, no retry and no missing usage; 307 new calls fit the 309 cap.
Provider-reported tokens do not guarantee exact currency billing. Paid model
settings remain DeepSeek v4 flash, JSON object, temperature zero, thinking disabled,
extraction cap 8,192 / Reader 2,048 / Judge 3,072.

## Artifacts and validation

Ignored local outputs, preserved without scores being edited:

- `data/doppel/longmemeval-continuation-10-live-v1.json`, SHA-256
  `6d2bb1f48ed03830c21706afbb8b80d580dfb8ec913e7d00ad903f321e975932`.
- `data/doppel/public-memory-continuation-10-v1/ingestion-live.json`, SHA-256
  `6ebb83170ece96163f0b76189f0520a11cff8bb6959a5f39acfb1ccb8112604c`.
- `data/doppel/public-memory-continuation-10-v1/retrieval-live.json`, SHA-256
  `962d6477ea48f32e09449d3bfd79d96fc0f8395df306536e890ae57783bf491b`.
- `data/doppel/public-memory-continuation-10-v1/answers-live.json`, SHA-256
  `d07b59fecd2149a66c8764ede4e340a4bc8ba4a5e8f95abbbfb53e26b36041b3`.

Before paid execution: 75 targeted tests, full **1,294 passed / 33 skipped /
3 subtests**, whole-repository Ruff, changed-file formatting and scoped Pyright
passed. The eleven added tests cover generic completed-prefix revalidation,
source loss detection, fresh bounded continuation, accounting and stage guards;
they do not validate semantic intelligence. Original parent journal/caches remain
unchanged. The user-owned `uv.lock` is neither edited nor staged. Docker was
already healthy and was not auto-started or reset.

A separate process removed `DEEPSEEK_API_KEY` from its environment and ran
`--live --cache-only`. It completed with zero new extraction, Reader or Judge
calls and zero new extraction tokens. All 482 source chunks were revalidated.
Comparison of the complete thirty retrieval rows, Reader/Judge request identities,
outputs and structural/quote checks, and profile summaries matched exactly.
Extraction, Reader and Judge ledgers and aggregate usage matched the live report;
parent journal/cache inventories remained unchanged. Local reranking ran again,
so this proves deterministic replay on this runtime, not hardware-independent
floating-point ranking or semantic correctness.

Replay outer report `data/doppel/longmemeval-continuation-10-replay-v1.json`, SHA-256
`503d4980770ea2c76b5fd28bb2b869d043b26abd03c53f3b1f3873acdcbaf284`.

## Next bounded work

Audit the opened count/refusal and plan-versus-fact cases against source evidence,
without rewriting this run. Freeze separate QA correctness versus justified-refusal
reporting before a new measurement; use a small source-bound audit rather than
another taxonomy calibration loop. Then test a generic composition change for
answer-bearing evidence density and multi-session aggregation on development
histories, with the same shared budget and raw fallback. Do not replace the
production default based on ten questions. Only after freezing the method should
the reserved histories and a larger independently selected set be opened.
