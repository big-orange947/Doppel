# Default analyzer lifecycle diagnostic: frozen plan, 2026-11-11

This is a small prospective synthetic development diagnostic, not a benchmark
score, independent blind test or release gate. The purpose is to replace the
scripted analyzer in four targeted lifecycle scenarios with the unchanged default
`ReferencePersonalMemoryAnalyzer` V8 and inspect the actual pipeline output.

## Frozen configuration

- Dataset: `benchmarks/datasets/personal-memory-lifecycle-probe-v1.json`.
- Four cases, five batches: newer correction followed by an older arrival;
  permanent residence plus an explicitly bounded temporary stay; cancelled course
  intention; contact ownership vs owner denial and historical assistant suggestion.
- Reference V8, default miner policy except explicit conversation-target scope;
  deterministic consolidation, arrival inbox, recoverable workflow and real SQLite.
- Index is a catalog test double. No embedding, Graphiti, ranking experiment,
  natural-language Planner, Reader or Judge. Query views are explicit structural
  diagnostics with no search text; they do not measure semantic recall.
- Model: `deepseek-flash`, official `https://api.deepseek.com`; json_object,
  temperature=0, thinking disabled, max_tokens=2048. The provider's model-list API
  reported this ID before freezing. Response aliases are recorded separately;
  no pinned model snapshot is claimed.
- Maximum five provider attempts, 100,000 canonical request bytes per call,
  500,000 total canonical request bytes. This is an attempt/byte cap, not an exact
  token/currency cap; missing provider usage is not zero cost. No retries.
- All model output is cached before downstream validation; source/config/model
  identities bind caches and the durable attempt ledger. Plan/config/code drift
  must reject reuse. Failures are retained and stop the run; no automatic repair,
  extra attempts, rubric change or selection of better samples.

Default miner behavior filters historical agent messages before extraction. The
scenario with an agent statement therefore tests that configuration and its raw
evidence separation, not model robustness to unfiltered agent evidence. Contact
query authorization comes from the synthetic host manifest, never a model proposal.
All derived facts remain candidates; successful processing is not owner approval.

## Review

Inspect the per-batch analyzer drafts and schema diagnostics, committed records,
source/evidence bindings and explicit current/planned/prior/as-of views. Frozen
rubrics stay outside model inputs. A completed empty extraction can be a quality
failure; workflow completion is never scored as semantic success. Invalid drafts
and evidence-policy failure must remain visible, including any valid drafts lost
when a default fail-batch gate blocks an entire batch.

Manual review is performed by Codex and is not independent. Cite source/output
wording and metadata when explaining errors. Do not compare a four-case fraction
with public benchmark scores. Date-only normalization precision is a separate
caveat; a schema-valid timestamp is not proof of a justified boundary.

After the live run, rebuild a new SQLite state directory from the same raw-output
cache with `--cache-only`, without reading the API key. Compare the semantic
projection digest (claims, states, selected temporal/subject fields, evidence IDs,
views and analysis observations), not full random IDs or ingestion timestamps.
The original database, journals, outputs and failed attempts remain intact.

## Invocation

```powershell
python -m benchmarks.personal_memory_lifecycle_probe `
  --run-dir data/doppel/lifecycle-probe-v1 `
  --state-dir data/examples/lifecycle-probe-v1 `
  --output data/doppel/lifecycle-probe-v1-preflight.json

# Only after freezing this implementation and preflight:
python -m benchmarks.personal_memory_lifecycle_probe --live `
  --frozen-preflight data/doppel/lifecycle-probe-v1-preflight.json `
  --run-dir data/doppel/lifecycle-probe-v1 `
  --state-dir data/examples/lifecycle-probe-v1 `
  --output data/doppel/lifecycle-probe-v1-live.json
```

Live execution reads `DEEPSEEK_API_KEY` only from the environment. For cache-only
reconstruction, add `--cache-only`, use a new state directory and output path, and
retain the same preflight/run-dir/model. A missing/invalid cache fails closed.
