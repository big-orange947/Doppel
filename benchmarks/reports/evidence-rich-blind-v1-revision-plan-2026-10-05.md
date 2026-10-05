# Evidence-rich blind V1: pre-retrieval revision plan

Date: 2026-10-05

Status: revised host and surface contracts frozen before new authoring or retrieval.

Revised host manifest fingerprint:
`a46ef5d4b2bc0e9a7246bbb07d7d68ec277f4584499b2bdc70c9957cf2d639b3`

## Authority and semantic repairs

`build_evidence_rich_blind_manifest_v2` derives a revision without mutating the original
builder or its fingerprint. A benchmark-only relation catalog declares endpoint types
and natural meanings. All original memory IDs, owner scopes, partitions, event
identities, private authority/state/time fields, labels, and relation routes remain
fixed. New entity slots isolate the no-answer object, its holder, and the competing
path's correctly typed final node.

Entity types follow each relation family. The competing first edge's brief names its
exact source instead of describing another similar object. Custody no-answer edges
use a separate object, so they cannot contradict the one-hop object's holder.
Historical edge text must explicitly state its past status. Temporary-residence
briefs include the frozen valid interval in natural language. Document and
cross-conversation questions must ask for the fact value rather than an identity.

The authoring contract permits consistent synthetic names and unspecified concrete
details, requires exact endpoint names in content and edge text, and enforces
owner-local uniqueness. The reviewer receives relation meanings and must assess
synonyms semantically, permit consistent synthetic choices, and never demand that a
question disclose an answer or its answerability. This changes the reviewer protocol;
its scores must not be represented as a repeat of the original review.

## Immutable reuse and new calls

The revision binds the authored-artifact and rejected-review hashes. Parent review
coverage, issue accounting, and owner/key references are validated before reuse.
Only exact `OwnerAuthoringBatch` equality plus zero parent findings permits a seed.
All 24 tail batches meet that condition: 2,304 unchanged memory strings are retained.
The 24 changed core batches must be generated afresh, with up to six sealed variation
attempts each. The nominal authoring cost is 24 calls; the total ceiling is 144.
No model receives another owner's text, private IDs, evidence labels, or retrieval
results. Same-owner inherited wording is supplied solely to avoid duplicate surfaces.

New authoring, review, and compile artifacts use `revised` paths. The new complete
semantic review covers all 48 batches, including inherited text, with up to 48 new
calls and no automatic rewrite. A rejection blocks compilation and is preserved.
Provider failures now expose only safe code/status/retryability metadata; no provider
body or secret is stored in diagnostics.

## Commands

All stages are dry-run by default:

```powershell
python -m benchmarks.evidence_rich_blind_revision author
python -m benchmarks.evidence_rich_blind_revision review
python -m benchmarks.evidence_rich_blind_revision compile
```

Explicit live authoring and review:

```powershell
python -m benchmarks.evidence_rich_blind_revision author --live-authoring --max-new-calls 144
python -m benchmarks.evidence_rich_blind_revision review --live-review --max-new-calls 48
```

Run review only after authoring reports complete. Run offline `compile --compile`
only after the revised review accepts every batch. No retrieval can start until the
compiled corpus is validated, fingerprinted, and committed. The original V7/V8
comparison policies and downstream evaluation gates remain frozen. Effective unique
surface counts and synthetic/shared-template limitations remain mandatory disclosures.
