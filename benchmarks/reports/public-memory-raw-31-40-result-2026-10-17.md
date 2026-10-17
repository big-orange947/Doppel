# New ten-history continuation: packing gain does not generalize uniformly

The fixed prospective ordinals31–40 completed in one run: ten full LongMemEval-S
histories /5103 raw messages /three retrieval profiles /two packing policies.
The previously observed hybrid-reranked skip-to-fit coverage26/27 does **not**
repeat here: new-question coverage is10/15 after either packer. Keep this result;
no tuning, replacement questions or new rule was introduced after evaluation.

## Primary new-history results

Nine answerable questions have15 annotated turns; one predeclared negative is
retained separately. Candidate window80, return20, same24,000-byte whole-item
context budget. All scores are evidence-turn coverage, not QA correctness.

| Fixed profile | Candidate /15 | Top5 /15 | Top20 /15 | Prefix packed /15 | Skip-to-fit packed /15 | All required after fit /9 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Local vector + reranker | 14 | 9 | 13 (86.7%) | 10 (66.7%) | **11 (73.3%)** | 7 |
| BM25 + vector | 15 | 8 | 12 (80.0%) | 10 (66.7%) | **11 (73.3%)** | 6 |
| BM25 + vector + reranker | 15 | 10 | **14 (93.3%)** | 10 (66.7%) | 10 (66.7%) | 7 |

Fully covered questions under prefix are6/9,6/9,7/9 respectively. With skip-to-fit,
vector-reranked improves to7/9; hybrid-reranked remains7/9. A different number of
covered turns with the same fully covered question count is not contradictory.

The new diagnostic contains seven public categories; it was not used to develop
the earlier packing comparison. It is still public benchmark data, not proof of
model-unseen independence or official LongMemEval/AML performance. The preceding
twenty opened questions and these ten new histories must not be pooled and called
a single independent blind test. No new answer/abstention score exists.

## Failure-stage attribution

- `e9327a54`: vector fails to bring its one annotated turn into the candidate80.
  BM25/vector brings it in but does not retain it in final20 without reranking;
  hybrid reranking recovers it. This is actual lexical candidate/ordering value.
- `gpt4_ec93e27f`: hybrid-reranked retrieves both annotated turns but loses both
  under either packer. Unreranked hybrid retains one with skip-to-fit. More
  complete retrieval does not automatically create a better bounded context.
- `gpt4_2f8be40d`: vector-reranked and hybrid-reranked each retrieve two of three
  annotated turns, then retain neither in packed context. Only three items fit:
  a16,782-byte original user message and two historical assistant replies of2772
  and2618 text bytes, plus metadata. No truncation was reported by the reranker;
  the loss is downstream context allocation, not its tokenizer cap. Unreranked
  hybrid retrieves/retains one annotated turn instead. The source message lengths
  were inspected only after evaluation; they did not guide selection or scoring.

The generic greedy skip policy preserves higher-ranked items, so it cannot evict
an early long item to make room for several later items. It improves some opened
and new cases, but does not resolve this resource-allocation problem generally.
Do not add category, entity, answer-value or question-ID rules for these failures.

## Execution, safety and cost

- Paid LLM calls0; provider tokens0; graph calls0; extraction/Planner/Reader/judge
  not run. Local models/hardware/time were used; no external-HTTP-count claim.
- Local embedding and strict CUDA reranker unchanged from the frozen plan.
  Twenty rerank operations /1600 scored pairs /zero reported truncations;
  longest query-content pair3810 tokens, below8192 cap. No stable latency claim.
- Thirty retrieval rows /sixty packing arms completed. Candidate Store checks
  2400, final attributed Store checks600; all rejection maps empty. Packed source
  records are additionally checked against Store. Raw ingestion validates roles,
  authority, source text/time and exact scope. This is normal-run integrity, not
  an adversarial security certification.
- Ten separate history receipts and all dedicated raw/vector data retained in
  `public-memory-raw-31-40-v1/`, schema `raw_next_c3e337f1cbe8`. No old schema,
  graph, cache or journal reset/deletion. No retry or second evaluation invocation.
- The historical continuation wrapper/test naming collision was corrected during
  execution as recorded in the plan. Both historical files now match a87187d
  exactly; the new raw wrapper preserves the exact frozen execution bytes.
- `uv.lock` remains untouched/unstaged. Core/defaults/models/packing algorithms
  remain unchanged. No fit policy promoted to a production default.

## Decision: prioritize evidence granularity, not more retrieval sources

Do not repeat the20-question96.3% result as expected deployment performance.
Hybrid retrieval now brings all15 annotations into candidates and14 into final20,
but whole-message context keeps only10. Adding another retrieval source or
whole-history graph authoring does not address this measured downstream loss.

The next useful implementation is an optional generic passage/span handoff for
long source messages, preserving immutable originals, source offsets, role/time
and full provenance. It must not be a special-case patch for these questions or
a compulsory Agent context manager. Freeze its generic policy before fresh tests.
For passage evaluation, **a source-turn ID match alone is insufficient**: a small
irrelevant fragment from an annotated message must not receive full answer-evidence
credit. Check actual span sufficiency and then a small paired answer run, rather
than adding another scoring-model calibration campaign. Do not silently shorten
messages and reuse the old whole-turn recall as if the metric were unchanged.

## Bindings and verification

Frozen execution commit18bbb1b; historical entry-point restoration/new raw path
commit90bbb1b. See [frozen plan and correction](public-memory-raw-31-40-plan-2026-10-17.md).
Plan fingerprint:
`93331b3a68ce2f9d7900e458b9342e6a9c4246eada2ef45c8a601b87d68b9c5a`.
Preflight SHA-256:
`ff26510896b27af26e5702a154818302c6c1db31eff79225850342c5c4419684`.
Output `data/doppel/longmemeval-raw-31-40-live-v1.json` SHA-256:
`4b11fc10f87e3e24c047b5c0108eb316f211098559c7df554604c3d46398ffcb`.

Twenty-nine targeted raw-continuation/prefix/fit tests passed, including eight
new tests. The restored historical and new entry points also pass16 tests
together. Ruff and new-file formatting pass. Full regression: **1905 passed,
33 skipped, three subtests passed** in261.07 seconds, with one existing optional
Graphiti/Pydantic deprecation warning. No QA or evaluation replay is claimed.
