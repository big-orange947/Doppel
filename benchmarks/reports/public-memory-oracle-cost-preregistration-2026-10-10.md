# Small S-derived oracle Reader diagnostic freeze

Before paid calls. Stop new graph/miner work; reuse prior S answers as descriptive
context only. This is oracle Reader diagnosis, not a Doppel retrieval score or
official LongMemEval/AML run. Current DeepSeek alias is not a pinned version;
official docs say legacy deepseek-v4-flash now serves V4.1-Flash. Keep the alias,
record the drift, do not attribute old/new changes solely to algorithm changes.

## Fixed cohort and source projection

First opened non-abstention case in each public type from the frozen 50-case
manifest: d52b4f67, 21d02d0d, 38146c39, gpt4_d9af6064, 3ba21379, ceb54acb.
Then opened refusal 29f2956b_abs and first source-order non-reserved refusal
0862e8bf_abs. The latter becomes a newly opened DEVELOPMENT case, never held-out.
Protect reserved IDs from the 3/10/50 manifests; no selection from outcome/gold.

Official HF oracle downloaded once, no paid call. Its question dates differ from
cleaned S for all eight selected IDs, so do not mix snapshots. Derive the oracle
from exact S answer-session IDs; refusal controls use official oracle session IDs
matched to S source. Preserve S text, session dates and question date. Explicitly
label this S-derived oracle, not the untouched downloaded oracle dataset. Oracle
data projection intentionally uses evidence annotations; no labels/reference or
profile reach Reader inputs, and no retrieval/planner uses those annotations.

Keep complete source sessions in stable timestamp order, assistant/user roles,
no text truncation. Context lengths 12/22/16/24/24/4/12/12 messages. This differs
from S top-20 packing and measures supplied-evidence Reader capability, not a
same-budget retrieval ablation. Old S scores/caches remain unchanged.

## Budget and replay

Unchanged Reader V2, DeepSeek task judge explicitly diagnostic (not official
GPT-4o). Eight Reader <=2048-token completions + eight judge <=1024: <=16 calls,
no retries. No planner, miner, graph, embedding, reranker or database writes.
Canonical request limit 100000 bytes; actual Reader 7365–53410 bytes. Check CNY
balance before every stage; stop at net observed debit >=1 CNY or check failure.
Single in-flight call can exceed the threshold; topups/concurrent account use mean
balance delta is not exclusive billing proof. Do not silently extend/retry budget.

- Preflight `data/doppel/public-memory-full-oracle-cost-preflight-v2.json`.
- SHA-256 `f482c364fb3ef7b224be75f58b69a0bbd70dcfd22bc6eb92c1a5b4a5d3ee5f8b`.
- Plan `dbd361cc0003727ba53ca32973e431d9839dcd455d98b9a527b444044001ad1f`.
- Run dir `data/doppel/public-memory-full-oracle-cost-v2`.
- Live `data/doppel/public-memory-full-oracle-cost-live-v2.json`.
- Replay `data/doppel/public-memory-full-oracle-cost-replay-v2.json`.

V1 preflight superseded before spending (timeout/format implementation identity
changed); no V1 live calls or overwrites. New module fake/offline seven controls
passing, surrounding directed suite 78 passing, Ruff passing, Pyright module clean.
Run empty-key cache-only replay, report each failure/abstention plus usage. Official
GPT-4o scoring is deferred, not replaced by relabeling this DeepSeek judge.

## Cost evidence from recent complete receipts

Graph histories 4–9: 4807 requests/20008428 reported tokens; natural QA 4–8:
25 requests/185395 tokens. Different cohort sizes, excludes extraction/schema/
earlier graphs/partial tenth and account activity: not an exact currency audit.
It identifies graph preparation as the dominant recorded resource use, not the
cost of a normal question. No claim that the account's entire ~20 CNY debit has
been exclusively reconstructed or assigned to these receipts.
