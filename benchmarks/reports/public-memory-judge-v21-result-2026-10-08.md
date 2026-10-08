# Judge v2.1 result: valid execution, failed development-control gate

## Outcome and scope

Starting commit `1f72a2b`; implementation and the
[bounded plan](public-memory-judge-v21-plan-2026-10-08.md) were committed as
`be49d34e35d5a16b59ab4a233181d97ea0c9000e` **before** live execution.
All six control requests completed, but the frozen gate failed on C2 and C4.
The preserved 18-row judging arm and six-row citation-order stability arm were
**not executed**. No new Reader, retrieval, ingestion, Store or index operation
was performed. This is not a memory-performance improvement or regression result.

The six unchanged controls reuse opened-question content and are development
regressions, not independent validation. Neither a passing nor a failing gate
would establish judge generalization, complete LongMemEval performance, a blind
score or an AML score. DeepSeek is diagnostic here, not an AML academic model profile.

## What changed before execution

The independent `benchmarks.public_memory_answer_judge_v21` module preserves the
v2 model and artifacts. It gives supplied-items-scoped absence reports an explicit
definition, preserves the model's commitment label and separately derives a
conflicting-premise refusal when an explicit refusal is accompanied by a
model-observed false absence claim or citation contradiction. Committed and hedged
answers cannot be escalated to refusals by this rule. `claims_scope_conflict` is
diagnostic only: it does not force citation support to `not_applicable`.

Single-record normalized text anchors are required for cited quotes; answer quotes
are also checked. Anchoring verifies text location, **not semantic entailment**.
The host's commitment composition still depends on fallible model observations.
Contradiction caps otherwise supported evidence below `supported`.

New prompt/schema/request fingerprints bind independent plans, caches and lifetime
attempt budgets. Rows require a matching control report and recompute the gate from
raw model observations. Stability requires a complete rows report and reverses only
the cited-ID array at fixed indices 1, 5, 6, 7, 9 and 11. Labels, profile names and
audit conclusions never enter the judge requests. The reference answer reaches the
judge only, not a Reader. No reference-value phrase detector determines the score.

The original control expectations, Reader v1 answers, old scores, source dataset,
audit decisions, caches, databases and reserved histories were unchanged.
The pre-existing user modification to `uv.lock` was not edited or staged.

## Six development controls

| Control | Answer match | Model commitment | Derived commitment | Citation support | Contradiction | Faithfulness | Frozen-label match |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C1: missing packed answer | incorrect | refused_unavailable | unchanged | supported | false | grounded | all five |
| C2: conditional arithmetic | correct | committed | unchanged | supported | false | grounded | commitment differs |
| C3: refusal on a contradicted premise | incorrect | refused_unavailable | refused_conflicting_premise | partially_supported | true | partly_grounded | all five |
| C4: scoped no-record answer | incorrect | refused_unavailable | unchanged | unsupported | false | grounded | support differs |
| C5: assistant recommendation | correct | committed | unchanged | supported | false | grounded | all five |
| C6: old and new temporal facts | correct | committed | unchanged | supported | false | grounded | all five |

Four of six match every frozen dimension. All six `answer_match` labels match the
control expectations; the controls intentionally include incorrect candidate
answers, so the aggregate `3/6` correct-answer field is **not** a benchmark QA score.
All outputs were valid and anchored: 10/10 citation quote anchors and 7/7
absence-claim answer anchors. There were zero invalid controls.

The unchanged gate requires all six outputs valid and fewer than two controls with
any frozen-label mismatch. Two mismatches mean **gate failed**. No expectation,
gate threshold or prompt was changed after observing the result.

### C2: a plausible classification disagreement

The candidate supplies the arithmetic result and qualifies that the unit price is
not stated directly. The model explains:

> The candidate states the requested per-mug value ($12) as a derivation, which counts as supplying the requested information rather than refusing or hedging.

It returns `committed` instead of the frozen `hedged_derivation` expectation.
Correctness, support, contradiction and faithfulness all match. This is a plausible
interpretation of commitment, not demonstrated arithmetic failure. The frozen
fine-grained taxonomy may be brittle. That does not authorize changing its expected
label after execution or counting this run as a passed gate.

### C3: deterministic composition works, not proof of smarter judging

The model identifies the missing-count assertion as false and flags a citation
contradiction, yet returns the base refusal label `refused_unavailable`. The host
escalates this to `refused_conflicting_premise` while retaining the original label.
This is the one host escalation and meets the frozen rule. The contradiction,
partial support and partial groundedness observations match expectations.

### C4: scoped absence remains unstable

Despite the explicit scoped-absence definition, the model returns
`answer_makes_factual_claims=true`. Its absence checks are true, its cited-ID list is
empty, and the host reports `claims_scope_conflict=true` rather than overwriting
support. The derived support remains `unsupported`, not the frozen
`not_applicable` expectation. Its own reason describes a lack of records **in the
supplied items**, while faithfulness is `grounded`.

This is unresolved judge/rubric alignment. The diagnostic flag makes the
disagreement visible; automatically forcing `not_applicable` here would conceal
rather than validate it.

## Calls, usage and stopping

| Arm | New-attempt cap | New calls used | Outcome |
| --- | ---: | ---: | --- |
| Controls | 6 | 6 | completed; gate failed |
| Preserved Reader v1 rows | 18 | 0 | blocked by controls gate |
| Citation-order stability | 6 | 0 | not executed |
| Cache-only controls replay | 0 | 0 | exact semantic-result replay |

Six requests succeeded; zero retries, failed requests, interrupted requests or
missing usage reports. Provider-reported usage: **10,317 input + 2,152 output =
12,469 total tokens**, including 6,528 cached input tokens, zero reasoning tokens.
Attempt/request-byte limits were enforced; exact billing and a hard total-token
cap are not claimed. The prior v2 round remains separately recorded at six calls
and 10,620 tokens; v2 plus v2.1 controls total 12 calls and 23,089 reported tokens,
not project-wide usage. Old costs are not refunded or reset by the new identity.

Following the frozen stop condition, no v2.2 prompt revision, retry or additional
paid execution was attempted.

## Reproduction and provenance

Plan fingerprint:
`0b2f46a60e64efd1961c8d4e4c755d69f3be840911e418d333db0434fc97df81`.

Model/config: `deepseek-v4-flash`, `https://api.deepseek.com`, `json_object`,
temperature 0, thinking disabled, 3,072 maximum completion tokens, 120-second
timeout. The live CLI reads `DEEPSEEK_API_KEY` from the environment. No key is
included in requests persisted to caches, reports or documentation.

| Ignored local artifact | SHA-256 |
| --- | --- |
| `data/doppel/longmemeval-judge-v21-preflight-controls-frozen-v1.json` | `cbbf512c6480ae4e3c9adc2b3b78bf9538c75f8fd49b9d810e4837e5a4d47957` |
| `data/doppel/longmemeval-judge-v21-controls-v1.json` | `e3031a9c66546164ce19a868cf9f020c121c56781bc185352f078296b48cda57` |
| `data/doppel/longmemeval-judge-v21-controls-replay-v1.json` | `75dd540d72c46d6799825ed66d5d8cb537773355104fe0cdecaabdccaf18620d` |

New run directory: `data/doppel/public-memory-judge-v21-controls-v1`.
The preflight before and after the implementation commit has the same plan/hash.
The live report records `be49d34` and only `uv.lock` as tracked-dirty.

| Preserved source | SHA-256 |
| --- | --- |
| v2.1 module at live execution | `bd4852e0999de0f31d48ebd5aaf6e6cc2ba3c47e857c185f6fb42113708817b6` |
| unchanged v2 module | `67d6c531875fa472c242c13f682457cc2db686cc1eb8c46f921e4e8761198885` |
| unchanged development controls | `753ee1cd3f2f7b6fbd3647e3045bdf2f9aad38455655b90974dc9bde03752963` |
| Reader v1 result | `ba005911d5639394ea473dcc1a52d8711c036a74f7fdd67079ef14c22cedbdbd` |
| Retrieval comparison | `a152356232524db418bcdcc9b6104f9ce90c8d94627338effd379440e7195ae7` |
| Prior v2 controls result | `aa05f09687809523620359c4f2abee33f710860997ea06c50243b99416996a48` |
| Audit decisions | `5ae0c8b940b8c58ad7fb5b84b22b049e86d30841837d7220c2cca5b619752ba1` |
| user-owned `uv.lock` | `91ffbe400cd5e2e2810caa3bca074dae3f08e1ea74573283016f79615512e249` |

A separate-process replay removed the API-key environment variable, used
`--live --cache-only`, hit all six cached requests and made **zero new calls**.
Model outputs, derived labels, metrics and gate match exactly. Live/replay file
hashes differ because execution/cache metadata differ. Both exit 1 for the failed
semantic gate, not a transport/runtime error; cumulative ledger attempts remain six.

A real rows preflight using the failed control report exited 1, created neither a
rows output nor a rows run directory, and made no provider request. The guard does
not accept a manually changed gate boolean: it recomputes labels and expectations.

## Verification

- 20 new offline tests: blinded payloads, taxonomy, text anchoring, plan/request
  binding, tampered control reports, fixed budgets, no retries, cache replay,
  redacted failures, unknown usage accounting and citation-order-only stability.
- Final full suite: **1,224 passed, 33 skipped, 3 subtests passed**. One upstream
  Graphiti/Pydantic class-config deprecation warning; skips are not live validation.
- Repository Ruff lint passed; new Python files pass Ruff formatting checks.
- Pyright with the workspace interpreter: zero errors and zero warnings.
- Old artifact hashes and user-owned `uv.lock` were rechecked unchanged.

## Next decision, not implemented in this round

Stop tuning prompts to make six opened controls match every auxiliary taxonomy
label. A fresh, explicitly frozen evaluation should separate primary answer
correctness and evidence contradictions from disputed commitment/scope categories,
record disagreements and use auditable review for affected rows rather than quietly
overriding model outputs. This would be a new measurement protocol, not a
retroactive pass for v2.1.

Then return to the actual Reader, context-packing and memory-capability questions,
followed by unopened histories. The previous opened-row audit remains **13/18 under
its lenient derivation criterion, 9/18 under its strict sensitivity reading**;
this round produced no new score for those rows and selected no retrieval profile.
No public benchmark or AML performance claim follows from these controls.
