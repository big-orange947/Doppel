# Judge v2 plan: independent re-scoring of the preserved Reader v1 answers

This freezes the Judge v2 rubric, schema, control samples and budget **before any judge
call is made**. Reader v1, every preserved answer, the original judge labels and the
provider caches are inputs and stay untouched: no retrieval, re-ranking, ingestion,
Store write or reserved-history access happens here. The judge re-scores the eighteen
preserved answers; it does not answer questions and cannot change them.

Still a three-question opened diagnostic, not a full LongMemEval run, a blind
evaluation, an independent verification or an AML academic score.

## Frozen inputs

| Input | SHA-256 |
| --- | --- |
| Preserved Reader v1 report `data/doppel/longmemeval-answer-comparison-v1.json` | `ba005911d5639394ea473dcc1a52d8711c036a74f7fdd67079ef14c22cedbdbd` |
| Comparison artifact `data/doppel/longmemeval-memory-comparison-v1.json` | `a152356232524db418bcdcc9b6104f9ce90c8d94627338effd379440e7195ae7` |
| Dataset `data/public-benchmarks/longmemeval_s_cleaned.json` | `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442` |
| Frozen controls `benchmarks/datasets/judge-v2-controls-v1.json` | `753ee1cd3f2f7b6fbd3647e3045bdf2f9aad38455655b90974dc9bde03752963` |
| Judge v2 module `benchmarks/public_memory_answer_judge_v2.py` | `67d6c531875fa472c242c13f682457cc2db686cc1eb8c46f921e4e8761198885` |
| Judge instructions / schema | `fb09d121f5707ff1723332f2c67e245b0abd2a0ff38c07ca07ebb25b0f61cb8c` / `7b2685434c7ba2eb82218d32a4b0c0a6d18c142acf013feb8a75bec3f974be4f` |

The runner refuses a different report/comparison/dataset binding, a changed controls
hash, an incomplete row set, an existing output path or a changed plan.

## What the judge sees, and what it never sees

Per case the judge receives only: the question, the benchmark reference time, the
reference answer, the candidate answer with its cited ids, and the complete supplied
context (every item with `memory_id`, `channel`, `role`, `authority`, `observed_at`,
temporal fields and text). It never receives the profile name, the original judge
labels, the audit conclusions, retrieval or coverage metrics, the reader's `abstained`
flag, or any other row's content. The reference answer is declared to the judge as
evidence for the answer match only.

Tests assert these exclusions on the serialized requests (no profile name, no old
label, no audit label, no `abstained`).

## Frozen rubric (v2)

| Dimension | Values | Rule |
| --- | --- | --- |
| `answer_match` | correct / partially_correct / incorrect / not_applicable | Lenient: paraphrase and a value conveyed through derivation or with a caveat count as correct when the same information is conveyed. `not_applicable` only when the reference itself carries no assessable answer. |
| `answer_makes_factual_claims` | boolean | True when the answer asserts any fact about the person, the world or the assistant's own earlier statements, **including a fact restated from the items**. False only when its sole assertions are about what the supplied items do or do not contain. |
| `commitment` | committed / hedged_derivation / refused_unavailable / refused_conflicting_premise / no_claim | Judged from the answer text only; the reader's flag is never shown. |
| `citation_judgments` | one entry per cited id, in order | Bound to a single record each: `support` ∈ supported / partially_supported / unsupported, plus `contradicts_answer`, a verbatim `quote` and a reason. |
| `absence_claim_checks` | list | Each claim that something is missing is quoted verbatim and checked against the **complete** supplied context. |
| `faithfulness` | grounded / partly_grounded / ungrounded | Answer versus the supplied evidence, separate from correctness against the reference. |

Code-derived row labels (the model never supplies them twice):

```text
citation_support:
  not_applicable  when answer_makes_factual_claims is false        # never counted as supported
  unsupported     when the answer makes claims and cites nothing
  supported       when every judged record is supported
  unsupported     when every judged record is unsupported
  partially_supported otherwise
citation_contradiction: any judged record with contradicts_answer = true
```

Text hits are recorded separately from the semantic judgment: a quote must appear
verbatim (whitespace-normalized, case-insensitive) **inside the one record it names** —
a quote that only exists across two records does not hit — and each absence claim quote
is checked against the answer text. Hits are reported as rates; they do not invalidate a
judgment, but an unbound citation list (missing, extra or repeated ids) does fail the row.

## Metrics, leniency and conclusion rate

- Primary lenient count: `answer_correct_lenient = answer_match == correct`.
- Reported sensitivity: `answer_correct_or_partial` (correct + partially_correct) and
  `answer_correct_strict_committed` (correct **and** committed), plus the number of
  `hedged_derivation` rows, so a reader can see the whole swing.
- `explicit_conclusion_rate` = committed / judged rows; `non_refusal_rate` =
  (committed + hedged_derivation) / judged rows.
- `citation_supported_successes` counts only `supported`; `not_applicable` is reported
  separately and is never added to it.
- `abstained_flag_consistency`: judged commitment ∈ {refused_unavailable,
  refused_conflicting_premise, no_claim} compared with the preserved reader flag.
- Per-profile breakdowns use the preserved row provenance; the judge never saw them.

No reference-answer phrase check decides whether an answer exists and none produces a
retrieval/packing attribution. Audit labels are a comparison baseline only: the result
report shows judge-versus-audit agreement and itemizes disagreements with both reasons,
without treating either side as ground truth.

## Controls and gate

Six synthetic controls (groups C1–C6) with frozen expected labels: grounded refusal that
restates a supplied fact, conditional derivation, refusal contradicting a cited record,
no-record answer with no assessable claims, assistant-recommendation attribution, and a
temporal previous/current update. They run through the same request builder and rubric.

Gate, frozen before the run: if any control output is invalid, or **two or more** controls
disagree with their frozen labels, the preserved-rows arm is not run. The gate is a
rubric check, not a quality score.

## Budget and artifacts

| Arm | Cap | Expected distinct requests |
| --- | ---: | ---: |
| Controls (C1–C6) | 6 | 6 |
| Preserved rows | 18 | 17 (two rows share an identical request) |
| Total new judge calls | **24** | no retries, failures preserved, no mid-run policy change |

Provider: `deepseek-v4-flash`, `json_object`, temperature 0, thinking disabled, timeout
120 s, `max_tokens` 3072 (raised from 2048 for the richer quote-bearing schema), no
automatic retries. A cache-only replay in a separate process must reproduce every label
with zero new calls and no API key.

Artifacts: preflight `data/doppel/longmemeval-judge-v2-preflight-v1.json`, controls
`…-judge-v2-controls-v1.json`, rows `…-judge-v2-rows-v1.json`, replay
`…-judge-v2-rows-replay-v1.json`, run directory `data/doppel/public-memory-judge-v2`.
Result report: `benchmarks/reports/public-memory-judge-v2-result-2026-10-07.md`.

## Verification before the paid run

Offline tests (`tests/test_public_memory_answer_judge_v2.py`) cover the request
exclusions, the preflight counts, the frozen support rule, single-record quote binding,
absence grounding, invalid-output preservation without retry, cache reuse and key-free
replay, key redaction, control loading and the gate, the sensitivity counts, and the
reporting-only audit comparison. The full repository suite, Ruff and Pyright must pass
and the plan must be committed before the live arms run.
