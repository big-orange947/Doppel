# Source-attribution V2 control comparison: frozen plan, 2026-11-11

Prospective synthetic development controls, not an independent benchmark. No
previous bicycle/interface/travel/cancellation case is executed or relabeled.
This round tests an optional source-review adapter, not extraction quality or
retrieval recall. A model review is not semantic verification or owner approval.

## Candidate and invariants

V1 remains unchanged in prompt, schema, request shape, version-binding formula,
default annotation policy and gates. V2 is module-only opt-in, with a separate
version identity. It combines two interventions: one draft's cited sources per
request, plus host-derived speaker/identity frames and perspective instructions.
This experiment does not separate their causal contributions.

V2 prechecks all request byte bounds before its first call, then validates each
single-draft response's exact coverage and source quotes before continuing. It
never rewrites content, fixes citations, upgrades authority, grants scope access
or confirms a fact. Unknown evidence remains for ordinary miner policy. Default
annotation retains candidates; no withhold policy is enabled in this experiment.
No role, name, domain dictionary or benchmark-ID special case is added to runtime.

## Controls, cost and comparison

- Four new cases, eight fixed drafts: two-person predicate ownership; contact
  first-person negation vs sibling; embedded quoted speech; uncited assistant
  contradiction and hypothetical action as a distraction from legitimate owner evidence.
- Each case contains one supported and one contradicted draft. Frozen expected
  labels/rubrics are never sent to the reviewer. Both arms receive the same drafts
  and evidence, with alternating arm order. V1 sees one case jointly; V2 reviews
  its drafts separately. The assistant example is passed directly to the wrapper;
  it does not imply that the default miner would include agent messages.
- V1 four calls; V2 eight calls. Twelve attempts total, no retries. Maximum
  canonical request bytes: 100,000 per call / 1,200,000 cumulative. Provider
  maximum output 2,048 tokens. Attempt/byte bounds are not a currency/token cap.
- DeepSeek `deepseek-flash`, json_object, thinking disabled, temperature zero,
  max_tokens; record actual response alias and finish reason. No pinned snapshot.
- Use existing durable ledger and content-addressed raw-output caches. Invalid
  reviews, provider errors or request drift stop; preserve failed attempts/cache.
  No fallback model, response repair, rubric relaxation or selection of repeats.
- Report exact verdict matches, uncertain decisions, high-confidence false flags
  and missed flags separately. A completed review is not a correct review.
  Do not promote any default from eight development judgments. Even perfect
  control results do not establish production precision, recall or calibration.
- Cache-only replay must reproduce rows and summary with zero new calls. No
  extraction, QA, Store/index writes, embeddings, Graphiti or real chats.

Both arms are model judgments assessed against synthetic author labels, without
independent adjudication. Original failed lifecycle outputs remain intact.

## Execution

```powershell
python -m benchmarks.source_attribution_controls `
  --run-dir data/doppel/source-attribution-controls-v1 `
  --output data/doppel/source-attribution-controls-v1-preflight.json

# After implementation and preflight are frozen:
python -m benchmarks.source_attribution_controls --live `
  --frozen-preflight data/doppel/source-attribution-controls-v1-preflight.json `
  --run-dir data/doppel/source-attribution-controls-v1 `
  --output data/doppel/source-attribution-controls-v1-live.json
```

Live requires environment `DEEPSEEK_API_KEY`; keyless cache-only replay uses the
same preflight/run-dir with `--cache-only` and a new output path. Repeated live
execution after prior attempts is refused. New core/source/config fingerprints
do not authorize reusing prior lifecycle experiment plans or caches as unchanged runs.
