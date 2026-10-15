# Frozen next three source-scope graphs (05–07)

Continue the same prospective fifty-question cohort, fixed ordinals 05/06/07:
`d23cf73b` (multi-session), `95228167` (preference), `bc8a6e93_abs`
(unanswerable). No outcome-based selection, core/default/config/prompt/model
changes, live calibration or early question/gold access. Four paired questions
are already scored; preserve their answers, warnings and judge disagreements.

Parent first-ten source receipt SHA-256:
`a577fc794e17b79ec9d07e1444f2522e09deac1c2937a5a370e39da50c6dcdf4`.
Cohort fingerprint remains
`cda3fbe324af2f63c60453faa87d4b66db0f68b1b9b77386bc4b09fbf27a5e5a`;
source ingestion fingerprint remains
`3055ab766570f7f5170a7af4c225ed8f843fecbcee8dc358a30975bb865e466d`.

| Fixed ordinal | 05 | 06 | 07 |
| --- | ---: | ---: | ---: |
| Source chunks complete | 51 | 50 | 47 |
| Original source turns | 512 | 507 | 493 |
| All eligible personal memories | 211 | 199 | 192 |
| Current scoped vectors | 730 | 707 | 687 |
| Graph attempt cap | 1,500 | 1,500 | 1,500 |

Scope 05 graph plan:
`62a54424349406d70794a7b30093ba81c23c8b815eb7f7dd8a721409e48dc521`.
Preflight SHA-256:
`1be567b6e5db1addbfdd65001d3923224186690f01015b1ab8269852050149a8`.
Source journal SHA-256:
`a73d697c6f4b0f2122cbd13e90aebaffa380d94db29c4d1d6eb466abbbb9b6db`.
Vector metadata SHA-256:
`19021f0aec05009a88626b15773c62792fc6808330d2050063ba4281460dac70`.

Scope 06 graph plan:
`0c248db2b73fe311f5c8e1663d4075ce9088d8d16eab8e021fd3271a211a9418`.
Preflight SHA-256:
`b8743407be6c6b5ab7931726deb7d82f2992b1625e4a60de27f4b051dea7d2e9`.
Source journal SHA-256:
`6d60e9b4ae6fa08bbe9ac3c3e914934f7711d475a149cc7698293235abff723c`.
Vector metadata SHA-256:
`27c6a033b09e4052d3376e15b94931def9a08d47ce27ec47cf1d1bb3784cc69f`.

Scope 07 graph plan:
`81a85e465fc0b45a41abdae195f95f2b708a93b067274bb32e20c1b861067aae`.
Preflight SHA-256:
`c4eb616feeb4d193b2a2c35133da96a53aa091f164141cd479f206f829a066ff`.
Source journal SHA-256:
`156941705cc17c1effbca3140086b390f6d4cc8e4d69bce9d34ad0427da4e9e9`.
Vector metadata SHA-256:
`70e8dd8c69563ead27aa76be8d7eb1784d8d41738ee6d5435ebef97f12a4b27f`.

Use unchanged production graph writer and operational scope adapter, all eligible
records in creation-time/memory-ID order, local 512-dimensional BGE embeddings,
DeepSeek flash/json_object/temperature 0/thinking disabled/8,192 output cap.
Each scope keeps the existing 500,000 canonical bytes/call and 32,000,000 total
bytes ceiling. Retain call usage/failures/warnings; no automatic retries, raised
caps, owned-slot repairs or deletion/reset of existing data. Successful graph
completion is scope-local projection only, not semantic-completeness certification.

Graph writes run sequentially so each can verify unchanged other cohort scopes.
A finished scope's read-only schema/QA may overlap the next scope's graph writer.
Before each schema, freeze actual distinct source-name inventory and six/seven/etc.
call count as determined by 24 names/batch; never include facts/question/gold.
Then freeze paired QA plans with original alternating order, five full calls and
three raw calls maximum, identical final context caps and same provisional judges.
No tuning after any score, partial-graph QA or new live control campaign.

Docker is healthy; provider key available; balance observation 53.59 CNY, not
exclusive billing. `uv.lock` remains unstaged user data. No full-fifty/full-500,
official LongMemEval, independent blind, AML or publication performance is claimed.
