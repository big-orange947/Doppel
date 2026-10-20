# Source grounding and precision guards: result and safety correction

The initial implementation/protocol was committed/pushed as **f7e8e02** before
9 paid calls. The annotation-only safety correction and zero-call follow-up
protocol were committed/pushed as **68d601a** before that follow-up. Both original
and corrected-policy artifacts are preserved, with no retroactive judgment,
threshold, control label or source change.

This is an opened source-entailment diagnosis, not new answer accuracy, blind
validation, complete LongMemEval/AML scoring or a default-promotion gate.

## What the actual reviewer caught, and what it got wrong

One fixed cross-domain/bilingual8-item batch: all4 intentionally unsupported
completions were flagged, all4 supported statements retained under the original
withhold policy. This includes a supported **decision** without asserting that
its target action completed. These are authored development controls, not an
independently calibrated reviewer or a guarantee of general8/8 performance.

Eight real windows reuse frozen extraction receipts:77 schema-valid drafts,
3 contradicted reviews,3 uncertain and71 supported. The ordinary actor/evidence
gate still quarantines6 subject/source mismatches. The3 contradicted drafts are:

| Window | Candidate | Source inspection |
| --- | --- | --- |
| 16 | “Owner upgraded their road bike's pedals …” | Unsupported completion: original says **decided to upgrade** and asks how to install |
| 16 | “Owner's road bike has Shimano Ultegra clipless pedals.” | Same underlying source/decision; also not an established installed state |
| 02 | “Owner visited Munich …” | **False positive**: owner explicitly says they visited; reviewer used another historical assistant denial |

The first2 are two bad claims from one source, not2 independent event failures.
The third review's own source quote is “I'm so glad I got to visit Munich during
that trip”, while its rationale says that another source contradicts it. This
demonstrates the difference between validating an exact quote and validating the
reviewer's reasoning: the quote is real, but does not support rejection.
The model violated per-draft source/actor reasoning despite valid output shape.

Other over-caution is visible: e.g. ownership from “my bike” was called uncertain.
Uncertain judgments were retained. No exhaustive independent entailment labels
exist for all77 drafts; do not claim reviewer precision/recall from these counts.

## Safe policy rather than another paid prompt-tuning cycle

Original experimental withhold behavior reduced71 eligible proposals to68:
2 real bad claims omitted, but also1 useful owner claim lost. That is not an
acceptable default recall tradeoff. Do not conceal it behind the8/8 controls.

The optional wrapper now defaults to **annotate**, not withhold. Applying the
exact same raw reviewer responses via a read-only parent cache gives:

- **71/71 original eligible proposals retained**, all71 with typed unverified
  annotations visible in transient claims as well as ordinary query metadata.
-65 supported,3 contradicted,3 uncertain among the retained proposals; these are
  model labels, not ground truth. All3 contradictory annotations remain visible,
  including the false one; the original bad completion text is not rewritten.
-The same6 source/subject mismatches remain quarantined by the authoritative
  miner gate. A supported review cannot elevate an agent assertion to owner fact.
-Disputed candidates remain recallable with an explicit unverified-review warning;
  they cannot certify an exact count. No Reader is forced to refuse an answer.
-No original history, prior stored memory or old result was deleted/rewritten.

Explicit experimental withhold remains available, but is not recommended as the
default. Source review remains opt-in/module-only; ordinary default extraction
does not gain an obligatory extra model request. An incorrect annotation can
still mislead downstream reasoning, so raw source/actor evidence remains vital.
This is recall safety and transparent qualification, not a complete semantic
extraction fix. Do not advertise the two completion errors as corrected facts.

## Time precision guard

The real “last week” coordinate spans7 days but is labeled day. A domain-neutral
duration sanity check now flags this mismatch. Query results preserve the claim
and original bounds/label, expose uncertainty and do not certify an exact
interval count from inconsistent precision. Day/month/year plausibility permits
one-hour DST shifts and second/microsecond closed ends; range is not forced into
a day. Tests cover short/long spans, leap February/year and DST.

This does not prove correct calendar alignment, relative-date interpretation,
event identity or completion status; passing the check is necessary plausibility
only. No entity/topic/benchmark-ID exceptions or invented replacement dates.

## Calls, replay and identities

Initial run:9 successful calls,0 retry/failure, complete usage accounting:
20292 input tokens (4096 provider-cached),7513 output, **27805 total tokens**;
78580 canonical request bytes. No new extraction, original-planner, Reader,
judge, embedding or graph calls;0 persistent source writes/reserved histories.

The initial key-free cache-only replay is byte-identical:

- Live/replay: data/doppel/source-grounding-live-v1.json and
  data/doppel/source-grounding-replay-v1.json
- SHA: 805323fdab8dcb03fe2172d0527c6fe68f25b440642ae7e1893bd7a8df8db6bf
- Frozen plan: 49eb38efa0582c83efe94dc35caaaff28d7fdddeb55cbdcd4a5c50f6c49dbb39

The annotation-only run and repeat are also key-free, cache-only and byte-identical:

- Live/replay: data/doppel/source-grounding-annotated-live-v2.json and
  data/doppel/source-grounding-annotated-replay-v2.json
- SHA: 7e3897152187c4b7c5b6479d831527f86247e0f5b581dc456ccfec0bc5229246
- Frozen plan: 5f68088922ddc7f60c0003c8ab7f2be63faf3a10599e59cfc360ccde2cef7bbd
- New reservations/calls/request bytes:0; reported_tokens=null because no new
  provider usage exists, not an unknown paid bill. Parent cache was not modified.

No new QA score exists. The uniform50 baseline stays37/50, prior small paired
grades remain unchanged, and local DeepSeek work is not an AML-compliant score.

## Verification and delivery focus

29 added tests in this turn; final full suite **2164 passed,33 skipped,3 subtests**.
Related source/time/transient/query/API suite221 passed. Ruff clean; relevant
new/changed files have0 Pyright errors. The additive transient annotation field's
wire snapshot is explicitly reviewed; older strict JSON consumers must update,
and old frozen experiments retain their Git/source pins. uv.lock was not changed
or staged by this work. One existing optional Graphiti/Pydantic deprecation
warning remains unrelated.

With only days remaining, do not spend further rounds optimizing this reviewer.
Freeze the deliverable runtime profile, keep review optional/annotation-only,
then prioritize cached fixed-cohort regression, adapter/API smoke and a concise
known-limitations/configuration handoff. Only rerun paid QA when a concrete
changed answer path warrants it; no more eager full-history extraction merely
to re-evaluate the same saved evidence. Broader independent quality validation
and reviewer hard-filter promotion remain later work.
