# Reviewer V2 result and contract-separated V3 pre-call plan

Date: 2026-10-06. Status: V2 rejected; V3 frozen before live outputs.

This is synthetic-surface reviewer development, not production memory intelligence,
Doppel retrieval quality, independent heldout evaluation or corpus acceptance.

Offline verification: 31 new dedicated tests pass; all 72 V1/V2/V3 reviewer tests
pass; full suite 914 passed, 33 skipped, three passed subtests. Ruff format/check
and Pyright pass. The existing Graphiti dependency emits one Pydantic deprecation
warning. New provider tests use fakes only; no V3 paid request has been made.

## Preserved V2 evidence

Report: `data/doppel/surface-review-calibration-v2.json`.
SHA-256: `bd85b93a76208f1ff865b30b9ada75078f52dea73009c5c4f35070a0e0788130`.
Implementation: `ee1eb6736a0c35a8689a411b49d1359c147f9b98`.
All 36 requests/reviews were valid: 32/36 correct, 15/18 defects detected,
1/18 acceptable controls falsely flagged, four unexpected issue flags, gate failed.
Usage: 36 calls; 77,373 input and 8,942 output tokens; total 86,315, no reasoning tokens.

Opened first-24 cohort: 22/24 correct, 11/12 defects detected, 1/12 false positives.
The immutable grounded V1 reference re-scored under V2 taxonomy was also 22/24
correct (10/12 defects detected, no false positives); this is not a clear overall
improvement. Additional twelve: 10/12 correct, 4/6 defects detected, no false flags.

| V2 failed control | Evidence-based diagnosis |
| --- | --- |
| 06, exclusive custody | Correctly reports overlapping exclusive intervals as temporal_mismatch, absent from V2's allowance. Taxonomy omission, not semantic blindness. |
| 17, actor/transfer chain | Falsely flags an explicitly stated intermediary adoption and subsequent sale; invents extra requirements not in the public brief. |
| 31, reversed custody roles | Reads the reverse wording but restores roles according to expected entity types instead of literal actions. True miss. |
| 34, reversed employment roles | Treats reversed employment as passive/inverted wording and copies expected roles. True miss. |

Control 15 passed through an `unnatural_language` issue, while its role observations
still repaired the reversed sentence to the declared direction. Thus its detection
does not establish correct relation-role parsing. The two new role variants reveal
why more quoted observations alone are insufficient. Four unexpected flags are
two temporal-category mismatches and two false flags on one acceptable control;
they are not four independent semantic failures.

No V2 result/cache is edited. No retrospective passing score is assigned.

## One-time taxonomy audit

Gold revision: `review-control-gold.v3`.
All 36 public inputs, private acceptability labels and allowed issue locations are
unchanged. V3 permits `temporal_mismatch` for exclusive-interval conflict as well as
the already repaired return/re-adoption category. The entire family inventory was
reviewed, not just the next failing row; no blanket allowance of all codes is added.

| Family | Contract defect dimension and category policy |
| --- | --- |
| unknown_relation_question | Supplied answer; answer_leak, not absence of a stored answer. |
| topic_is_not_truth_value | Supplied truth conclusion; answer_leak. |
| old_current_custody | Overlapping exclusive roles; relation/semantic conflict OR temporal_mismatch. Only new category allowance. |
| historical_question_after_event_ends | Requested date substitution; temporal_mismatch or semantic_drift. |
| exact_interval_boundary | Changed validity boundary; temporal_mismatch or semantic_drift. |
| issuable_document_subtype | Wrong document subtype; relation/entity/semantic mismatch. |
| edge_content_meaning | Different action, same names; relation_mismatch or semantic_drift. |
| relation_direction | Reversed endpoint roles; existing relation/entity/semantic/language categories. |
| acquisition_actor_chain | Mutually exclusive first-source identities; existing relation/entity/semantic categories. Unstated external conditions are not defects. |
| return_and_readoption_lifecycle | Explicit lifecycle contradiction; existing V2 temporal allowance retained. |
| requested_operation | Cancelled versus completed count; existing semantic/temporal categories. |
| competent_issuer_role | Violation of explicitly supplied qualification; existing relation/entity/semantic categories. |
| positive_candidate_confirmation | Candidate truth under neutral contract; answer_leak. |
| negative_candidate_confirmation | Candidate negative truth under neutral contract; answer_leak. |
| permitted_confirmation_contract | Candidate allowed; answerability declaration prohibited. Existing answer_leak/semantic categories. |
| passive_and_active_custody | Role reversal, not passive phrasing itself; existing role/language categories. |
| fronted_workplace_roles | Role reversal, not fronting itself; existing role/language categories. |
| independent_content_edge_roles | Independently reversed edge; existing role/language categories. |

The same opened V2 responses re-scored under V3 taxonomy give 33/36, still failed.
That diagnostic is shown alongside ORIGINAL 32/36 and is not a new measurement.
Any future taxonomy correction must also preserve old output and identify opened
rescoring explicitly. Positive controls still require zero flags.

Controls fingerprint:
`5edbc08f654678067230aa9c87e7be3171b1ab731c7737675edf2fb015c8ed79`.

## Architectural experiment: two independent structured requests

Protocol: `doppel.surface-review.separated.v3`.

Stage 1 sees ONLY authored memory/edge/question strings and an opaque, sorted
entity-name inventory. Original entity keys, types, briefs, intended relations and
endpoints, query intent/time/contract, baseline nonce and private gold are withheld.
Opaque refs derive from display names, not expected roles or hidden gold. The reading
nonce hashes only this filtered input. Tests prove the entire first request is
unchanged when withheld types/briefs/relations/intent/nonce are changed or the public
entity inventory order is reversed. Each call is independent, not a continuing
conversation containing a prior full-contract request.

The model records literal action frames: actor, affected participant, optional origin
and recipient, action kind, negation and temporal quote. Queries receive a literal
mode without a judgment of whether that mode is allowed. Implausible text is not
repaired into plausible text. All nonempty fields require exact coverage and their
full original quotation. Each action/participant/time quote must occur in its clause.
A named participant ref must be grounded in its supplied display name. Pronouns or
unnamed roles may be observed with empty refs, but unresolved required relation
endpoints block automatic validation rather than being guessed.

Stage 2 receives the full public contract AND the frozen, validated first reading.
The reading and aliases are hash-bound; the second schema cannot supply replacement
relation bindings or query modes. It reports grounded contract issues and query
policies. Every issue needs both an authored-text quote and a supplied-requirement
citation. This cannot prove that the rationale follows from the requirement, but
forces its provenance to be inspectable. No unstated obligations are introduced.

Host ontology adapters compare the frozen roles, not the second model's desired
roles: HELD_BY maps affected->actor; WORKS_AT maps actor->affected; ISSUED_BY maps
affected->actor, with matching action kind and positive assertion required. These
are relation-type mappings, not name, phrase, fixture-ID or query-specific rules.
The experimental adapter intentionally supports only these three types used by the
controls; unknown types require manual review. Other issue dimensions remain model
judgments, not hidden deterministic sentence checks. Production retrieval code is
unchanged. This is NOT a general-purpose production fact extractor.

First readings can still be wrong: without explicit contract hints the model may
still infer a sensible meaning instead of literal grammar. Unit tests demonstrate
that a wrong but quote-valid reading can fool the host. Separation is an experiment
to reduce anchoring, not a semantic guarantee. Existing false model flags are never
waived; distinct codes remain separate, and equivalent flags retain both sources.

## Frozen measurement, budget and next boundary

Same 36 OPENED development controls, 18 positive/18 defective; no new heldout claims.
The strict gate remains all 36 valid, correct judgments and zero unexpected flags.
No incomplete/error control is counted as a successful detection. Failed/uncertain
controls populate a local manual-review queue; a queue does NOT grant an override.
No V3-corpus acceptance, compilation, embedding, graph or retrieval execution occurs.

Default model/settings remain DeepSeek deepseek-v4-flash, json_object, disabled
thinking, temperature zero, max 1,536 completion tokens, zero retries. At most 72
new requests, two per control. Both phases share the same request-level call budget
and strict raw-output cache. If stopped BETWEEN phases, the first phase remains
cached and resumes at no charge. First-stage invalid output does not launch stage 2.
Successful HTTP JSON is retained even when later validation fails. Corrupt existing
entries are errors, not replaced by paid retries. First complete outputs are immutable.
The implementation/configuration/controls/reference are bound before calls.

V2 report, manifest/state, 36 cached envelopes, normalized readings/issues and original
scores/summary are verified read-only. V1 is also protected from new output-path
overlap. V2 historical usage is separate and never added to V3 call/token totals.

Dry-run: no reference/key read, provider construction, write or network:

```powershell
cd D:\project\Doppel
.\.venv\Scripts\python.exe -m benchmarks.surface_review_calibration_v3
```

After committing, in the process holding DOPPEL_API_KEY:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.surface_review_calibration_v3 --live --max-new-calls 72
```

No Docker or GPU. Complete output:
`data/doppel/surface-review-calibration-v3.json`; partial progress and raw cache are
preserved. Exit 0: preliminary calibration pass; 1: complete failed experiment;
2: incomplete. Resume only an incomplete run with the same configuration/commit.
Do not rerun a complete failure until lucky.

This is a bounded architectural comparison, not a plan for unlimited prompt versions.
If it fails, preserve the diagnosis and establish explicit human-adjudication
requirements for corpus review rather than automatically adding more prompts or
lowering the gate. Any eventual human decision must be a separate, auditable artifact,
not a rewritten failed machine review. A pass only permits the next minimal corpus
repair inventory and versioned review; corpus acceptance must still be earned before
the enlarged blind retrieval evaluation is opened.
