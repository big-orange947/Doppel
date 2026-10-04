# Evidence-rich blind V1 authoring V8: complete sealed result

Date: 2026-10-05

Runner: `doppel.evidence-rich-blind-authoring.v8`

Implementation commit: `c1c6f57a8850680190029a7d44ace53ebd28609f`

Manifest fingerprint: `852dfde146d8ac2920683ac275eb5a35700bdb47e01cf09cad4dd0433065d253`

Authored artifact SHA-256:
`b381788d6efa0ee0fe307f452a5895d05ad077ef35ac7983cbb55c5884f0ba37`

## Outcome

V8 completed all 48 authoring batches for 24 owner-disjoint scopes. The sealed output
contains surfaces for 4,608 memory slots and 240 query slots. It remains
`authored_unreviewed`: retrieval has not been opened, no quality metric is available,
and no result-dependent prompt or corpus edit has occurred.

The deterministic parent reconstruction recovered 23 batches from the immutable
V4/V5/V6 caches without a provider call. The live continuation completed the remaining
25 batches with 31 new calls, for 78 cumulative calls and 893,810 cumulative tokens:

| Result | Count |
|---|---:|
| Batches accepted on attempt 1 | 38 |
| Batches accepted on attempt 2 | 8 |
| Batches accepted on attempt 3 | 0 |
| Batches accepted on attempt 4 | 2 |
| Maximum accepted attempt | 4 |
| V8 scope-collision retries | 3 |
| V8 structural-validation retries | 3 |

The 225-call safety ceiling did not cause unused calls to be spent. The continuation
stopped immediately after batch 48 succeeded. All three parent-cache hashes and the
preserved V7 observation remained bound and unchanged. No API-key-like string was
found in the authored artifact or V8 provider cache.

## Next gate

The first independent semantic review is frozen at one request per authoring batch,
with at most 48 uncached calls. It may report issues but cannot rewrite surfaces. A
rejected review is preserved as a first result and prevents compilation. Only an
accepted review permits the offline compiler to project private host structure into a
new `compiled_unopened` corpus. Retrieval evaluation remains closed until both gates
succeed.
