# Opened-eight structured-memory counterfactual: frozen plan

This is an opened development experiment, not a blind test, highest-config
retrieval run, LongMemEval full score, AML result or default-promotion gate.
Freeze this document and implementation before any new provider invocation.

## Question and selection

Does the existing structured personal-memory pipeline help answer time and
multi-session questions when the supplied raw evidence cannot change?

Take the first three answerable temporal and three answerable multi-session
cases, first knowledge-update case and first abstention case in the frozen
50-case parent order. Do not read previous QA outcomes for selection; retain
correct, incorrect and negative examples. Ten reserved histories stay closed.

| Ordinal | Case | Role |
| --- | --- | --- |
| 02 | gpt4_d31cdae3 | temporal |
| 03 | b6019101 | update control |
| 05 | d23cf73b | multi-session |
| 07 | bc8a6e93_abs | abstention control |
| 09 | gpt4_fa19884c | temporal |
| 12 | 00ca467f | multi-session |
| 16 | gpt4_e414231e | temporal |
| 19 | 5a7937c8 | multi-session |

## Arms and source boundaries

Both arms receive the exact saved raw context (whole-message BM25/vector/BGE,
20-item/24KB packing); Reader V2 instructions/schema and provider configuration
are identical. Rerun the raw control contemporaneously instead of importing its
old score. Alternate raw/structured Reader order by cohort index. Judge requests
contain only question, reference answer and candidate answer, never arm names,
retrieved context, old labels or diagnostic conclusions.

The structured arm additionally receives a bounded, explicitly unverified view:

1. Existing opt-in **ReferencePersonalMemoryAnalyzerV10**, source-only input,
   then real PersonalMemoryMiner gates (existing config, max_memories=40).
2. TransientMemoryViewBuilder and advisory event grouping; nothing confirmed,
   merged, corrected, deleted or persisted to production.
3. InMemoryStore of those candidates; actual Reference Planner V2 and
   PersonalMemoryQueryEngine with production default thresholds. No semantic
   or relation index in this ephemeral Store; this is not a Graphiti experiment.
4. Keep all validated claims alongside query-selected IDs and all original raw
   items. No engine filter can erase the raw fallback. Claims preserve actor,
   authority, type, declared event key, effective and observed time, state and
   original source IDs. Unknown validity is not false. Candidate interpretations
   are not new independently verified evidence and cannot be citation IDs.

All inference is restricted to this already-retrieved source window. Its missing
claims or event groups cannot prove global absence. Even if the engine can count
its complete *ephemeral* Store, the exported whole-history count must remain
indeterminate, value=null. Full engine results are retained separately for audit.
Question reference time is retained, while observation horizon is the maximum
of question time and available supplied observations: supplied-history, not
causal replay. Scope is reconstructed from the original preparation receipt,
not widened or substituted with another owner.

## Cost, accounting and limitations

DeepSeek flash, temperature=0, thinking disabled, json_object. No automatic
retries or completion of failed attempts. Stage caps: analyzer8 (8192 output
tokens), planner8 (2048), Reader16 (2048), provisional task judge16 (1024),
**48 new calls maximum**. Identical requests may hit the local cache. Raw evidence
is unchanged; the structured arm has extra model computation and up to40KB extra
UTF8 view payload. This is deliberately **not token-budget matched**, and cannot
attribute any gain exclusively to time filtering or graph reasoning. Existing
V10 has known atomicity/coverage limitations and is not promoted to the default.

Each stage uses a durable ledger, content-addressed cache, source-bound frozen
requests and started/completed/failed receipts. Dynamic structured Reader request
hashes are saved before either Reader call. Any invalid stage stops the run,
retains failure and unused budget; no model repair, replacement case, bound
extension or silent dropping. A key-free cache-only replay must make zero new
calls and preserve outputs and summaries.

Report paired gains/regressions, per-type results, extraction/quarantine counts,
nonempty effective bounds, actual engine scans/hits, answer text and provisional
grades. Inspect changed answers against original text, including false date
precision, plan-to-fact promotion, actor reversal and reasonable abstention.
Eight development cases cannot establish general statistical superiority.

## Frozen identities and commands

Implementation: `benchmarks/public_memory_structured_pair.py`; preflight:
`data/doppel/structured-pair-preflight-v1.json` (ignored local artifact).

- Preflight file SHA-256:
  `f33e77c005fe975ddd9b5e0470f41df4aff7749e113d9dbce0048e29a079b94f`
- Plan fingerprint:
  `1d90c766ad1940989f133d79d700b2b46a65b0de40a7a7d140354eeaee7f429d`
- Dataset SHA-256:
  `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`

The plan binds dataset, parent manifest, both existing preparation reports,
implementation dependencies, per-case scope/context, exact analyzer/planner/raw
Reader requests, model configs and caps. Preflight consumed zero provider calls;
185 targeted tests pass, including9 new offline tests, exact request consistency,
ephemeral real engine execution, candidate/authority gates, no global exact count,
failure retention, missing-key replay and identical-judge cache deduplication.

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_memory_structured_pair --run-dir data/doppel/structured-pair-v1 --output data/doppel/structured-pair-live-v1.json --frozen-preflight data/doppel/structured-pair-preflight-v1.json --execute
```

Do not change the experiment after observing its outputs. Diagnose a failure as
a failure; freeze a separate follow-up if warranted.
