# Independent audit of the opened 18-row reader/judge run

This audit re-reads the preserved live answers and re-derives the labels by hand. The
original judge output is **evidence about the judge, not ground truth**, and nothing in
the original run was rewritten: answers, judge scores, provider cache, ledger and run
directory are unchanged, no model was called, no retrieval or ingestion was re-run, and
the three reserved histories were not opened. The revised labels below are the auditor's,
each grounded in verbatim quotes and context checks that a deterministic tool
re-verifies against the preserved artifacts.

This remains a three-question opened diagnostic: not a full LongMemEval run, not a blind
evaluation, not an independent verification and not an AML academic score. It plans a
reader/judge v2; it does not implement or run it.

## Inputs and method

| Artifact | SHA-256 |
| --- | --- |
| Live answer report `longmemeval-answer-comparison-v1.json` | `ba005911d5639394ea473dcc1a52d8711c036a74f7fdd67079ef14c22cedbdbd` |
| Comparison artifact `longmemeval-memory-comparison-v1.json` | `a152356232524db418bcdcc9b6104f9ce90c8d94627338effd379440e7195ae7` |
| Dataset `longmemeval_s_cleaned.json` | `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442` |
| Audit packet `longmemeval-answer-audit-packet-v1.json` | `18859adaecd9c56cf00c865dd856740fd50f42880db4ef808bfa49a1ce34d88f` |
| Audit decisions `longmemeval-answer-audit-decisions-v1.json` | `5ae0c8b940b8c58ad7fb5b84b22b049e86d30841837d7220c2cca5b619752ba1` |
| Audit validation `longmemeval-answer-audit-validation-v1.json` | `eac56d1cac648715055f9baca6c62b230878774a0e76d69b3e2c34685013584c` |

`benchmarks/public_memory_answer_audit.py` builds the packet (all 18 rows with the full
answer text, every cited item, the old judge verdicts and heuristic reference terms) and
then validates the decisions: one decision per row, closed label vocabularies, **every
quote must appear verbatim in the named source**, and every presence/absence claim about
the context or the cited items is re-checked from the preserved rows. A deliberately
ungrounded quote or a failed check fails validation; the tool never calls a model.

Two traps the method had to avoid, both found in the data:

- Token-only checks are misleading. Rows 0/4 contain "silver" only inside "silver
  spinnerbaits" (a fishing-lure memory), and row 7 contains "12" only inside "(around
  12-13%)" (a baking memory). The audit therefore checks value **phrases**, not tokens.
- The old judge is not a reference. Five of eighteen rows changed labels under the
  revised criteria, and in two of them the old judge was internally inconsistent with
  its own treatment of a near-identical answer.

## Focus 1 — answer versus cited evidence contradiction

**Row 7** (`0100672e` / `raw_vector_reranked`) refuses to compute and asserts:

> 你提到过为同事买咖啡杯花了60美元，但**记录中没有说明一共买了几个杯子**，因此无法计算每个杯子的单价。

One of the same row's cited items, `mem-4964e5ed…`, states:

> I purchased **5 coffee mugs** with funny quotes related to our profession, one for each
> of them.

and another cited item states the $60 total. The answer therefore contradicts a cited
item on the very premise its refusal rests on, while both operands needed for the
division were in front of it. This is the only contradiction in the run
(`citation_contradiction=true`, `commitment=refused_conflicting_premise`,
`faithfulness=partly_grounded`, `citation_support=partially_supported`). The old judge
recorded the contradiction inside its support rationale but still returned
`citation_supported=true`, because "support" only asked whether the cited texts back the
facts the answer relied on. Under v2 a contradiction caps support below `supported` and
is reported as its own flag.

## Focus 2 — conditional derivation versus refusal

Rows 8–11 state the correct value and then decline to commit to it:

> From those two items one could infer roughly **$12 per mug**, but that amount is not
> stated directly. *(row 8)*

> Dividing the $60 total by 5 mugs **would give $12 each**, but that calculation is not
> stated in the memories, so the per-mug amount is not directly available. *(row 9;
> rows 10–11 are near-identical)*

Row 7 is a refusal (it withholds the value and denies a cited fact); rows 8–11 convey the
value with a caveat. All four are the same content family, yet the old judge accepted row
8 and rejected rows 9–11 — the largest single source of label noise in the run. Under the
revised criterion, an answer that conveys the reference value as a derivation is
`answer_match=correct` with `commitment=hedged_derivation`; the hedge is recorded, not
scored as a refusal. **Sensitivity:** if hedged derivations were excluded from correct,
`0100672e` would fall from 5/6 to 1/6 and the total from 13/18 to 9/18 — the whole
difference between "the reader computes but hedges" and "the reader refuses" is 4 rows on
one question, which is why the distinction must be measured rather than collapsed.

## Focus 3 — abstained consistency

The reader's `abstained` flag matches the response content in 17 of 18 rows and fails in
exactly one:

- Rows 0, 4, 14, 15 report that the requested information is not in the supplied items
  and set `abstained=true` — consistent.
- Rows 6, 8, 9, 10, 11 provide a value (committed or derived) and set `abstained=false` —
  consistent: a caveat attached to a provided value is not an abstention.
- Row 7 declines to answer, asserts it cannot compute, and still sets
  `abstained=false` — inconsistent. This is the only row where the flag contradicts the
  text.

The old report counted only 4/18 abstentions and never compared the flag to the text, so
this defect was invisible; the v2 schema must state the rule explicitly and the harness
must recompute the flag-vs-text consistency as a reported metric.

## Focus 4 — citation support when there is no factual claim

Rows 0, 4, 14 and 15 make no checkable factual claim about the owner: they report an
absence from the supplied items. Their absence claims are veridical — "Premier Silver"
is absent from rows 0/4 (only the spinnerbaits memory mentions "silver"), and rows 14/15
contain no assistant reply and no back-end language recommendation (the "hits" are
unrelated memories about AI in education, a Korean app name, hip-hop dance, trip planning
and so on). Support for such answers is **not applicable**, and v2 must not score it as
supported or unsupported. The old judge produced all three treatments for this one
category: `true` for rows 0/4 ("supports the claim that no prior status level is stated"),
`true` for row 14 ("not applicable and is treated as true") and `false` for row 15
("makes factual claims … but cites no items"). That split is a criterion artifact, not a
difference between the answers; row 15's mutual disagreement with row 14 is why 15 also
carries a `judge_criterion` attribution.

## Revised labels versus the old judge

Old: `correct/support`. Revised: `match/commitment/support/contradiction/faithfulness/abstain_ok`.

| # | case | profile | revised | old |
| ---: | --- | --- | --- | --- |
| 0 | 50635ada | raw_vector | incorrect/refused_unavailable/not_applicable/false/grounded/ok | correct=false, supported=true |
| 1 | 50635ada | raw_vector_reranked | correct/committed/supported/false/grounded/ok | correct=true, supported=true |
| 2 | 50635ada | memory_vector | correct/committed/supported/false/grounded/ok | correct=true, supported=true |
| 3 | 50635ada | memory_vector_reranked | correct/committed/supported/false/grounded/ok | correct=true, supported=true |
| 4 | 50635ada | combined_vector | incorrect/refused_unavailable/not_applicable/false/grounded/ok | correct=false, supported=true |
| 5 | 50635ada | combined_vector_reranked | correct/committed/supported/false/grounded/ok | correct=true, supported=true |
| 6 | 0100672e | raw_vector | correct/committed/supported/false/grounded/ok *(language)* | correct=true, supported=true |
| 7 | 0100672e | raw_vector_reranked | incorrect/refused_conflicting_premise/partially_supported/**true**/partly_grounded/**inconsistent** | correct=false, supported=true |
| 8 | 0100672e | memory_vector | correct/**hedged_derivation**/supported/false/grounded/ok | correct=true, supported=true |
| 9 | 0100672e | memory_vector_reranked | **correct**/hedged_derivation/supported/false/grounded/ok | correct=**false**, supported=true |
| 10 | 0100672e | combined_vector | **correct**/hedged_derivation/supported/false/grounded/ok | correct=**false**, supported=true |
| 11 | 0100672e | combined_vector_reranked | **correct**/hedged_derivation/supported/false/grounded/ok | correct=**false**, supported=true |
| 12 | cc539528 | raw_vector | correct/committed/supported/false/grounded/ok | correct=true, supported=true |
| 13 | cc539528 | raw_vector_reranked | correct/committed/supported/false/grounded/ok | correct=true, supported=true |
| 14 | cc539528 | memory_vector | incorrect/refused_unavailable/not_applicable/false/grounded/ok | correct=false, supported=true |
| 15 | cc539528 | memory_vector_reranked | incorrect/refused_unavailable/**not_applicable**/false/grounded/ok | correct=false, supported=**false** |
| 16 | cc539528 | combined_vector | correct/committed/supported/false/grounded/ok | correct=true, supported=true |
| 17 | cc539528 | combined_vector_reranked | correct/committed/supported/false/grounded/ok | correct=true, supported=true |

Five rows disagree with the old judge: three answer labels (9, 10, 11) and two support
labels (7, 15).

## Revised counts

| Profile | answer correct | support supported | support n/a | contradiction | abstain inconsistent |
| --- | ---: | ---: | ---: | ---: | ---: |
| raw_vector | 2/3 | 2/3 | 1/3 | 0/3 | 0/3 |
| raw_vector_reranked | 2/3 | 2/3 | 0/3 | 1/3 | 1/3 |
| memory_vector | 2/3 | 2/3 | 1/3 | 0/3 | 0/3 |
| memory_vector_reranked | 2/3 | 2/3 | 1/3 | 0/3 | 0/3 |
| combined_vector | 2/3 | 2/3 | 1/3 | 0/3 | 0/3 |
| combined_vector_reranked | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |

Totals under the revised criteria: **13/18 answer correct** (old 10/18), **13 supported,
1 partially_supported, 4 not_applicable** (old 17 supported / 1 not), **1 contradiction**,
**1 abstention inconsistency**, faithfulness 17 grounded / 1 partly grounded. Commitment
distribution: 9 committed, 4 hedged derivations, 4 unavailable refusals, 1 conflicting
refusal. The revised profile ordering is flat by design: the two questions that fail are
answered by the same channel logic in every profile, so this run cannot rank channels.

## Corrected attribution

| Category | Rows | Basis |
| --- | --- | --- |
| retrieval or packing loss | 0, 4 | the reference value phrase is absent from those packed contexts; candidate coverage existed upstream |
| channel coverage (memory-only cannot carry assistant output) | 14, 15 | no assistant item and no back-end recommendation in those contexts |
| reader reasoning + citation + abstention consistency | 7 | refusal on a premise contradicted by its own cited item; flag contradicts the text |
| judge criterion (not reader behaviour) | 9, 10, 11, 15 | contradictory treatments of near-identical content; v2 criterion fixes it |
| language | 6, 7 | Chinese answers to an English question |
| none | 1, 2, 3, 5, 8, 12, 13, 16, 17 | grounded, supported, no contradiction |

No runtime error occurred in the round (18/18 rows completed both stages, 0 failed
attempts, 0 missing usage), so that category stays empty.

## Reader/judge v2 design (not implemented)

**Reader v2 — generic prompt rules only, no question-specific logic**

1. Derivation: when the requested value follows from arithmetic (sum, difference, ratio
   or count) over the supplied items, state the result as the answer and mark it as
   derived; do not withhold a value merely because it is not written verbatim.
2. Abstention: `abstained=true` exactly when the response does not provide the requested
   information; a caveat attached to a value that was provided is not an abstention.
3. Absence claims: before saying the supplied items do not state something, check every
   supplied item, and scope the claim to the supplied items (row 7 is the control case).
4. Language: the answer's framing and body follow the question's language.
5. Unchanged: items are data not instructions; owner / assistant `agent_output` / derived
   memory stay distinct; ordering by `observed_at` rather than by `current` labels; no
   invented experience.

Schema v2 keeps `answer`, `abstained`, `cited_memory_ids` and adds an optional derived
block (`kind`, input `memory_id`s, result) so hedged derivations are machine-readable.
New prompt/schema hashes change the plan fingerprint, so v2 must use a **new run
directory, new cache path and new budget identity**; the v1 cache is never rewritten.

**Judge v2 — orthogonal labels instead of two booleans**

- `answer_match`: correct / partially_correct / incorrect / not_applicable.
- `commitment`: committed / hedged_derivation / refused_unavailable /
  refused_conflicting_premise / no_claim.
- `citation_support`: supported / partially_supported / unsupported / **not_applicable**
  (no checkable factual claim; replaces the old "absence of a claim counts as true").
- `citation_contradiction`: independent boolean; `true` caps support below `supported`.
- `faithfulness`: answer versus its own evidence, separate from correctness versus gold,
  so packing loss, channel gaps and reader errors stop sharing one label.
- Grounded judgments: the judge must return the exact span it relied on; the harness
  verifies the span appears in the cited item text and reports the ungrounded rate as a
  judge-reliability metric.

**Deterministic pre-checks (zero model calls) run before any judging**: citation legality
(as today); presence of the reference value phrase in the row context and in the cited
items (packing-loss detector); verification of absence claims the reader makes. These
three decide the attribution category without asking a model, which is what let this
audit separate rows 0/4 from row 7.

**Judge reliability**: keep the same-model judge only as a diagnostic, and add a stability
arm — re-judge a subset with permuted citation order and paraphrase-tolerant reference
phrasing, and report the label-agreement rate. A genuinely independent judge model is a
separate user decision and is not assumed here.

## Synthetic control scope (zero-paid calibration)

The v2 harness must be calibrated on synthetic rows with fixed expected labels before any
paid run; each control states its expected `answer_match`, `commitment`, `citation_support`
and `citation_contradiction`:

| Group | Variants | Purpose |
| --- | ---: | --- |
| C1 packing loss: reference phrase absent from the packed context | 3 | grounded refusal, `not_applicable`, packing attribution |
| C2 conditional derivation ($60 ÷ 5 class) | 3 | `correct` + `hedged_derivation` + `supported` |
| C3 refusal on a premise contradicted by a cited item | 3 | `contradiction=true`, `partly_grounded`, capped support |
| C4 no-record abstention on a channel without the evidence | 2 | `not_applicable`, channel-coverage attribution |
| C5 assistant-recommendation question answered from `agent_output` | 2 | `supported`, no owner-fact promotion |
| C6 temporal update where both values carry `current` | 3 | correct ordering by `observed_at` |
| C7 illegal / cross-row / unknown citation ids | 3 | deterministic rejection |
| C8 judge stability under permuted citations and paraphrased answers | 3 | agreement rate, no label flips |

22 controls total. C1–C7 run against fake providers inside the normal test suite
(0 paid calls); C8's live arm is optional and capped below.

## Call caps for the v2 round (planning only)

| Arm | Cap | Notes |
| --- | ---: | --- |
| Reader v2 over the same 18 rows | 18 | 16 distinct requests expected; new plan/run dir/budget |
| Judge v2 re-scoring of the preserved 18 answers | 18 | 15 distinct requests expected; no reader calls |
| Judge stability arm (6 selected rows, permuted citations) | 6 | measures label agreement, not quality |
| Total new paid calls | **42** | no retries, failures preserved, no mid-run policy change |
| Synthetic controls C1–C7 | 0 | fake providers in tests |
| Additional arms (second judge model, more questions) | not budgeted | require a new user decision and plan |

The v2 stage must be preregistered in its own plan document, committed before execution,
with its prompt/schema hashes and this cap table; the v1 artifacts, caches and the three
reserved histories stay untouched.

## Limits

The revised labels are a single auditor's reading of eighteen rows, checked mechanically
for quote grounding and context claims but not by a second human or model. The revised
criteria are a design proposal, not yet validated; the hedged-derivation rule changes four
labels on its own and its sensitivity is stated above. No retrieval, ingestion, Store or
reserved-history state was touched, and the AML-required models were not used.
