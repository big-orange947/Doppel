# Evidence-rich blind V1 authoring V7: preserved zero-call observation

Date: 2026-10-05

Runner: `doppel.evidence-rich-blind-authoring.v7`

Implementation commit: `882d35400f4c25012e102d6dfec3eacd01a2fbc7`

Manifest fingerprint: `852dfde146d8ac2920683ac275eb5a35700bdb47e01cf09cad4dd0433065d253`

## Outcome

V7 made zero provider calls and stopped at `owner-blind-02:01` with 2/48 batches
replayed. The cumulative provider ledger remained unchanged at 47 calls and 535,745
tokens. Retrieval remained unopened and no quality metric was computed.

This was not a provider, corpus, or scope-local validation failure. It exposed a cache
lineage dependency. Historical V4 request fingerprints included `must_change` keys
derived from the then-global evidence registry. For the first owner-02 batch, V4's
historical request path carried three global collision keys. Replaying the same cached
candidate under V7's scope-local registry correctly found only one owner-local
collision. That changed the next request body, and therefore its content-addressed
fingerprint, before V7 could find V4's already-cached second attempt.

The V7 state and empty V7 provider cache are preserved as evidence. No parent cache was
rewritten, copied, or re-keyed, and no missing cache entry was regenerated.

## Continuation decision

V8 separates two responsibilities that V7 accidentally coupled:

1. It replays each historical V4/V5/V6 chain with that chain's original global
   registry, reproducing the exact request fingerprints and locating immutable cached
   responses.
2. Independently, it evaluates every located candidate with the scope-local V7
   registry and selects the earliest candidate valid under the corrected authority
   boundary.

This deterministic reconstruction recovers 23 accepted batches without a provider
call: the 22 batches accepted historically plus the first owner-12 batch, whose V6
attempt 7 was structurally valid and repeated evidence only across owners. V8 then
continues the remaining 25 batches in its own cache namespace with the scope-local
contract. It binds the hashes of all three parent caches and the preserved V7
observation. Retrieval remains closed until authoring, independent review, and offline
compilation succeed.
