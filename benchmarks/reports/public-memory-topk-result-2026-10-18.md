# Exact-k smoke: preserved failure, no quality result

Implementation/plan commit `059456f`. First source selection (`e9327a54`)
returned8 unique authorized IDs, not the requested20. Valid JSON, successful HTTP,
no unknown IDs/duplicates, normal completion. Strict exact-count validation failed;
the run stopped with `ValueError` at `source-selection`. No output was padded or
rescored, no source/passage QA comparison exists. Remaining11 calls were not spent.

One new call:19,332 input +46 output = **19,378 tokens**, all usage observed.
Reader/judge0 calls. This is additional to the previous permutation smoke's
1 call/19,290 tokens, not a refund/reallocation. All three preflight source/pool
bindings reproduced. No Store/index/graph writes or default changes.

The problem is a quota in the adapter contract, not demonstrated poor relevance:
up-to-k retrieval need not pad to exactly k. Introduce a separate upper-bound
contract without changing this result or accepting its cached output in another
experiment. Keep the exact-k class and rejection tests. Identity, uniqueness,
maximum size, scope/provenance and original-source checks must not be weakened.

Artifact `data/doppel/topk-diagnostic-live-v1.json`, SHA-256
`a9caf8e5d08f963cfe7c02cb8836b253b6889e40867706403cca66d629b37fc8`.
Run/cache/ledger: `data/doppel/topk-diagnostic-20261018-v1`.
Initial full regression:2009 passed/33 skipped/three subtests (229.17s); following
bounded-contract changes are verified separately. No independent benchmark claim.
