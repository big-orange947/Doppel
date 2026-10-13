# Episode audit: count identity already works; destructive merge gates needed repair

Starting HEAD `53af96f`. **Zero model/provider calls, zero paid tokens, no external
database/journal/index writes or Docker/GPU work.** Audit probes use fresh in-memory
fixture Stores and `plan_once` only; no production consolidation plan is executed.
Unit tests separately exercise writes/replay on their own disposable in-memory fixtures.
This is a structural audit, not recall/LongMemEval/AML scoring or independent semantics.

## Baseline findings

`PersonalMemoryQueryEngine` already aggregates distinct declared `event_key` values
over complete structural selections, rather than counting proposal records. Two
detail records sharing an event key do not necessarily mean two occurrences.
Natural-language relevance-qualified queries remain indeterminate for exact counts;
key equality does not independently verify the model's event identity interpretation.

Saved V9/V10 control 07 contains two episode drafts and one shared key; control 08
contains two episodes with different keys. Their original deterministic plans have
zero actions. This audit **does not demonstrate data loss or double counting in those
actual saved outputs**. Their failed single-enrichment rubric remains unchanged.

The destructive runner did, however, admit unsafe custom/model merge decisions.
It selects one existing canonical sentence, unions evidence references and supersedes
the sources. It cannot synthesize all complementary details. A synthetic dinner probe
selecting “I left a 25 yuan tip at that dinner.” drops “I paid 340 yuan for the dinner.”
from canonical content while scheduling replacement of both source records. Evidence
IDs or inactive sources may allow recovery, but active canonical content loses that
detail. This probe plans, never applies, that destructive operation.

The deterministic consolidator also grouped identical episode text by shared topic
without checking event identity/effective bounds. Identical descriptions of two
workshops with different keys, or one key with incompatible dates, could become a merge.

| Synthetic probe | Before: forced/custom merge | Before: deterministic | After |
| --- | --- | --- | --- |
| Same occurrence, complementary details | admitted, canonical keeps only tip sentence | no merge | forced merge rejected; details stay separate |
| Different event keys, identical text/shared topic | admitted | merge | forced merge rejected; no deterministic merge |
| Same key/text, unequal effective bounds | admitted | merge | forced merge rejected; no deterministic merge |
| Same key/content/temporal metadata, true duplicate | admitted | merge | safe merge still permitted |

Before/after audit uses the same four generic probes. No field-name/domain-specific
code or benchmark-answer matching is added to core algorithms.

## Core repair: separate grouping from replacement

Persistent episode `merge` now requires matching non-empty declared keys, identical
content apart from surrounding whitespace, and matching temporal status, revision
marker and effective-bound metadata. Matching stored bounds are compared conservatively;
equivalent timestamps written differently may stay separate. Missing identity does
not certify a duplicate. Internal punctuation is not erased: e.g. decimal values
cannot collapse through punctuation normalization. No semantic equality is inferred.

The deterministic consolidator uses the same signature to propose only these safe
episode duplicates. Different complementary details remain active. Non-episode
merge/correction/conflict policy is unchanged. Reference consolidator sees the previously
omitted `event_key`, with matching episode instructions. Both identities advance V4→V5;
use new version-bound checkpoints/caches/journals, not silent V4-cycle resumption.

The runner enforces this episode gate at planning **and execution**, before writing.
Integrity-valid legacy unsafe plans are rechecked; failure returns no committable
checkpoint and makes no further writes/transitions. Exact-safe partial/repeated plans
still replay. Previously persisted unsafe mergers are not automatically undone.

This is a conservative constraint on **destructive replacement**, not a RAG evidence
qualification gate: ordinary query hits are not removed and Reader abstention is not
forced. Complementary detail claims stay available for downstream model reasoning.

## Additive read-only event grouping

New provisional `TransientEventGroup` and `group_transient_events(view)` collect
builder-produced episode claims into an explicit event view without choosing a
canonical sentence, synthesizing text or applying any lifecycle action. Each group
contains full per-detail claims/evidence/times, not merely a pooled citation list.
Non-episode claims remain in the original view. Existing `TransientMemoryView` fields
and default Reader representation are unchanged; applications opt into this utility.

Grouping partitions scope, actor, authority, subject and subject ID. Shared declared
keys follow existing lowercased key conventions; they remain **advisory**, with
`semantic_identity_verified=False`. Unkeyed claims remain separate, not text-guessed.
Temporal metadata disagreement stays visible, never newest-wins or interval union.
Metadata equality does not prove effective time correctness. Group count is not a
certified real-world occurrence count. Host authorization/source validation still
precedes the utility; manually constructing a valid model does not grant permission.

### Saved actual output audit, no new extraction calls

Bind the unchanged prior live artifact SHA
`3932b5c5b052f675321c2693d3fe478f1581cad1acb7c1e912a486dbb456a415`, rebuild source-bound
views against the committed fixtures, and compare all claim fields before/after grouping:

| Saved control/profile | Claims | Groups | All detail/source fields preserved |
| --- | ---: | ---: | --- |
| Same picnic / V9 | 2 | 1 | yes |
| Same picnic / V10 | 2 | 1 | yes |
| Distinct visits / V9 | 2 | 2 | yes |
| Distinct visits / V10 | 2 | 2 | yes |

All eight claim snapshots match exactly in their grouped projections. This verifies
lossless grouping of these observations, not that inferred keys are semantically
correct or that the analyzer met its one-enriched-draft rubric. Do not recalculate
V9/V10 7/8 as 8/8, promote a default analyzer, or run the blocked old task cohort.

## Tests and local bindings

Twenty-five new tests cover unsafe detail/decimal/key/bound/status/revision merges,
missing identity, exact duplicate replay, execution of legacy plans, real query count
and retained detail hits, reference-model key exposure, trust-namespace grouping,
temporal disagreements, unknown identity, limits, input immutability and source retention.
New group wire fields are explicitly reviewed in the API snapshot.

Focused core/API/provider tests: **115 passed**. First full regression detected one
stale provider-boundary version assertion (expected consolidator V4 after intentional
V5 change): 1796 passed, 1 failed, 33 skipped. Update only that version expectation;
do not relax any semantic assertion. Final full rerun: **1797 passed, 33 skipped,
3 subtests passed** in 163.49s. Ruff full repository and selected core/audit Pyright
checks pass.

Ignored local artifacts (old artifacts are not overwritten):

- `data/doppel/event-consolidation-audit-before-v1.json`, SHA
  `3e434d044077dfe92aef977402a9de33bbc2badfbf06e2f714e28c73a1b5b1cb`.
- `data/doppel/event-consolidation-audit-after-v1.json`, SHA
  `c08d2d99caefadf25bb29bc8a3f27d77e76b4705a3b67899aa365b55fdf62068`.
- `data/doppel/event-grouping-saved-v1.json`, SHA
  `50e0253d31608672b0ddcd9dac6ef1df50cb39d1495e230cb5b21efe95ee274b`.

Runtime source digests are retained in artifact execution metadata; baseline probes
precede the repair. Source Stores are ephemeral fixtures, not user databases.
`uv.lock` remains the untouched pre-existing user change. No credential is read or
used by the zero-model audit. Existing deprecation warnings/skipped optional backends
are not treated as new live database validation.

## Next boundary

No additional prompt version or paid control retry. Keep raw evidence, candidate
claims and per-detail provenance available. A separately frozen small new-sample
end-to-end diagnosis can later measure whether this representation helps answering;
this audit cannot claim that gain. Source-qualified effective-time precision and
explicit revision targets remain higher-value open work than forced single-sentence
enrichment. Default V8 extraction, both failed control gates and old task scores stay
unchanged.
