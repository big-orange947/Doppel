# Actual-request supplement: prospective five-case paired QA

2026-10-18. The [original protocol](public-memory-prospective-selection-41-45-plan-2026-10-18.md)
and implementation were frozen in commit`7a21f4f` before preparing any of these
five histories. No algorithm, prompt, case selection, budget, source cutoff or
scoring change followed the preparation. Do not inspect per-case coverage to tune
the impending model calls.

## Completed zero-LLM preparation

All5 histories/2,517 original messages are in dedicated schema
`raw_select_952e5f3593e0`, namespace
`longmemeval-prospective-selection-41-45-v1`. Per-history receipts contain full
candidate snapshots, source inventory and request hashes, and BGE baseline
contexts. No other schema, graph, journal or old cache was changed/deleted.

Existing CUDA BGE model:10 local operations/601 scored pairs,0 reported truncated
pairs, longest pair1,708 tokens against8,192 cap, actual device`cuda:0`. This is
execution metadata, not a stable-latency benchmark. Preparation paid calls0.

Prepared report `data/doppel/prospective-selection-41-45-prepare-live-v1.json`:
SHA-256 `67ae6a8221e2601e6cebd62ba20cbb4fd1e3593b57b1baf5bb9ff0f5c457f59c`.

## Actual paid-request binding, before first API call

Preflight `data/doppel/prospective-selection-41-45-evaluate-preflight-v1.json`:
plan fingerprint
`7797fd9a2a315ffbbf5dd7bc0121da39795e9aca6b08588db23522739d281de8`.
It binds the entire preparation report, identical implementation/model identities,
original scoped inventory/candidate hashes and the five actual source requests.

| Case | Canonical source selection request bytes |
| --- | ---: |
|d6233ab6|79,242|
|a96c20ee_abs|91,365|
|f4f1d8a4|72,810|
|gpt4_7abb270c|103,997|
|6a27ffc2|84,668|

All fit unchanged limits without source truncation. The later passage request is
query-selected, bounded80 fragments; exact-output caches and durable per-request
byte/call limits apply before network sends. No prior failed-selection output or
opened-case QA score is reused for these five cases.

## Execute unchanged protocol

At most30 **new** calls:10 LLM selection,10 Reader,10 provisional task judge.
Source+passage selection for five cases; both BGE and LLM contexts receive actual
QA/judging. The selector upper bound is20, not a quota; empty/fewer results are
visible, never padded. Stage caps/provider configuration/failure policy and
source→selected→packed metrics remain exactly as in the original plan. No retries
or post-result scorer calibration; stop first runtime/validation failure and
retain every billed/missing-usage attempt plus checkpoints.

Run directory `data/doppel/prospective-selection-41-45-v1`; final evaluation output
`data/doppel/prospective-selection-41-45-evaluate-live-v1.json`. Store connections
are server-enforced read-only. Environment key only, no content or credentials in
arbitrary exception text. Report four answerable cases and the predeclared
negative separately; do not count negative annotations as answer-support hits.
Span source presence is not semantic support; leave its answer-support metric
undefined. Official AML/full500/generalization/release claims remain out of scope.
