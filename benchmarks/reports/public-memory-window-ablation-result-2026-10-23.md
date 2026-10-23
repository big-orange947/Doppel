# Candidate80 vs160: higher pool recall, lower delivered evidence

All50 fixed opened diagnostic cases completed. Protocol/code/test commit:
**bb28aea**, pushed before preflight and local inference. Frozen plan fingerprint:
81ef53406d67d0023442eb8df4dd822b367e1fe4f3e5a5e9b71cdd86b5949b03.
No question replacement, source repair, automatic retry, parameter change, graph,
LLM/paid API call or source/index write. Original37/50 answers/grades unchanged.

## Controlled comparison

Both arms independently retrieve production BM25/vector equal-weight RRF60 raw
windows from existing read-only PostgreSQL/pgvector. Same local BGE-small-zh512
embedding and frozen BGE-reranker-v2-m3 weights/runtime, CUDA batch1/8192 tokens;
same final20 whole-source items and ranked-fit24000 UTF-8 JSON bytes. No metadata
factoring, passage expansion, role preference, topic/date rules or lexical fallback.

Pointwise scoring is shared across each query's unique candidate union. Each
arm's own candidate order resolves ties. Actual80 candidates are a subset of160
in every case (union160 each); this was observed, **not assumed** by cutting160.
All source snapshots/actors/provenance are reloaded before and after model work,
with full corpus hash and complete current raw-vector catalog metadata checks.
Authoritative Store and vector metadata snapshots match throughout all50 cases.

**Fresh80 contexts reproduce all50 old contexts exactly.** This is stronger than
a loosely comparable fresh baseline and confirms that the observed evidence
differences below occur under the candidate-width change. It still does not
generate a new QA score or independently verify annotations/answer support.

## Primary positive-only results

43 answerable questions/76 annotated original turns. Seven unanswerable cases
are excluded from positive denominators and retained in operational/item totals.
No new answer/refusal, privacy/security or faithfulness score is claimed.

| Stage | Fresh80 | Fresh160 | Change |
|---|---:|---:|---:|
|candidate-window annotated turns|72/76 (94.7%)|75/76 (98.7%)|+3|
|top20 annotated turns|66/76 (86.8%)|59/76 (77.6%)|-7|
|packed-context annotated turns|60/76 (78.9%)|56/76 (73.7%)|-4|
|positive questions with all annotated turns packed|36/43|34/43|-2|
|all50 packed item count|574|490|-84|

Paired effects (recovered/displaced source annotations):

- Candidate:3 recovered,0 displaced,3 questions improve/0 regress.
- Top20:0 recovered,7 displaced,0 improve/5 regress.
- Packed:0 recovered,4 displaced,0 improve/3 regress.

The recovered candidate annotations at05/44/48 never reach the new top20.
Top20 losses:05 (3→1),20 (2→1),37 (2→1),40 (2→0),44 (1→0).
Packed losses:05 (3→1),13 (1→0),26 (2→1).
This does **not** mean those new answers would necessarily become incorrect:
annotations are not exhaustive, and no new Reader/judge was run. Keep37/50 frozen.

## Diagnosis, not a role-filter prescription

Across each arm's1000 top20 sources (including negatives), mean source text
length increases from1663.1 to2145.0 Unicode characters. Assistant sources rise
from662/1000 to757/1000; owner sources fall from338 to243. Packed bytes total
1176639 versus1181270 despite fewer packed items. Wider candidate competition
therefore changes source composition and increases average source length under
the same byte budget. Neither more candidates nor more topical text is by itself
successful delivery of annotated memory evidence.

These descriptive associations are not proof that assistant/long sources are
irrelevant or that a fixed owner/length penalty would improve QA. Legitimate
assistant-recall tasks require assistant output. Do not add role quotas, suppress
assistant evidence, tune on affected case IDs or promote an unsupported scorer.
Prior metadata/MMR and LLM-selector diagnostics remain separate; their old scores
are not revised or combined into this experiment.

Decision: **do not change the current80-candidate default to160** on this result.
This decision uses *answerable evidence delivery*, not an increased abstention
rate. No framework, service, embedding, Reader or answer-cache default changed.

## Actual local cost and integrity

- Completed50/50, no failure; frozen plan/code/input hashes and all50 checkpoint
  receipts recheck after completion.
- Local pointwise scoring50 calls/8000 pairs, below12000 hard maximum. Shared
  overlap saves4000 pairs versus independently scoring80+160 for each case.
- Actual model device `cuda:0`, zero token-truncated pairs, longest4107 tokens.
- Actual local query embedding calls50; cross-arm cache hits50. No document
  embeddings, index repair or online model download.
- Sum of per-case local comparison times393.265s (~6m33s), including both arms,
  source/vector validation and first model load. Not single-search latency or an
  idle-GPU p50/p95; the regression test process also ran concurrently.
- Paid provider/LLM calls0, graph calls0, Store/index writes0. PostgreSQL sessions
  enforce read-only mode. Reserved histories remain outside runtime preparation.
- All50 full ordered top20 objects **and** packed contexts are now stored for
  each arm. Later packing-budget analysis need not repeat this model run. Old
  preparation files lacking complete orders were not overwritten.

Local artifacts (ignored, no credentials):

- `data/doppel/window-ablation-plan-v1.json`, SHA-256:
  f45b41b7f146bd1bcba90103fe40b026b4d8ac1a036d9191d02031b271f95c0d.
- `data/doppel/window-ablation-live-v1.json`, SHA-256:
  d43c29bde9ce4a4d392db97e0e464aea1ce6177f7bfbdf64c03bfbbe4f61c906.
- `data/doppel/window-ablation-v1/case-01.json` through `case-50.json`.
- Old50 summary SHA-256 unchanged:
  a5ecbc7c038a072eb69e73d5024fd53f3ec92800a5aec8c1bbeedd95c7ad8408.

10 new offline tests cover symmetric copy-safe query caching, pointwise score
reuse/per-arm tie order, changed query/source rejection, union consistency,
positive-only paired accounting and exact raw-vector catalog scope/version/
fingerprint validation. Full suite **2263 passed,33 skipped,3 subtests**,239.28s;
one existing optional Graphiti/Pydantic deprecation warning. Ruff clean, new
module Pyright0 errors/warnings. Existing uv.lock untouched/unstaged.

## Next bounded question

Candidate coverage is already near saturation here; simply enlarging the pool
does not repair source ordering. Use the saved full top20 sources to examine a
uniform24/48/96KB context-budget curve with **zero new model calls**, separating
what is merely dropped by byte limits from what never reaches top20. Larger
budgets must be labeled a resource/quality tradeoff, not a same-budget algorithm
gain. Only then choose a bounded source-selection/answer comparison if warranted.
Do not restart eager paid graph building or claim an official/independent score.
