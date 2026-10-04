# Evidence-rich blind V1 authoring V4: preserved incomplete result

Date: 2026-10-04

Runner: `doppel.evidence-rich-blind-authoring.v4`

Implementation commit: `90c213ddb26b17259cf0d6d7daf742a986c65306`

Manifest fingerprint: `852dfde146d8ac2920683ac275eb5a35700bdb47e01cf09cad4dd0433065d253`

## Outcome

V4 stopped at `owner-blind-09:01` with `SurfaceGenerationExhausted`. It accepted
16/48 batches covering eight complete owner scopes, made 29 paid provider calls, and
used 325,750 provider tokens. Retrieval remained unopened and no quality metric was
computed. A zero-call replay produced 29 cache hits, zero misses, and the same stop.

The final invocation requested twelve new calls but used only four: owner 08's second
batch passed on its first attempt, then all three sealed attempts for owner 09's first
batch collided. The remaining eight-call budget was not consumed.

## Root cause

The 96 host-owned memory slots in the stopped batch had 96 distinct semantic
specifications. The provider nevertheless collapsed families of distractors into
verbatim-equal output:

| Attempt | Unique memory strings | Duplicate groups | Registry collision keys |
|---:|---:|---:|---:|
| 1 | 49/96 | 14 | 47 |
| 2 | 65/96 | 20 | 31 |
| 3 | 91/96 | 5 | 6 |

On the third attempt, five collisions were within the batch and one also matched an
already accepted memory. This is a contract mismatch rather than a corrupt cache or a
host-manifest duplicate: V4 told the provider not to reuse another owner's evidence,
but did not explicitly require all memory and non-empty edge strings inside the same
request to be distinct. The registry intentionally enforced both invariants.

## Accepted-surface audit at the stop

| Surface | Raw | Unique |
|---|---:|---:|
| Entity names | 128 | 93 |
| Memory contents | 1,536 | 1,536 |
| Non-empty relation edge facts | 80 | 80 |
| Query texts | 80 | 60 |

The repeated entity and query surfaces are intentional cross-scope isolation pressure.
There were zero accepted memory duplicates, edge-fact duplicates, nonce leaks,
internal-handle markers, invalid cache entries, or credential markers.

## Continuation decision

V4 remains immutable. V5 binds to hashes of the V4 acquisition manifest and all 29
provider envelopes, reads those entries without writing to the parent directory, and
replays their exact V4 requests. New attempts use a separate content-addressed cache
and an instruction that explicitly requires within-batch memory and edge uniqueness.
The sealed ceiling is raised from three to six attempts. V5 therefore continues from
attempt four of the failed batch without regenerating or migrating the 16 accepted V4
batches. Retrieval remains closed until authoring, independent review, and offline
compilation all succeed.
