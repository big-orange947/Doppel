# Attributed evidence paired diagnosis: speaker inversion remains

Frozen implementation: `c8ac7e3` on master. Follow-up to the
[preregistered plan](aml-evidence-representation-plan-2026-10-10.md).
Both fresh arms completed: **18 Reader calls, zero failures, zero Judge calls**.
The primary target was not met: the dedicated speaker-inversion control fails
with both representations. Do not promote this as a Reader fix or recall gain.

## Scope and unchanged contrast

These are nine **already opened synthetic development controls**, not LongMemEval,
reserved histories, an independent blind evaluation, official AML Answer outputs
or a competition score. No retrieval/miner/graph calls were made. The production
exporter was exercised using temporary InMemory historical-source fixtures.

`existing_structured` preserves the full existing input, including role,
authority, observation time and original text. `attributed_content` uses the actual
`AttributedEvidenceExporter.historical` output inside the declared content field.
Question, clock, source text, evidence selection/order, output schema and common
instructions are unchanged between arms. Controls and rubrics were not edited.

The common representation decoder is new relative to the preceding Reader test.
Neither arm reuses its old answers. Therefore the fresh baseline is not a clean
regression comparison against that earlier test. JSON shape, explicit speaker
labels, source IDs and length change together: this tests the whole representation,
not the isolated causal effect of an actor label.

Requested model: `deepseek-v4-flash`; **all 18 responses report `deepseek-flash`**,
finish reason `stop`. The alias is not a pinned snapshot. Settings: json_object,
temperature zero, thinking disabled, max output 1,024 tokens. Sequential alternating
arm order, durable 18-attempt cap, no retry/repair or extra calls.

## Reviewed outcomes

All 18 decisions were manually reviewed by Codex, with exact answer/source quotes
validated against the bound artifacts. This is **non-independent review**. Quote
anchoring establishes provenance, not the semantic correctness of those judgments.

| Observation | Existing structured | Attributed content |
| --- | ---: | ---: |
| Original control rubric passed | 7/9 | 8/9 |
| Answer language matches question | 2/9 | 4/9 |
| Abstention flag consistent with answer | 9/9 | 9/9 |
| Observed plan promoted into completed fact | 0 | 0 |
| Dedicated speaker-inversion control C8 | fail | fail |
| Owner vs assistant authority conflict C7 | pass | pass |

C1–C7 satisfy their original content rubrics in both arms. C8 fails in both.
C9 changes from a Chinese answer to an English answer, satisfying its explicit
language rubric in the attributed arm. Other controls' original rubrics do not all
require language matching; the separate language row must not be confused with
overall rubric correctness. One result per cell and opened controls cannot
establish a general language benefit or a population attribution-error rate.

Both arms preserve the elapsed-plan/unknown-completion distinction, the explicitly
completed event, causal-information insufficiency, counting and arithmetic
derivation. No abstention inconsistency recurred here; that is an observation,
not proof that the previous defect is fixed.

### The attribution failure is still explicit

C8 asks the owner-side question:

> 你上次建议我尝试什么运动？

The historical assistant source is:

> I suggested trying rowing on a stationary machine.

Existing structured answer:

> 你上次建议尝试划船机（室内划船机）运动。

Attributed content answer:

> 你上次建议我尝试划船机（stationary machine 上的划船运动）。

Both attribute the previous suggestion to “you,” the owner, instead of the
historical assistant. The attributed arm also explicitly reverses the recipient
with “我.” The exercise itself is retrieved correctly; attribution is not.
The source survives with `historical_assistant` and `agent_output` labels, so
their presence alone is insufficient to guarantee this Reader's interpretation.

## Accounting and representation overhead

All 18 responses have provider usage; reported reasoning tokens are zero.
Local disk-cache hits during the live execution were zero. Provider-reported
cached input is a different mechanism and must not be counted as skipped calls.

| Usage | Existing structured | Attributed content | Total |
| --- | ---: | ---: | ---: |
| Input tokens | 13,119 | 14,182 | 27,301 |
| Output tokens | 1,110 | 992 | 2,102 |
| Total tokens | 14,229 | 15,174 | 29,403 |
| Provider cached input tokens | 9,984 | 10,368 | 20,352 |
| Provider cache-miss input tokens | 3,135 | 3,814 | 6,949 |

Attributed input adds **1,063 tokens, 8.10%** over the baseline input across nine
requests, or 88–179 tokens per control. Planned serialized request bytes add
3,378 bytes, 5.36%, or 279–573 bytes per control. Output length also changes, so
the 945-token total difference is not an isolated serialization estimate.

The immediate balance observation was CNY 4.95 before and after execution.
**This does not establish zero charge**: balance settlement may lag. The observed
CNY 1 decrease stop is not an exact prepaid invoice cap. No paid Judge, graph,
embedding or reranker calls were introduced, and no hosting was purchased.

## Reproduction and validation

A separate child process with `DEEPSEEK_API_KEY` removed ran the frozen experiment
with `--live --cache-only`: all 18 local-cache hits, zero misses, zero new attempts.
Plans and result rows exactly match live execution. Ledger attempts remain 18;
different execution/accounting metadata means whole report hashes need not match.

Artifacts are in ignored `data/doppel/`; credentials and authorization headers are
not persisted. Source code, controls, old caches, old answers, production databases
and journals were not rewritten. The user's existing `uv.lock` change is untouched
and unstaged. No Docker or GPU work was required.

| Artifact | SHA-256 |
| --- | --- |
| Preflight file | `24380ed7889dee37ceae80a505e9794a7521ee96fbc8ee07122eb6b8021d4f7d` |
| Plan fingerprint | `9cb8568ec890f4ef77c130b143f520c7d2eaa6519dc745b40ffb61e850ed2d22` |
| Live file | `6e411ec2f185b27f56de217f9330d140c7eee4c75ad2b9f1d506ceb64b838da8` |
| Canonical live report identity used by review | `7a1614780ba17790ad79edbab03ecb466890ec938c19ebab7bb24eb574ab0176` |
| Key-removed replay file | `adcf13e0818cc61dd067ea485b9071c27fc4cfc582cd5296fd8ef7ae01665a69` |
| Manual review file | `d07ca7b169daed28377acf4786c3fccdf372bfeb003f9ffbdb42cf6dc64d3ce0` |
| Review validation file | `b43832cb4dc55c9e81c59d4a5b27f111a3bf8a76fe407390befbbdad66bd191e` |

Validation: **19 new offline tests**, **52 passed** with exporter tests; full
regression **1,710 passed, 33 skipped, 3 subtests passed**. Repository Ruff passed;
changed Python files pass Pyright with zero errors. A pre-existing optional
Graphiti/Pydantic class-config deprecation warning remains.

## Decision and next boundary

Keep attributed content as an **opt-in transport capability**, not an automatic
semantic repair or new default retrieval policy. This experiment neither improves
retrieval rankings nor measures the platform's own Answer model. Do not add a
rowing-specific, pronoun-specific or benchmark-answer correction to make C8 pass.

Stop this Reader-policy loop here. Return to the bounded **recall-only versus
query-time lazy analysis** diagnosis: hold candidate evidence/budgets explicit,
measure temporal/update coverage and extra cost separately, and preserve failures.
Reuse existing lawful public-data preparations before generating new histories.
Do not resume expensive S-wide eager analysis. Lazy behavior remains an explicit
competition/diagnostic profile, not a replacement for the open-source personal
memory framework's existing persistent analysis pipeline.
