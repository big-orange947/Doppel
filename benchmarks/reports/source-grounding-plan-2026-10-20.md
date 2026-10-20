# Source-grounding and precision repair: frozen plan

Freeze implementation/protocol before new paid execution. This is a bounded
source-entailment development diagnostic, not new QA accuracy, blind validation,
full LongMemEval or AML scoring. No eager analysis or graph construction.

## Fixed inputs and requests

Use all8 previously opened event-time trial windows in the same frozen order,
replaying their completed analyzer receipts. Exact request hashes/provider
identity must match. No new extraction call, query/gold/old-answer/old-score
input to the reviewer. Apply actual SourceGroundedPersonalMemoryAnalyzer,
PersonalMemoryMiner actor/evidence gates and TransientMemoryViewBuilder.
Unknown/malformed citations are not repaired; original raw evidence remains.
The previous report is integrity-bound by SHA-256:
288809840186943057b82e9aa50dd31fb49719676cfb73b619afa396e7e49b6d.

One additional fixed8-item cross-domain/bilingual control batch comes from
benchmarks/datasets/source-grounding-controls-v1.json. Four intentionally
unsupported completions and4 supported claims cover decision, intention,
conditional action, actual completion, cancellation and a completed decision
whose target is not completed. The reject labels stay local and are never sent
to the model. These controls are authored development checks, not independent
blind evidence or an exhaustive reviewer calibration.

Use exactly9 reviewer calls maximum (1 control batch+8 opened windows). Semantic
control errors are recorded, not hidden, reworded or used to change thresholds;
complete the observational diagnosis without default promotion. Invalid schema,
coverage, quotes or provider failure stop the run and retain used/unused budget.
No automatic retry, replacement case, cap expansion or output repair.

## Behavior and reporting

The opt-in wrapper omits only confidence>=0.8 contradictions, retaining supported/
uncertain/lower-confidence drafts without confirmation. It never rewrites content,
dates, scope or actor. Report accepted/rejected drafts, exact source quotes,
confidence, already-ineligible overlaps, false positives and the observed
decision-to-completion mistake. Do not claim a supported verdict verifies truth.

Precision sanity uses domain-neutral duration bounds, not new calendar parsing:
flag a week labeled day; preserve its raw range/label and candidate inclusion,
expose an uncertainty warning, and prevent exact interval-count certification.
Date normalization and exact-day/calendar proof remain outside this repair.

New Reader/judge calls, persistent source writes, graph/embedding calls and
reserved-history access are all0. No new answer accuracy or replacement of37/50
or previous small paired scores. Source review can lose valid claims, so maintain
raw fallback and do not promote this experiment to a default policy.

## Budget and reproducibility

DeepSeek flash/json_object, temperature0, thinking disabled;8192 output tokens
per review request. Durable9-call ledger,100KB request cap,900KB cumulative
request cap. Frozen request hashes and per-call started/completed receipts.
Separate key-free cache-only replay must produce byte-identical output with0
new calls; provider token accounting is not exact currency billing.

- Runner: doppel.opened-source-grounding.v1
- Frozen preflight: data/doppel/source-grounding-preflight-frozen-v1.json
- File SHA: a97ac12e45b2d66c44178e085fdce80b0a859e5379320b6810c7863582850f18
- Plan: 49eb38efa0582c83efe94dc35caaaff28d7fdddeb55cbdcd4a5c50f6c49dbb39
- Run directory: data/doppel/source-grounding-v1
- Earlier preflight draft is not the frozen identity.

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_memory_source_grounding --run-dir data/doppel/source-grounding-v1 --output data/doppel/source-grounding-live-v1.json --frozen-preflight data/doppel/source-grounding-preflight-frozen-v1.json --execute
```
