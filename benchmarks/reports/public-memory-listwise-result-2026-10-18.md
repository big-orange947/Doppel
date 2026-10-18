# Listwise diagnostic: stopped on an incomplete permutation

Date: 2026-10-18. Frozen implementation/plan commit: `d155a0c`. This is an
**unsuccessful protocol smoke**, not a retrieval-quality comparison or score.
The [pre-call plan](public-memory-listwise-plan-2026-10-18.md) remains unchanged.

## What actually ran

All three opened cases reproduced the existing BM25/vector top-80 candidate pools
and original scoped Store inventory hashes. Read-only source reload/resolver
checks passed for the preflight pools. No original text was truncated for source
ranking. Canonical source requests were 75,404, 104,303 and 121,869 bytes.

The first source ranking request (`e9327a54`) exactly matched its frozen request
hash. HTTP generation succeeded, returned syntactically valid JSON and stopped
normally, but `ordered_ids` contained **79 unique IDs instead of 80**:

- Missing: `candidate-74`.
- Duplicate IDs: zero.
- Invalid/invented IDs: zero.
- Full-permutation validation: failed.

The scorer rejected the output; `SourceAwareReranker` surfaced its unavailable
status as a `RuntimeError`. That is the wrapper-level failure class in the report;
the output cache establishes the more specific incomplete-permutation cause.
No IDs were appended, repaired, dropped or silently treated as a successful order.
The run stopped immediately, as preregistered.

| Stage | New attempts | Complete provider usage | Actual tokens |
| --- | ---: | ---: | ---: |
| Source/passage ranking | 1 of 6 | 1/1 | 19,290 |
| Reader | 0 of 3 | N/A | no calls |
| Provisional task judge | 0 of 3 | N/A | no calls |

Ranking usage: 18,889 input + 401 output = **19,290 total tokens**, reasoning 0,
cached input 0. All attempt/byte budgets remained within limits. Completion
usage is observed, not estimated; no monetary price or exact billing claim is
made. The remaining 11 planned calls were **not** spent or carried into a retry.

There was no passage ranking, packed candidate context or generated answer. Old
baseline grades remain 2/3 and were bound successfully, but **new correctness is
not measured**. Do not report 0/3, a quality regression, a successful gain or a
paired comparison. End-to-end citation/semantic support was not exercised.

## Engineering result and next decision

The generic opt-in scorer and bounded diagnostic are implemented. Offline tests
cover malformed bindings, limits before provider calls, request mutation,
untrusted-data separation, no retries and preservation of scope/authority/text
through the existing wrapper. The live failure shows that demanding a complete
order for every distractor is a fragile output contract for this model. The JSON
schema is not provider-enforced in JSON-object mode; parsing JSON is insufficient.

This says nothing yet about whether the model ranks useful evidence better.
Keep current production defaults and all failed outputs. Do not tune question
keywords, role quotas, judges or evidence labels to make the experiment pass.

The next bounded implementation should ask for an **explicit top-k selection**,
with k fixed before the call (the consumer needs 20, not a meaningful order of
all 80). Validate exactly k unique authorized IDs; report the unselected remainder
as *unranked*, not inferred model judgments. This is a new contract and must have
new tests, a new frozen request/schema/budget identity and a separately reported
run. It must not reinterpret this 79-ID response as a valid top-k response or use
implicit completion/repair. No further paid calls were made this turn.

## Provenance and verification

Local ignored artifacts:

- `data/doppel/listwise-diagnostic-preflight-v1.json` SHA-256
  `19c454b3f9de938d033a331510f8bdaa22d1592d33e67be5450378d3c8c5efc2`.
- `data/doppel/listwise-diagnostic-live-v1.json` SHA-256
  `8e109da49df8a17a6d6123c5bff946a8463422bca7bc76a507fb8c2fd1bdda27`.
- Cached provider output SHA-256
  `4068140c90715dbbc35e126e30bcdb589c8eb42d75ed27827d2de1bed6fccf83`.
- Run directory `data/doppel/listwise-diagnostic-20261018-v1`, including durable
  SQLite attempt/usage ledgers and the pre-await request receipt.

Full regression: **1,985 passed / 33 skipped / three subtests passed** (222.72s).
Targeted suite 35 passed. Ruff repository check and new-file formatting pass;
Pyright new implementation/driver: zero errors. One existing Graphiti/Pydantic
deprecation warning remains. No graph calls, source/index writes, database resets,
reserved/new questions or changes/staging of the user's `uv.lock`. Key remained
environment-only. No paid recovery, fresh-generation retry or cache-only full-run
replay was performed.
