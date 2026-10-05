# Blind corpus revision: V2 stop and V3 continuation

Date: 2026-10-05

Status: authoring diagnosis only. No retrieval result has been opened for this corpus.

## Preserved V2 observation

The V2 authoring run at commit `40d167dfac63bc450a8482e9f2e66d68bafa9727`
stopped at `owner-blind-10:01` with `SurfaceGenerationExhausted`, not at its total
call budget. It completed 33/48 batches: 24 inherited tail batches and nine newly
accepted core batches. These nine core batches passed structural validation only;
their independent semantic review is still pending.

The run used 37 provider calls and 594,763 reported tokens (378,577 input and
216,186 output, with zero reasoning tokens). Of its 37 responses, nine were
accepted, 25 failed entity-name uniqueness, and three repeated same-owner memory
text. The per-core accepted attempt counts were `6, 1, 6, 2, 4, 1, 2, 4, 5`;
all six attempts at the tenth core batch failed entity-name uniqueness.

The parent binding is the existing V2 manifest fingerprint
`a46ef5d4b2bc0e9a7246bbb07d7d68ec277f4584499b2bdc70c9957cf2d639b3`.
The stopped acquisition manifest SHA-256 is
`33fd531ad496951c0cc0b3c298da6dbc6aa63e5bbbf2d2f70ccdd02227b169e9`;
its state SHA-256 is
`fcf715cc0c279c27276959784814e085bb9729dae7d67575f3ed1741a64bd6ae`.
All 37 raw provider-cache entries remain intact. Their sorted relative-path/hash
inventory fingerprint is
`82e387a783421fcde2eddbfdfbb0020b8a6136e73d488869b5b7ac6edf85e806`.

## Contract defect and bounded repair

V2 changed `memory-competing-second` to point to `entity-branch-final`, but left
the old brief saying it points to the shared-alias organization. The brief and
structured endpoint consequently contradicted each other. Cache-only inspection
found the branch-final/shared-alias name collision in 19 rejected responses.
Other rejected responses reused place names across residence and relation-endpoint
slots; some responses had multiple duplicate pairs. These observations do not
prove that the contradictory brief explains every generation failure.

The V3 host manifest replaces only that contradictory brief, in each owner. All
entity slots/types, private scope/authority/state/time fields, memory identities,
query targets, labels, expected evidence and relation routes remain unchanged
from V2. The original and V2 builders and their request fingerprints are untouched.
The V3 manifest fingerprint is
`70fcb5c2fcbe3b2da7ec89e889b78066394a46027ab27e354ade7e1e3dcf0000`.

V3 authoring explicitly requires a distinct type-correct name for every entity,
including different place slots, and a silent final uniqueness audit. It explains
that shared names are allowed across owners only, and inherited memory texts are
exclusion references, not additional output slots. Output coverage, name uniqueness,
evidence uniqueness, nonce exclusion, authority boundaries and review gates are
not relaxed. No Doppel retrieval code, query-specific rule or score is changed.

## Reuse and accounting

The continuation reconstructs the exact V2 content-addressed request history,
including the original retry change-key sets and inherited owner-local text.
It validates each envelope, replays both structural rejection and collision
decisions, and must agree with the recorded accepted attempts, completion count
and stop point. Unexplained cache files or incompatible private/structural fields
block continuation. Parent manifest/state/cache inventory hashes are bound into
the new run. The parent cache is read-only.

The 33 accepted batch projections can be reused without a provider call. Existing
core surfaces are NOT declared semantically accepted under the corrected brief.
A new complete review of all 48 batches is mandatory. No cached rejected response
is rewritten or selected as a later lucky retry. New authoring uses separate V3
cache/progress/output paths and the same six-attempt ceiling per remaining batch.

There are 15 remaining core batches: nominally 15 new calls, at most 90 authoring
calls under the frozen per-batch ceiling, followed by up to 48 review calls.
These are budgets, not promises of completion or actual billed calls. V3's own
ledger records only new V3 calls/tokens; the earlier 37 calls and their usage
remain separately recorded under `parents.revision_v2`, preventing double counting.
Generation may still stop on a validation or provider error before either ceiling.

## Continuation commands

Dry-run authoring replays parent caches without a key or network call:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.evidence_rich_blind_revision_v3 author
```

Paid authoring and review use the key already in the current PowerShell process:

```powershell
$blindV3Surfaces = "data\doppel\evidence-rich-blind-v1-revised-v3-authored-surfaces.json"
$blindV3Review = "data\doppel\evidence-rich-blind-v1-revised-v3-review.json"
if (-not (Test-Path -LiteralPath $blindV3Surfaces)) {
    .\.venv\Scripts\python.exe -m benchmarks.evidence_rich_blind_revision_v3 author --live-authoring --max-new-calls 90
}
if (Test-Path -LiteralPath $blindV3Surfaces) {
    if (-not (Test-Path -LiteralPath $blindV3Review)) {
        .\.venv\Scripts\python.exe -m benchmarks.evidence_rich_blind_revision_v3 review --live-review --max-new-calls 48
    }
} else {
    Write-Host "V3 generation incomplete; preserve the cache and report its final progress."
}
```

A file-existence check protects the review transition even though the underlying
authoring runner reports an incomplete, safely cached stop with exit code zero.
Do not rerun the frozen V2 author command: it will replay the same six rejected
responses. Do not compile before the complete V3 review reports acceptance.
Review instructions remain the V2 semantic-review protocol; the reviewer receives
the corrected V3 briefs. V3 results are a new revision, not an untouched original
blind test or a fresh retrieval-quality measurement.

## Offline verification

The full suite passes with 842 tests, 33 skips and three subtests. Nine new tests
cover prose-only authority preservation, explicit surface contracts, exact retry
replay, parent-cache immutability, zero-budget continuation, four corruption cases,
15-call fake completion followed by a full 48-call fake review, rejection blocking
compilation, and continued duplicate-name rejection. Ruff and Pyright pass for the
new runner. The real parent cache dry-run recovers 33/48 projections with zero new
provider calls. Fake tests verify the workflow, not live generation quality.
