# Blind corpus: bounded repair inventory, retrieval still unopened

Date: 2026-10-06

This work returns to corpus curation after the three failed reviewer calibrations.
It does not introduce a fourth calibration prompt, repair the production retrieval
algorithm, waive machine review findings, or report new retrieval scores.

## Immutable inputs and offline output

The inventory is bound to these original artifacts:

- Host manifest: `70fcb5c2fcbe3b2da7ec89e889b78066394a46027ab27e354ade7e1e3dcf0000`.
- Authored surfaces: `d000d2a4ec413a45700b848074e3ec91a2f5f7b0dc043a94f6eeb4394823609e`.
- Rejected review: `e413f3880d639f52a370e67b707c23092deb438de920a7a23ee6c03ac7c58d3d`.
- Private authority fingerprint, excluding semantic prose briefs:
  `127c3a74137e12e70e89873aff6d745f18dbb7136ddb5b325d402a9842e006b6`.

The local packet is `data/doppel/evidence-rich-blind-v1-repair-inventory.json`,
SHA-256 `049ec372ff6106fa79c9c415f7ffd59a2f1edb13f8ccee7d15e68327a4bd0e27`.
It includes original texts and review reasons for bounded inspection; it stays
ignored and is not published with the blind answers. The published report uses
opaque slot/owner references only. Original authored/review hashes remain unchanged.

The runner refuses changed source hashes, incomplete review coverage, duplicate
or missing findings, an opened retrieval artifact, and replacement of an existing
inventory. It makes zero provider calls and does not read an API key.

## Frozen scope, not mandatory rewrites

There are 106 candidate surface slots out of 5,304 owner-local slots (about 2%).
A listed slot may be retained after verification. Unlisted surfaces must remain
byte-identical. This freezes a proposed repair boundary; it is not proof that every
unlisted surface is semantically correct. A newly discovered defect requires a
separately documented inventory amendment before retrieval, not an unlogged edit.

| Work family | Coverage | Candidate slots |
| --- | --- | ---: |
| Exact half-open temporary residency | All 24 owners | 24 memories |
| Exact as-of query date | All 24 owners | 24 questions |
| Issuable document subtype / competent issuer role | Owners 02, 10, 18 | 12 entity names |
| Sale/adoption actors and transfer lifecycle | Owners 08, 16, 24 | 12 memories |
| Consistent references if issuing entities are renamed | Owners 02, 10, 18 | 34 memory/query slots |

The 34 reference slots include textual occurrences outside typed graph endpoints.
This prevents a renamed entity leaving stale names in distractors, edge facts or
questions. No renaming has been performed yet. Shared-name requirements and all
entity identities/types remain host-authoritative.

The existing interval remains `[2026-02-01, 2026-04-01)`: entry February 1,
occupancy through March 31, no temporary residency from April 1. The historical
question remains bound to March 15, rather than an unspecified day in March.

Issuance repairs must make both document subtype and issuer role coherent. They
must not change `CREATED_BY` / `ISSUED_BY` routes to easier relationship types.
Animal repairs must supply explicit acquisition actors and a coherent transfer or
return/re-adoption sequence; they must not delete the competing or stale branch.
Keep the host's existing temporal boundaries, relation direction, evidence IDs,
scope, subject, authority, lifecycle, answerability, evidence labels and route gold.

## Preserve all findings; no automatic acceptance

All 23 original owner/slot/code findings are retained verbatim. Diagnostic
classification matches the prior audit: 12 suspected reviewer false positives,
five coherence findings and six ambiguities. Every finding remains
`pending_adjudication`, including the suspected false positives.

In particular, unknown-buyer and subject-correction questions are not placed in
the repair scope simply to satisfy the reviewer. A question can name its topic
without leaking its answer; it must not be rewritten to announce that the Store
cannot answer it. Historical and current custody can coexist without conflict.
These are assistant diagnostic judgments, not independent approval.

Acceptance, compilation, retrieval metrics and publication readiness all remain
false. The existing compiler still rejects the original rejected review. The
inventory does not implement an alternate accepted-review format or bypass.

## Next concrete work

1. Prepare a separate bounded surface revision and a per-slot old/new diff using
   this inventory; preserve verified untouched slots, including the bulk of the
   model-authored prose. Do not regenerate all 96-memory core batches.
2. Validate authority fingerprint, dependency consistency, same-owner uniqueness,
   exact time wording and complete retention of all unlisted slots. Revisit the
   corpus findings directly, not another paid reviewer-calibration experiment.
3. Record explicit adjudications with literal evidence and unresolved items;
   acceptance needs its own auditable decision, not relabeling the failed report.
4. Only after acceptance and corpus freeze, open the independent retrieval
   comparison using unchanged preselected V7/V8 configurations. Report required
   evidence, related context, ranking and hard isolation/time/provenance gates.

No new claims about recall or generalization follow from this inventory.

## Verification

- New offline tests: 11 passed, including unchanged parents, rejected compiler
  gate, all-family coverage, text-only dependency closure, missing/duplicate
  findings and authority-versus-prose fingerprint sensitivity.
- Full suite: 925 passed, 33 skipped, three subtests passed. One existing
  third-party Graphiti Pydantic deprecation warning remains.
- Ruff: both new Python files pass. Full Pyright with the workspace Python
  interpreter: zero errors/warnings. The initial interpreter-unspecified check
  could not resolve 17 optional backend imports; explicitly selecting `.venv`
  resolved those environment errors without installing or changing dependencies.
- No production code, accepted corpus, retrieval report or lockfile was changed.
