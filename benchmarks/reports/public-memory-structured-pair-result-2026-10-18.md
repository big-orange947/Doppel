# Opened-eight structured-memory comparison: no net task gain

**Decision: do not promote this view or claim a temporal/multi-session advantage.**
The frozen real-pipeline comparison completes8/8 pairs. Both contemporaneous
arms score6/8 with the provisional DeepSeek task judge: one gain, one regression.
These are opened development cases, not independent/official LongMemEval or AML
results. No production algorithm/default, raw evidence, graph or Store changed.

See the [pre-registered protocol](public-memory-structured-pair-plan-2026-10-18.md).
Implementation/plan commit `2f4d51f` was committed and pushed before live calls.

## Paired task outcomes

| Ordinal | Case/type | Raw | Structured | Interpretation |
| --- | --- | --- | --- | --- |
| 02 | trip ordering / temporal | correct* | incorrect | regression; both answers overcautious |
| 03 | reported MCU total / update | correct | correct | query engine itself returns no hits |
| 05 | different cuisines / multi-session | correct | correct | four relevant episodes available |
| 07 | uncle birthday / abstention | correct | correct | no invented uncle event |
| 09 | elapsed music days / temporal | correct | correct | Reader arithmetic; not engine duration computation |
| 12 | March appointments / multi-session | correct | correct | two episodes survive engine filters |
| 16 | bike events elapsed days / temporal | incorrect | correct | qualified four-day answer replaces refusal |
| 19 | December faith activities / multi-session | incorrect | incorrect | both exclude the church food drive |

By category: temporal2/3 in both arms; multi-session2/3 in both; update1/1 and
negative1/1 in both. All16 Reader outputs pass structural citation/derivation
checks. Those checks prove ID legality, not semantic entailment or arithmetic.

*Ordinal02 raw is **not an unqualified sound answer**: it says the relative
expressions imply the Southwest trip came first, but also says the order cannot
be established. The judge accepts the conveyed expected result under its frozen
qualified-answer policy. Structured supplies only refusal, hence fails. We retain
both original grades and explicitly flag raw answer inconsistency rather than
silently presenting this as a clean temporal success.

The same eight old uniform-baseline answers scored5/8; this fresh raw control is
6/8. Ordinal02 alone changes grade despite the **same request hash**. Do not
compare structured6/8 against historical5/8 and call that an improvement. A
temperature-zero hosted model and provisional same-model judge are not guaranteed
deterministic. No additional resampling or judge retuning was performed.

## What the real pipeline actually did

Analyzer V10 parsed71/71 valid draft objects. Miner accepted64 candidates,
discarded2 below confidence and quarantined5 subject/source-actor mismatches.
All accepted candidates in this particular run happen to be owner-attributed;
this does not prove arbitrary agent output is harmless. Actor gate behavior
also has offline controls. No candidate was confirmed or written to PostgreSQL.

| Ordinal | Accepted claims | Engine scanned | Engine hits | Operation / time view |
| --- | ---: | ---: | ---: | --- |
| 02 | 4 | 4 | 4 | lookup / unbounded |
| 03 | 5 | 5 | 0 | count / interval |
| 05 | 8 | 8 | 4 | count / interval |
| 07 | 19 | 19 | 15 | lookup / unbounded |
| 09 | 5 | 5 | 1 | count / unbounded |
| 12 | 9 | 9 | 2 | count / interval |
| 16 | 7 | 7 | 1 | count / unbounded |
| 19 | 7 | 7 | 0 | count / interval |

Total64 scanned,27 query hits. All six count plans return indeterminate, not
an exact total. Exported whole-history counts are independently forced to
indeterminate because a retrieved subset cannot certify the full history.
All original raw items and all accepted candidate claims remain available to
the Reader, including candidates excluded from the query engine's hit set.
Therefore a Reader success does **not** mean the engine independently solved it.

All64 candidates have null valid_from/valid_to. Dates are sometimes preserved in
claim prose or declared event keys, but no machine-readable effective interval
is supplied. This is not an argument to blindly fill validity fields with
observation times: state validity and event occurrence are different concepts.

## Concrete product gaps, not question-specific rules

1. **Event time is missing between language and execution.** Ordinal19 extracts
   all three December episodes, but they were described in January. The Planner
   correctly requests December; the engine rejects all three as
   `outside_time_interval` when no explicit effective bounds are available.
   Evidence recall and extraction succeeded; temporal execution does not consume
   the event dates still present in text/event keys. Filling a date-shaped event
   key is not a typed occurrence-time implementation.
2. **Planner quantity semantics are too narrow.** Both elapsed-day questions
   become `operation=count`, while the engine's count is event cardinality, not
   subtraction between two event dates. For ordinal16 the decision is a PLAN
   candidate while repair is an EPISODE; the `memory_types=[episode]` gate keeps
   only repair. The correct structured answer comes from the retained claims/raw
   fallback and a qualified Reader inference, not a complete selected pair.
3. **Reported aggregates and event enumeration are confused.** Ordinal03 has
   explicit aggregate observations of four and then five MCU films, classified
   as STATE. The Planner requests only EPISODE, so all five candidates are gated
   out by type. Raw fallback still conveys the latest reported five. A general
   quantity query needs to distinguish reported totals from counting episodes.
4. **Good extraction cannot solve all answer policy problems.** Ordinal19's
   food-drive episode is present in raw text and candidate claims. Both Readers
   exclude it because it is described as volunteering rather than explicitly
   faith-related, contrary to the reference's broader category. Adding graph
   edges or more history would not by itself fix this classification decision.
5. **Relative ordering and uncertainty need useful representations.** Ordinal02
   preserves “a few years ago” and “last summer”, but obtains no reusable temporal
   ordering from them. The Reader interprets lack of exact dates as inability to
   order the events. Do not patch the two locations or phrases into the benchmark
   runner. General relative/partial temporal constraints require separate design.

English questions still sometimes receive Chinese answers (nine of16 outputs),
and ordinal02 raw mixes refusal with the expected ordering. Existing Reader
language/consistency instructions are not hard guarantees. Keep this separate
from retrieval and temporal-engine claims; changing Reader now would confound
the frozen experiment.

## Cost and reproducibility

| Stage | Successful new calls | Input tokens | Output tokens | Total |
| --- | ---: | ---: | ---: | ---: |
| Analyzer | 8 | 53,421 | 6,693 | 60,114 |
| Planner | 8 | 11,072 | 1,127 | 12,199 |
| Reader | 16 | 141,876 | 4,566 | 146,442 |
| Provisional judge | 16 | 8,227 | 737 | 8,964 |
| Total | 48 | 214,596 | 13,123 | 227,719 |

Zero failed/interrupted calls, retries, missing usage, source writes and graph
calls. Provider usage is not an exact monetary bill; no price claim is inferred
from rounded balance snapshots. All new calls stay inside the frozen caps.
This is bounded query-time analysis of roughly24KB retrieved context per case,
not full115K-token-history extraction.

Structured Reader canonical requests total301,971 bytes versus225,436 raw
(+33.95%). Extra reasoning/model calls and prompt length are confounders; even
the one gain cannot be attributed uniquely to structured time reasoning.

Live artifact: `data/doppel/structured-pair-live-v1.json`; key-free cache-only
replay: `data/doppel/structured-pair-replay-v1.json`. They are **byte-identical**,
including row outputs, audit views, summaries and cumulative ledgers:

`2900fbb1020d41665ab7dbfa0a05798645cb96a01d5e7641ad52d535b750f77a`

Replay reserves zero new attempts. Reports/caches are ignored local artifacts;
no API key is persisted. Source hashes, model configs and request identities
remain bound to the preflight fingerprint in the frozen plan.

Validation: **2098 passed,33 skipped,three subtests**;9 new offline tests,
185 targeted tests; repository Ruff passes, new files formatted, new files
Pyright0 errors. Only existing optional Graphiti/Pydantic warning. Preexisting
`uv.lock` changes untouched and unstaged.

## Next implementation boundary

Do not expand to500 questions or resume eager Graphiti before repairing this
seam. Design an opt-in typed event-time representation distinct from state
validity: exact/partial/relative time, precision/uncertainty, observed anchor and
source provenance. Missing time must remain unknown, not inherit created_at as
an asserted occurrence date. Add generic synthetic controls before another live
experiment: recalled-old events, partial dates, relative ordering, decisions vs
completed actions and repeated statements of one event.

Then distinguish **reported quantity, distinct-event count, distinct-day count,
elapsed duration and ordering** in the planner/executor contract without
overloading existing exact-count behavior. Preserve uncertain candidates/raw
evidence for the host LLM rather than enforcing a wrong hard filter. These are
cross-domain operations, not film/bike/church rules. Freeze a new comparison
only after offline controls pass. This run supplies a concrete improvement
target; it does not establish that any proposed fix already improves quality.
