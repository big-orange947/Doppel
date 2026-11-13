# Source-clause extraction pilot: frozen plan, 2026-11-13

Three new synthetic messages: account-owner vs colleague acquisition/denial;
embedded reported relocation vs the enclosing speaker's unchanged residence;
contact/roommate ownership and intended application. No previous opened control
is reused. This is an authored, non-independent diagnostic, not a benchmark score.

Compare default V8 with the opt-in source-clause analyzer. Both use the same
messages and existing arrival/miner/consolidation/SQLite workflow, separate state
directories, same structured unbounded query views and catalog-only index.
Queries/rubrics/expected answers never enter analyzer requests. Default runs first,
so profile order is not balanced and causal comparisons are limited. No prompt
adjustment, sample replacement, retry or output repair after freezing.

The candidate's content policy is mechanically whole-source, so matching original
wording is a retention invariant, not evidence of better semantic interpretation.
Review model annotations, missing claims and expanded context separately. Do not
award a semantic score for copying source text. Candidate output has no free-form
summary/subject-ID fields, but can still misclassify source perspective or metadata.

Maximum six provider attempts: three default and three candidate; no reviewer,
Reader/Judge, embedding, graph or real chat. Official DeepSeek `deepseek-flash`,
json_object, temperature zero, thinking disabled, max_tokens=2048. Durable attempt
cap six, canonical input byte bounds 100,000 per call / 600,000 total; these do
not imply an exact token/currency cap. Raw outputs cached before later processing.
Provider, schema or evidence failures stop execution and preserve all state.

Freeze code/dataset/config in preflight before calls. Replay from the same raw
cache in a new state directory with zero new attempts; inspect projections and
full-source retention, not fresh random Store IDs. Default remains unchanged;
no automatic confirmation, withhold policy or authorization change is permitted.

```powershell
python -m benchmarks.source_clause_probe `
  --run-dir data/doppel/source-clause-probe-v1 `
  --state-dir data/examples/source-clause-probe-v1 `
  --output data/doppel/source-clause-probe-v1-preflight.json

python -m benchmarks.source_clause_probe --live `
  --frozen-preflight data/doppel/source-clause-probe-v1-preflight.json `
  --run-dir data/doppel/source-clause-probe-v1 `
  --state-dir data/examples/source-clause-probe-v1 `
  --output data/doppel/source-clause-probe-v1-live.json
```

Uses environment `DEEPSEEK_API_KEY`. Cache-only execution adds `--cache-only` and
new state/output paths; key is not read on that path. Preserve original receipts,
failed attempts, journals and the unmodified old experiment artifacts.
