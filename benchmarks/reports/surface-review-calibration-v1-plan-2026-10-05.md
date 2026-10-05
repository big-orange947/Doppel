# Surface reviewer calibration V1: frozen pre-call plan

Date: 2026-10-05

Status: offline implementation verified; no live calibration result yet.

Offline verification: 14 dedicated tests and the full suite pass (856 tests,
33 skips, three subtests). Ruff and Pyright pass for the new modules. Tests use
fake providers to verify workflow only; they are not live reviewer quality scores.

Controls fingerprint:
`6bb7df9932077b198e4b365591bbd5cf65b93a91fb5b9e2b319ed09c7d5b9951`.

## Scope and independence

This experiment checks the reviewer before another blind-corpus repair. It does not
read, rewrite, compile, retrieve from, or grant acceptance to the V3 corpus. V3's
23-finding first rejection and the diagnostic audit remain unchanged.

There are 24 hand-authored development controls: twelve correct/defective pairs.
They use separate text and synthetic identities, not copied V3 owner surfaces.
They deliberately exercise the general reasoning mistakes exposed by the audit.
They are therefore NOT unseen heldout tests or proof of broad reviewer reliability.
The candidate prompt was designed with these reasoning categories in mind.

| Pair family | Correct control | Defective control |
| --- | --- | --- |
| Unknown relation question | Ask for an unrecorded buyer | Put a buyer in the question |
| Topic versus truth value | Ask whether a health condition holds | State its answer in the question |
| Old/current custody | Ended old holder, later current holder | Overlapping exclusive holders |
| Historical lookup | Ask for the contracted historical date | Substitute a different date |
| Interval boundary | Preserve the exact end boundary | Extend occupancy beyond it |
| Document subtype | Formal issuable certificate | Ordinary book substituted for the certificate |
| Content/edge meaning | Two custody paraphrases | Custody content, sale edge |
| Relation direction | Person works at organization | Reverse person and organization |
| Acquisition actors | Adoption by intermediary, later sale | Mutually exclusive sole-source acquisitions |
| Return/re-adoption | Explicit return followed by re-adoption | Deny re-adoption while asserting it |
| Query operation | Count cancelled plans as requested | Ask for completed trips instead |
| Issuer role | Issuer has the supplied signing qualification | Print-only supplier claims to issue |

Case IDs, pair/family labels, expected acceptability and allowed issue locations/codes
remain in the local scorer. Provider requests contain only the public surface brief,
authored surface, relations and review schema. A nonce is derived from public input,
not from gold labels. Each request is independent; there is no conversational
feedback teaching the model the preceding control's answer.

## Profiles

`baseline_v3` uses the frozen V2/V3 review instructions and the original
`OwnerSurfaceReview` output schema. The control input envelope follows V3's review
material; it is not a replay of the actual V3 corpus requests.

`grounded_v1` uses a separately versioned general review protocol and requires exact
source quotations on each reported issue. Citations name a supplied surface key and
field; each issue must cite its own authored surface. Missing coverage, duplicate
issues, invented quotations, unknown keys and quotations found only in a different
field are validation errors. Citation validation does not judge semantics or remove
flags: a perfectly valid quote can support a wrong conclusion, which still counts
as an error in the control scorer.

Both profiles use the same controls and configured model. This compares protocols,
not two independent model providers or an external human adjudication.

## Scoring and gate frozen before live output

A correct control requires zero issue flags. A defective control requires at least
one flag at a declared appropriate location with an allowed category; extra flags
outside that allowance prevent a correct result. Symmetric conflicts allow either
participating statement to be flagged rather than arbitrarily choosing a culprit.

Reports include positive false flags, defective controls detected, unexpected flags,
errors and unrun controls separately for each profile. When all positive controls
have not been validly reviewed, false-positive rate is unavailable (`null`), not
zero. Errors/unrun negative controls never count as successful defect detection.

The preliminary gate requires all 48 profile/control requests to produce valid
reviews and all 24 candidate judgments to be correct, with no unexpected flags.
The baseline may make semantic mistakes: these establish the comparison, not an
additional baseline quality threshold. Baseline malformed output or cache corruption
still blocks the complete comparison.

A pass merely permits the next bounded corpus-repair experiment. It grants no V3
acceptance, no retrieval quality score and no publication readiness. If the controls
or protocol subsequently change, preserve this first report and version a new
experiment instead of changing its expected answers to match observed output.

## Budget, provenance and commands

Default provider configuration is DeepSeek `deepseek-v4-flash`, `json_object`,
disabled thinking, temperature zero, 1,536 maximum completion tokens, no retries.
Maximum new requests are 48 (24 per profile). The raw-output cache, dataset/protocol
requests, provider identity, implementation commit and configuration are bound.
Cache hits use zero calls. Existing invalid cache files are errors and are not
overwritten by paid retries. Provider failures stop the run with only safe
code/status/retryability diagnostics. A completed first report cannot be overwritten.

Dry-run, no API key read or provider construction:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.surface_review_calibration
```

One complete live comparison, in the PowerShell process that holds `DOPPEL_API_KEY`:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.surface_review_calibration --live --max-new-calls 48
```

Output: `data/doppel/surface-review-calibration-v1.json` when all controls have been
attempted; otherwise `data/doppel/surface-review-calibration-v1-progress.json`
contains the stop point and conservative partial metrics. Exit zero means the
calibration gate passed, one means a completed comparison failed, and two means the
run is incomplete. A failed complete report is a useful measurement, not a reason
to keep rerunning until it passes. After a budget interruption, the same command
can resume from raw caches with no charge for completed responses.

## Repair work after calibration

Before any new blind-surface authoring, freeze a hash-bound repair inventory using
the unchanged V3 authored/review artifacts. Audit all 24 scopes' residency intervals
and March 15 queries consistently. Audit complete issuer/adoption relation families,
including unflagged scopes, for subtype/role and transfer/lifecycle coherence.
Preserve gold evidence, scope/state/time fields and relation routes. Changes to
entity display names must include their referencing surfaces; unchanged strings
should be retained. Then author only bounded necessary slots, perform explicitly
versioned semantic review, and keep compilation closed until acceptance.
