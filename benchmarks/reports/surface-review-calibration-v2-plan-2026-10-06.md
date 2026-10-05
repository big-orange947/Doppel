# Surface reviewer V1 result and V2 pre-call plan

Date: 2026-10-06

Status: V1 complete and rejected; V2 development controls/protocol frozen before
any V2 live response. This is reviewer calibration, NOT Doppel retrieval quality.

Offline verification: 27 new dedicated tests pass; the final full suite has
883 passed, 33 skipped and three passed subtests. Ruff format/check and Pyright
pass for the new modules. The existing Graphiti dependency emits one Pydantic
deprecation warning. All new provider tests use fakes; no V2 paid call was made.

## Preserved V1 result

Report: `data/doppel/surface-review-calibration-v1.json`.
SHA-256: `b3d5e63310757d34ca99d13e05e4e0bb9e41d573a983ab2a6a242f64960ec838`.
Implementation: `622d424f96922a3990129772cc0f118a5c2358eb`.

| Original V1 scoring | Baseline V3 | Grounded V1 |
| --- | ---: | ---: |
| Reviewed controls | 24 | 24 |
| Positive false flags | 1/12 | 0/12 |
| Negative controls detected | 8/12 | 9/12 |
| Correct controls | 19/24 | 21/24 |
| Unexpected issue flags | 3 | 1 |

The complete gate failed. All 48 provider responses were valid, costing 54,789
tokens (51,230 input, 3,559 output). These results and their caches are unchanged.
Zero observed false positives on twelve positives is not evidence of a zero
population error rate. Neither profile accepts the rejected V3 corpus.

The candidate's two genuine missed defects were a supplied negative answer in an
open-question contract and reversed employment roles in both content and edge text.
A third strict miss was a scoring taxonomy oversight: the lifecycle contradiction
was correctly reported as `temporal_mismatch`, but V1 allowed only
`relation_mismatch`/`semantic_drift` for that family. Exact citations did not prevent
the other two misses. V1's original 21/24 is preserved, not retrospectively promoted.

## V2 contract and controls

Protocol: `doppel.surface-review.observations.v2`.
Gold taxonomy: `review-control-gold.v2`.
Controls fingerprint:
`1e04c7658cad564f3498b6f3278e374fb950912073690a2182f9cdc12d00f9d9`.

V2 uses the same first 24 public inputs. Its only gold change is allowing
`temporal_mismatch` for defective return/re-adoption lifecycle controls. V1 controls,
requests, scorer, raw responses, normalized reviews and scores are immutable.
Reports show original V1 scores AND separately labeled opened-response rescoring
under V2 taxonomy. That diagnostic rescoring gives baseline 20/24 and grounded
22/24, but is not a new experiment or a pass of the original gate.

Twelve additional development controls form six balanced pairs:

- positive supplied-answer confirmation versus an open whether-question;
- negative supplied-answer confirmation versus an open whether-question;
- a public contract that permits a confirmation question, but not an answerability declaration;
- active/passive custody descriptions preserving versus reversing roles;
- fronted workplace phrasing preserving versus reversing roles;
- correct content with an independently reversed edge versus two correct paraphrases.

There are 36 controls: 18 acceptable, 18 defective. These are hand-authored
development controls, designed after opening V1 failures, NOT independent heldout
evaluation. The additional twelve use new names/text but exercise known categories.
IDs, pair/family names, expected judgments, gold revisions and allowed issue codes
are never sent to the provider. Public-input nonces do not encode private labels.

## Structured observations, not a sentence-specific rule

The model must describe every question as neutral, containing a candidate answer,
declaring answerability, or uncertain. Separately it interprets the question's
PUBLIC semantic brief as requiring a neutral question or permitting confirmation.
Each interpretation needs exact query/brief quotes. The host compares those
observations to the public contract. A real user may absolutely ask a confirmation
question; this is an authoring-contract check, not a production query ban.

For every declared relation memory, the model independently parses both content
and edge text into semantic source/target keys with role explanations and exact
referring-expression quotes. The host checks entity membership, field provenance
and supplied declared endpoints. Token order, names, topics, control IDs and
particular phrases are not used to infer roles. Active and passive sentences can
have identical semantic direction. Clearly expressing a different relation has
an explicit `not_expressed` observation; uncertain roles cannot silently pass.

Every ordinary model issue is preserved. Host comparison flags are separately
attributed; equal surface/code flags aggregate citations/sources, while different
codes remain separate. No host check deletes a model flag or grants an acceptance
override. Missing/duplicate observation coverage, forged quotes, unknown keys or
uncertainty are errors. A valid quote proves its source, not grammatical truth:
the model can still call an answer neutral or copy declared endpoints incorrectly.
Offline tests deliberately demonstrate this limitation.

## Comparison and frozen gate

Only `observations_v2` makes new requests: one per control, at most 36. The V1
baseline and grounded responses are immutable historical references on the shared
24 controls, not newly measured profiles. The additional twelve have no new
baseline, and scores are reported separately for both cohorts and the full set.

Before any provider construction, the runner checks the V1 report's pinned SHA,
manifest/state/configuration, exact 48-request coverage, every cached response's
envelope, normalized review, original score and complete summary. Raw-file inventory
hashes are included in the new experiment binding. Parent corruption stops the
experiment without a paid replacement. Parent report/cache path overlap is refused.

Automatic correctness means a positive control has no flags; a negative has at
least one flag at an allowed location/category and no unexpected flags. This is
location/category scoring, not proof that every free-text rationale is correct.
The preliminary gate requires ALL 36 controls to have valid observations and correct
scored judgments. Errors/unrun controls are not detections; incomplete positive
coverage makes false-positive rate unavailable, not zero. Cohort summaries never
replace this full-set gate. No thresholds or expected values change after live output.

A pass permits bounded corpus repair work, not corpus acceptance. A completed
failure is preserved for diagnosis, not rerun until lucky. Next steps remain:
freeze the minimal full-family repair inventory; repair only necessary surface
contracts/text under unchanged private gold, scope, time and routes; then perform
explicitly versioned corpus review. Compilation/retrieval stays closed until actual
corpus acceptance. Do not promote development calibration to publication metrics.

## Budget and operation

Same model/settings as V1: DeepSeek `deepseek-v4-flash`, `json_object`, disabled
thinking, temperature zero, max 1,536 completion tokens, zero provider retries.
Cache/state/configuration/implementation commit are bound. Invalid existing entries
are errors, never implicit paid replacements. Raw outputs are retained even if
observation validation fails. First complete reports cannot be overwritten.
V1's historical usage is labeled separately, never added to V2 usage.

Dry-run performs no reference read, key read, provider construction, network call
or file write:

```powershell
cd D:\project\Doppel
.\.venv\Scripts\python.exe -m benchmarks.surface_review_calibration_v2
```

After committing this plan, in the PowerShell process that holds `DOPPEL_API_KEY`:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.surface_review_calibration_v2 --live --max-new-calls 36
```

No Neo4j, Docker, embeddings or GPU is used. Output:
`data/doppel/surface-review-calibration-v2.json`; an incomplete run writes only the
progress sidecar and preserved raw cache. Exit 0 means this preliminary gate passed;
1 means a complete failed experiment; 2 means incomplete. Budget interruption can
resume with the same command and configuration, without charging for cached responses.
An existing completed output must be preserved. A diagnostic cache-only replay uses
`--max-new-calls 0` and a DIFFERENT output path and cannot make a paid call.
