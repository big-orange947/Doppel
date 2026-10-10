# Low-cost S-derived oracle Reader diagnosis

Frozen at e5e9442, live artifact SHA-256
`e0f6636bcf6d82e01fa98e6a6366c900f14fdfdc75b4d348f2cf81179a214165`:
`data/doppel/public-memory-full-oracle-cost-live-v2.json`.
Eight complete rows, 16 successful calls, zero missing usage, no retries, no
miner/graph/planner/index/database work. Not a Doppel retrieval score, official
LongMemEval metric, blind validation or AML result. Unchanged Reader V2 and a
DeepSeek task judge; live model alias may now resolve to V4.1-Flash.

| Public category | Case | Diagnostic task result |
| --- | --- | --- |
| Single-session user | d52b4f67 | correct: Grand Ballroom |
| Multi-session | 21d02d0d | correct final count 2; wording starts with 1 then adds another, not a clean response |
| Single-session preference | 38146c39 | incorrect: refuses to generate personalized cookie advice |
| Temporal reasoning | gpt4_d9af6064 | correct: router precedes thermostat |
| Knowledge update | 3ba21379 | correct: current Ford F-150 instead of older Mustang |
| Single-session assistant | ceb54acb | correct: four previously proposed alternatives |
| Refusal | 29f2956b_abs | correct: guitar evidence does not supply violin duration |
| Refusal, newly opened development | 0862e8bf_abs | correct: cat name does not supply hamster name |

Ordinary tasks 5/6; refusal controls 2/2; combined diagnostic 7/8. Each category
has only one ordinary sample: no population/per-category performance estimate.
All citation IDs legal, not independent entailment proof; English questions still
often answered in Chinese. The count's mixed wording and judge lenience are
retained, not silently relabeled or advertised as perfect reasoning.

## Interpretation

All relevant sessions are deliberately supplied, up to 24 complete messages.
The preference failure persists with full source evidence; more graph authoring
will not fix a Reader that demands an already-recorded recipe instead of giving
new advice based on remembered preferences. A generic response-policy distinction
between fact recall and newly generated personalized advice needs separate
controls; do not special-case cookies or any benchmark domain. Doppel facts and
suggestions must remain distinguished.

Count/update succeed under this supplied-evidence diagnostic while earlier
highest-config runs could fail. This suggests useful focus on evidence selection,
structure/metadata interpretation and downstream response policy, but does NOT
isolate causality: source amount/order, timestamps exposed to Reader, model-alias
drift and sampling differ. Old S raw/memory/combined scores remain immutable and
are not directly pooled or subtracted as a controlled graph/temporal uplift.

Official oracle question dates differ from S on all eight selected IDs. The run
uses S-derived evidence-session projection with S dates/text/reference and strips
labels before Reader. For refusal controls, official oracle session IDs select
the matched S source; never substitute empty refusal context. Protected reserved
cases remain untouched. One additional refusal becomes development, not blind.

## Resource and currency observations

- Reader: 8 calls, 56695 input/1569 output/58264 total tokens.
- Judge: 8 calls, 3610 input/343 output/3953 total tokens.
- Combined: 62217 tokens, 51089 cache-miss input/9216 cached input/1912 output.
- Balance endpoint: 5.32 CNY before, still 5.32 at live-report completion; a later
  read returned 5.26 CNY, observed net debit 0.06 CNY. The immutable live receipt
  retains its original immediate zero delta. Delayed billing means neither zero
  immediate delta nor the balance-stop policy is a strict per-call spending cap;
  account delta is not proven exclusive billing attribution. Do not claim free.
- Previous graph scopes 4–9 alone: 4807 calls/20008428 tokens versus recent QA
  scopes 4–8: 25 calls/185395. Different scopes/stages, not an exact total invoice.

Empty-key replay `data/doppel/public-memory-full-oracle-cost-replay-v2.json`,
SHA-256 `b3104ab548a8b241e31626c7ee97290cacbe4ec4ebfc4d5524b5703ccb56fbff`:
all rows and frozen plan canonically identical; 16 cache hits, zero new requests.
Directed 78 tests passing, Ruff whole repo passing, Pyright new module clean.
No repeated full-suite run on this benchmark-only change; last full suite 1559
passing belongs to the preceding source-window code and is not relabeled here.

Next: reuse matching S contexts for a small contemporaneous response-policy or
retrieval comparison, with fresh freeze/call budget; no new Graphiti authoring or M.
Official GPT-4o grading and full A/B/C matched ablation have NOT been performed.
