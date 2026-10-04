# Evidence-rich blind V1 authoring V5: preserved incomplete result

Date: 2026-10-04

Runner: `doppel.evidence-rich-blind-authoring.v5`

Implementation commit: `74470cac4a7573ce7ed1f9c163b825e2be1c893e`

Manifest fingerprint: `852dfde146d8ac2920683ac275eb5a35700bdb47e01cf09cad4dd0433065d253`

## Outcome

V5 stopped at `owner-blind-12:01` with `SurfaceGenerationExhausted`. Across V4 and
V5 it accepted 22/48 batches covering eleven complete owners, made 44 provider calls,
and used 498,255 provider tokens. V5 itself contributed 15 calls and six accepted
batches. Retrieval remained unopened and no quality metric was computed. A zero-call
replay reproduced all 29 V4 and 15 V5 provider entries and the same stop.

V5 fixed the V4 same-batch memory-collapse defect. No V5 attempt reproduced V4's
large families of identical within-batch memory strings. Its remaining retries were
caused by exact evidence reuse across owners and owner-local entity-name duplication,
both rejected before acceptance.

## Exhausted batch

The stopped batch contained sixteen entity slots, one of which had a host-required
shared alias. The repeated name never involved that required slot. It always joined
the ordinary current-city slot to the ordinary two-hop target-organization slot:

| Attempt | Result |
|---:|---|
| 1 | Duplicate display name across the city and target-organization slots |
| 2 | One relation edge fact matched previously accepted evidence |
| 3 | Seven collision keys: six prior-memory matches and two prior-edge matches |
| 4 | One prior-memory match |
| 5 | Same city/organization display-name duplication |
| 6 | Same city/organization display-name duplication |

The host semantic specifications and entity types were distinct. V5 inherited V4's
general instruction that entity names be distinct but added detailed self-audit only
for memory and edge text. The provider therefore satisfied V5's repaired evidence
contract without reliably enforcing the older entity constraint.

## Accepted-surface audit at the stop

| Surface | Raw | Unique |
|---|---:|---:|
| Entity names | 176 | 125 |
| Memory contents | 2,112 | 2,112 |
| Non-empty relation edge facts | 110 | 110 |
| Query texts | 110 | 79 |

The repeated entity and query surfaces are intentional only across owner scopes.
Accepted evidence contained zero memory duplicates, edge-fact duplicates, nonce leaks,
internal-handle markers, invalid cache entries, or credential markers.

## Continuation decision

V4 and V5 remain immutable. V6 binds the manifest and provider-cache hashes of both
parents, replays each historical request with its exact protocol instructions, and
writes only new requests to a third cache. Its prompt requires an explicit pairwise
audit of the complete entity array, type-appropriate names, no city/organization reuse,
and exact preservation without reuse of host-required names. The sealed ceiling rises
from six to nine total attempts. The first V6 request is therefore attempt seven of
the exhausted batch. Retrieval remains closed until authoring, review, and compilation
all succeed.
