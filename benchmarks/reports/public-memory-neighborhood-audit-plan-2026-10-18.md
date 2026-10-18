# Opened-five source neighborhood audit: frozen zero-LLM protocol

2026-10-18. This is a diagnostic on already-opened ordinals41-45, not independent
validation, a new QA/AML score or a rescore of the fixed3/5 vs3/5 answers.

## Frozen input and algorithm

Bind original S source/parent manifest, completed prospective preparation and
evaluation reports, unchanged scoped Store inventories and their actual80-pools.
Keep all5 cases including the negative; no replacements or new/reserved histories.

Use `SourceOrderResolver` with positions from the immutable runtime projection,
not scoring annotations, observation-time sorting, actor alternation or resettable
transport chunk indices. In the reference index, source memory/evidence IDs and
scoped session ordinals are unique, gaps remain gaps, and returns are detached.

Expand each current80-anchor pool by at most one original message before/after
each anchor. Source order is host-provided, not a model inference. Keep base
anchors unchanged and first, then deterministic anchor-rank/distance/before-after
neighbors, deduplicated. Default caps:80 anchors,240 total,300,000 source-content
JSON UTF-8 bytes,30-second expansion timeout. No role quota, query/category/entity
heuristic, forced event merging, generated summaries or mutation of source data.

Every source is reloaded and checked for exact scope/session/evidence/current
state/actor/authority/text; invalid scope/window/position results fail closed.
Changed order/source/anchor is not returned as a successful snapshot; newly added
neighbors without a surviving anchor are discarded. Missing positions and budget
skips are explicit; no truncation, retries or unbounded fallback.

## Capacity-matched native baseline

For each case let N be the actual expanded pool count. Execute the existing
production BM25/vector equal-RRF query with limit N, no neighborhood lookup,
then the same attributed-source validation. This prevents attributing all gain
from80→N candidate capacity to source adjacency. Native RRF recomputes its wider
pool; it need not contain the exact original80 as a prefix. Match count, report
content bytes separately, flag a native byte-cap excess. Do not claim perfectly
equal compute or token budgets from equal count alone.

At most5 local query-embedding operations with the unchanged existing local
bge-small-zh512 profile; read-only vector identity/schema validation, no reindex,
new model download, BGE cross-encoder, LLM/provider calls or graph authoring.

## Preflight and execution

Entry point:`python -m benchmarks.public_memory_neighborhood_audit`.
Preflight:`data/doppel/neighborhood-audit-41-45-preflight-v1.json`.
Plan fingerprint:
`b275a998c36153b07a631e3d46c56fc9e2e5fd6f8cef69b276599ce89f23cdce`.
Run directory:`data/doppel/neighborhood-audit-41-45-v1`.
Output:`data/doppel/neighborhood-audit-41-45-live-v1.json`.

Commit code/plan before execution; require exact preflight match, exclusive
attempt/checkpoints, server-enforced read-only Store and original inventory hashes
before/after. Stop first failure, preserve all records/caches; no reset or second
automatic invocation. This code does not read API keys or create provider clients.
Do not modify old answers/scores, defaults, databases, journals or user`uv.lock`.

## Metrics and decision

Report original80 / expanded / same-N-native candidate counts, annotated-turn
coverage for four positive cases, source bytes, budget/rejection/position traces,
original anchor preservation and Store/source integrity. Keep the negative row
without a positive evidence denominator. Source IDs/turn annotations measure only
candidate availability, not fragment sufficiency, selected/packed evidence or
answer correctness. No new QA run or claim that the temporal answer is corrected.

If native widening matches/beat adjacency, record that honestly and prefer the
simpler setting unless further evidence supports adjacency. If adjacency helps,
it stays opt-in pending a separately frozen untouched comparison with selection
and QA budgets adjusted explicitly. Do not tune this window/cap on these5 cases,
keep rerunning judges, or call opened-set annotation coverage a general score.
