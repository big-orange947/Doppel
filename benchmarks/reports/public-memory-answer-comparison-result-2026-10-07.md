# Opened LongMemEval pilot: unified reader and judge result

This follows the [frozen plan](public-memory-answer-comparison-plan-2026-10-07.md).
The three opened diagnostic questions, the six profiles and every packed context are
the ones already produced by the retrieval comparison: nothing was re-retrieved,
re-ingested, reindexed or written to a Store, and no source was expanded. The reader
never saw a reference answer; the judge never saw the reader's profile name or the
citation-legality result. **Three opened questions are not a full LongMemEval run, a
blind evaluation, an independent verification or an AML academic score.**

## Execution

- Frozen code `a97bec3` (module, tests and plan). Live run and replay bind the same
  plan fingerprint `ffb3c0679fbb239cbe5b87bfa3422249697cbd9dff1f2dd23df4384499a5eb45`
  and the same input hashes: dataset `d6f21ea9…`, manifest `9b21d2c2…`, comparison
  `a152356232524db418bcdcc9b6104f9ce90c8d94627338effd379440e7195ae7`.
- Contract hashes: reader instructions `f75f473e…`, judge instructions `2a941b50…`,
  reader schema `f739410a…`, judge schema `489da84c…`.
- Provider (reader and judge): `deepseek-v4-flash`, `json_object`, temperature 0,
  thinking disabled, timeout 120 s, `max_tokens` 2048, no automatic retries.
- 18 logical rows → **16 distinct reader requests and 15 distinct judge requests**:
  31 new calls (16 reader + 15 judge), all succeeded, zero retries. The four
  `cc539528` raw/combined rows produced identical answers and citations and therefore
  shared one judge request.
- Replay in a separate process with `--live --cache-only` and the API-key variable
  removed: status `complete`, **0 new calls**, 16 + 15 cache hits, identical answers,
  judgments and citation checks.
- Ignored artifacts (preserved): preflight
  `data/doppel/longmemeval-answer-comparison-preflight-v1.json` (`f8e21084…`), live
  `…longmemeval-answer-comparison-v1.json` (`ba005911…`), replay
  `…longmemeval-answer-comparison-replay-v1.json` (`7eca9cd9…`); run directory
  `data/doppel/public-memory-answer-comparison-v1` with bound `plan.json`
  (`0f2c4acd…`) and 16 + 15 provider-cache entries.

## All 18 logical rows

| # | case | profile | answer correct | citations legal | citation supported | abstained | reader/judge status | note |
| ---: | --- | --- | :---: | :---: | :---: | :---: | --- | --- |
| 0 | 50635ada | raw_vector | no | yes | yes | yes | completed/completed | abstained; no Silver item in the packed context |
| 1 | 50635ada | raw_vector_reranked | yes | yes | yes | no | completed/completed | ordered 2022 Silver before 2023 Gold |
| 2 | 50635ada | memory_vector | yes | yes | yes | no | completed/completed | memory-only row also carries Silver |
| 3 | 50635ada | memory_vector_reranked | yes | yes | yes | no | completed/completed | same evidence, reranked memory order |
| 4 | 50635ada | combined_vector | no | yes | yes | yes | completed/completed | abstained; no Silver item in the packed context |
| 5 | 50635ada | combined_vector_reranked | yes | yes | yes | no | completed/completed | raw and derived both cited |
| 6 | 0100672e | raw_vector | yes | yes | yes | no | completed/completed | computed $12; answered in Chinese |
| 7 | 0100672e | raw_vector_reranked | no | yes | yes | no | completed/completed | declined to divide although it cited the 5-mug fact |
| 8 | 0100672e | memory_vector | yes | yes | yes | no | completed/completed | "one could infer roughly $12" |
| 9 | 0100672e | memory_vector_reranked | no | yes | yes | no | completed/completed | "would give $12 … not stated directly" |
| 10 | 0100672e | combined_vector | no | yes | yes | no | completed/completed | near-identical to row 8 |
| 11 | 0100672e | combined_vector_reranked | no | yes | yes | no | completed/completed | near-identical to row 8 |
| 12 | cc539528 | raw_vector | yes | yes | yes | no | completed/completed | assistant reply cited as agent_output |
| 13 | cc539528 | raw_vector_reranked | yes | yes | yes | no | completed/completed | reranked raw context |
| 14 | cc539528 | memory_vector | no | yes | yes | yes | completed/completed | memory channel holds no assistant reply (0 citations) |
| 15 | cc539528 | memory_vector_reranked | no | yes | no | yes | completed/completed | same channel gap (0 citations) |
| 16 | cc539528 | combined_vector | yes | yes | yes | no | completed/completed | duplicate request of the raw_vector context |
| 17 | cc539528 | combined_vector_reranked | yes | yes | yes | no | completed/completed | duplicate request of the reranked raw context |

Totals: answer correct **10/18**, citations legal **18/18**, citation supported
**17/18**, abstained **4/18**, reader completed 18/18, judge completed 18/18.

## Per-profile summary

| Profile | answer correct | citations legal | citation supported | abstained | reader/judge completed |
| --- | ---: | ---: | ---: | ---: | ---: |
| raw_vector | 2/3 | 3/3 | 3/3 | 1/3 | 3/3 · 3/3 |
| raw_vector_reranked | 2/3 | 3/3 | 3/3 | 0/3 | 3/3 · 3/3 |
| memory_vector | 2/3 | 3/3 | 3/3 | 1/3 | 3/3 · 3/3 |
| memory_vector_reranked | 1/3 | 3/3 | 2/3 | 1/3 | 3/3 · 3/3 |
| combined_vector | 1/3 | 3/3 | 3/3 | 1/3 | 3/3 · 3/3 |
| combined_vector_reranked | 2/3 | 3/3 | 3/3 | 0/3 | 3/3 · 3/3 |

Per case: `50635ada` 4/6, `0100672e` 2/6, `cc539528` 4/6. The denominator is the
three opened questions, not a quality estimate: one question dominates several of
these differences.

## Findings

1. **The two abstentions were a packing loss, not a reader failure.** In `50635ada`
   the reference answer is *Premier Silver*. The `raw_vector` and `combined_vector`
   packed contexts contain no Silver item at all (verified by searching the frozen
   artifact), while the candidate pool did contain both annotated sources. Both rows
   correctly reported that the context does not state it. The four profiles whose
   contexts did contain Silver all answered correctly. This is a ranking/packing
   loss already visible in the retrieval comparison, and it is now also an
   answer-level loss.
2. **Temporal handling held where evidence was packed.** Both derived memories carry
   `temporal_status=current` with null bounds, yet the reader ordered the 2022 Silver
   statement before the 2023 Gold statement by `observed_at` and answered "previous
   status was Premier Silver" — the behaviour the frozen prompt asks for. No temporal
   reasoning failure was observed in this opened set; the unhelpful `current` labels
   remain a real metadata limitation, not something this run repairs.
3. **The assistant-recommendation question behaved exactly as predicted.** The
   memory-only rows contain zero assistant items and returned 0-citation abstentions;
   the raw and combined rows cited the two assistant replies as `agent_output` and
   answered correctly. No assistant reply was promoted to an owner fact, and the
   memory channel's failure is attributed to channel coverage, not to the reader.
4. **The arithmetic question failed on reader behaviour, not retrieval.** All six
   packed contexts contain both the $60 total and the five-mug fact. Only two rows
   were judged correct; the others stated that the division "is not stated directly"
   and declined to give $12, even though the frozen prompt allows ordinary counting
   and reasoning. This is a reader-conservatism finding.
5. **Citation legality was perfect; citation support was 17/18.** All 40 citation
   mentions (16 rows) resolved inside their own row's context with no duplicates and
   no illegal ids. The single `citation_supported=false` is row 15: an abstention that
   still asserts facts ("no record of…") with no citations.
6. **The same-model judge was not fully self-consistent.** Row 8 ("one could infer
   roughly $12, but that amount is not stated directly") was judged correct while
   rows 9/10/11 said the same thing in different words and were judged incorrect;
   rows 14 and 15 are near-identical abstentions, but citation support was true for
   row 14 and false for row 15. Per-row judge labels carry roughly ±1 row of noise and
   are not independent verification.
7. **Language rule drift:** rows 6 and 7 (both `0100672e`) answered in Chinese for an
   English question despite the frozen instruction to answer in the question's
   language. Row 6 was still judged correct.

## Accounting

| Stage | New calls | Success | Cache hits (replay) | Input tokens | Output tokens | Total tokens | Missing usage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Reader | 16 | 16 | 16 | 55,194 | 2,837 | 58,031 | 0 |
| Judge | 15 | 15 | 15 | 13,521 | 2,320 | 15,841 | 0 |
| Total | 31 | 31 | 31 | 68,715 | 5,157 | 73,872 | 0 |

Usage is the provider's reported usage with the prompt-cache split included; it is
not an exact billing statement. The live invocation had zero cache hits (cold cache);
the replay had zero attempts and zero provider reachability. Budgets were 18 reader /
18 judge attempts for the plan lifetime; 16 + 15 were consumed.

## Attribution

| Row(s) | Category | Evidence |
| --- | --- | --- |
| 0, 4 | not packed (ranking loss) | Silver absent from the packed context; present in the candidate pool |
| 14, 15 | channel coverage (memory-only cannot carry assistant output) | 0 assistant items in the memory rows; correct answer exists in raw/combined |
| 7, 9, 10, 11 | reader reasoning (declined available arithmetic) | both required facts present and cited in all six contexts |
| 8 vs 9/10/11, 14 vs 15 | judge inconsistency | near-identical answers, different labels |
| 6, 7 | language rule drift | Chinese answers to an English question |
| — | runtime error | none: 18/18 rows completed both stages, 0 failed attempts |

No retrieval profile, extraction policy, prompt or core default was changed in this
stage.

## Verification

- New synthetic tests: **21 passed**, covering gold-blind reader requests, request
  payload contents, cross-row/cross-user/unknown citation rejection, assistant
  attribution, independent correctness/support, cache reuse and prompt/schema/
  generation-parameter invalidation, plan binding, resume without double charging,
  invalid output, timeout and missing usage, redaction, no-overwrite and key-free
  cache-only replay.
- Full suite: **1173 passed, 33 skipped, 3 subtests passed** against the preceding
  baseline of 1152 passed / 33 skipped; the 21 new tests account for the difference.
  Ruff lint clean; changed-file formatting clean; Pyright reports no error in the new
  files (the remaining whole-repo Pyright notices are the known missing optional
  `graphiti`/`fastembed`/`neo4j`/`asyncpg` installs in this local environment, which CI
  installs).
- Replay equality: answers, judgments, citation checks and the profile summary are
  byte-identical between the live report and the cache-only replay.

## Limits and next round

The reader and judge shared one model, one prompt each and one generation
configuration; the judge's reference answer was never shown to the reader, but no
second provider or human graded these rows. Retrieval was not re-run, the three
reserved histories were not touched, and the AML-required models
(`text-embedding-v4`, `gpt-4o-mini`) were not used anywhere in this stage.

Planned generic next-round work, from these failures only and before any new scoring
run: make simple arithmetic over supplied facts an explicit acceptable derivation in
the generic prompt; require the reader to set `abstained` consistently with its
answer text; tighten the citation-support rule so "no record" abstentions are not
scored as supported claims; and address the packing loss seen at `50635ada` in the
retrieval profile rather than in the reader. None of this is implemented here.
