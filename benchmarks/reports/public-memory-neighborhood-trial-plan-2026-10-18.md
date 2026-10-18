# Prospective native vs source-neighborhood QA: ordinals46–50

Frozen before source preparation or provider calls. These are the final five
diagnostic histories in the existing fifty-history parent manifest, not the ten
reserved histories. Selection uses parent order only: no replacement, looking at
gold to choose a case, or opened-example parameter tuning. Public LongMemEval S
data may have been seen by the model; this is not an independent blind benchmark,
an official LongMemEval score, an AML score, or a publication/release gate.

## Fixed protocol

- Raw ingestion plus existing local bge-small-zh-v1.5/512 vectors only. New schema;
  no graph construction, LLM extraction, summarization, or deletion of old data.
- Original80 production BM25/vector RRF candidates; optional source neighborhoods
  at explicit original-session ordinal±1, max240 candidates/300000 formatted
  content bytes. Preserve all original anchors; host source order is trusted.
- Native baseline recomputes production retrieval at the actual expanded count N.
  Require identical counts, not identical byte sizes. Record request bytes and
  expansion caps/rejections. No claim that equal counts imply equal cost.
- Both arms: same bounded selector, model, metadata/instructions and limits:
  max240 offered candidates,350000 source-input characters, source selection≤20;
  lossless1200-char/160-overlap spans, round-robin≤80; same selector≤20 passages;
  ranked-fit packing≤24000 bytes. No hidden old80 truncation, speaker quotas,
  score threshold, role/entity/question-specific exceptions, or forced padding.
- Fixed arm order native then neighborhood. Source request hashes are frozen in
  the completed zero-LLM preparation before any paid call. They contain question
  and authorized evidence, never gold, profile labels, annotation positions or
  prior judgments. Evaluation uses server-read-only Store and frozen candidates.
- Unchanged Reader v2 and provisional DeepSeek task-accuracy judge. Citation
  legality is not support. Source-ID coverage is not fragment entailment. Report
  full annotated source text retained in packed spans separately from QA accuracy.
- Hard caps: selector≤20 calls (1024 output tokens each), Reader≤10 (2048),
  judge≤10 (1024), total≤40. Selector request≤600000 bytes/12000000 cumulative;
  Reader/judge≤100000 bytes each/1000000 cumulative per stage. These bound
  attempts/bytes, not monetary billing. Temperature0, thinking disabled, no
  retries, output repair or automatic budget extension. Empty stages may make
  fewer calls. Durable ledger, per-stage caches and per-row checkpoints retained.

## Decisions and reporting

Primary: paired final task accuracy, per-case successes/regressions and reasons.
Secondary: candidate/selected annotated-turn presence, packed full-turn retention,
actual context/source request bytes, provider tokens/calls and scope/provenance
checks. Negative questions do not inflate positive evidence coverage. With five
cases, no significance/generalization claim or default promotion is allowed.
Do not merge these results into the earlier opened41–45 audit or rescore it.

An interrupted or invalid paid response stops the run and is retained. Any
recovery would require a separate frozen allowance, not a silent repeat. Source
preparation is zero paid; a failed/partial schema is preserved, never reset.

Initial preparation preflight: five histories/2483 source turns, schema
`raw_neighbor_f922530685b6`; plan fingerprint
`08d2faa24367ea53eb21328ba0b1b12107242ec8b1673c94a75ae61ee43dc65c`.
Local report: `data/doppel/neighborhood-trial-46-50-prepare-preflight-v1.json`.
Eleven offline runner tests pass, including a real Store100-source test proving
that the identical frozen preview reaches the selector without an80-item crop.

Runner: `python -m benchmarks.public_memory_neighborhood_trial --phase prepare`
with fresh `--run-dir` and `--output`; first emits a preflight, then `--execute`
requires its exact `--frozen-preflight`. Evaluate similarly, with the completed
`--preparation` report. Keys are environment-only and never written into reports.
