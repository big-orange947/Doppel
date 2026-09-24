# Combined retrieval V2: frozen-corpus preregistration

Date: 2026-09-24

Dataset: `doppel-combined-retrieval-zh-v2`

Dataset fingerprint: `f35257ad354f5132c49f152b0b705fbba2cc7ce04dec4635237c91c505a84f6b`

V1 was superseded before any provider or live retrieval call. An offline validator
showed that repeated cross-owner scenarios also repeated some full natural-language
prompts, which would overstate topology sample size. V2 retains the same 36 owner
scopes, 3,600 memories, 216 entities, 144 graph edges, evidence labels, time bounds,
and cross-owner name collisions, but gives all 144 cases distinct provider input.

No V2 provider output or retrieval metric existed when this document and fingerprint
were committed. V2 adopts every acquisition, topology, retrieval, safety, diagnostic,
and non-claim rule from
[`combined-retrieval-v1-preregistered-2026-09-24.md`](combined-retrieval-v1-preregistered-2026-09-24.md),
with the following binding replacements only:

- dataset suite/version/fingerprint are V2 values above;
- provider acquisition has 144 unique cases and at most 288 uncached calls under the
  V3 two-pass review protocol;
- the default acquisition cache, progress file, and first-result filename use the V2
  namespace, so no V1 artifact can be replayed accidentally.

Acquisition may be resumed only while dataset fingerprint, relation-catalog hash,
generator identity/version, provider configuration, and implementation commit remain
identical. Partial acquisition exposes progress and token usage but no quality score.
All 144 observations must be cache-valid before the first topology metrics are
calculated. A failure of any pre-registered threshold remains a reportable result and
does not authorize query-, entity-, category-, or relation-specific runtime patches.
