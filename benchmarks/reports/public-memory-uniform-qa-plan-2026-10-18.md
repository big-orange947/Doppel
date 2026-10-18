# Uniform low-cost QA baseline: fixed ordinals11–40

Freeze before paid calls. Finish the27 histories which have retrieval diagnostics
but no final answer; then run the already-opened32/37/40 using the same rules.
All30 cases must contribute, including failures. This is opened development data,
not independent validation, full50, official LongMemEval, AML or highest-config
performance. Ten reserved histories stay closed. No outcome-based replacements.

## Protocol

Reuse exact saved production BM25/vector RRF candidate80 and local BGE-reranked
top20 source order, whole-message ranked-fit24,000 UTF-8 JSON bytes/max20 items.
Both original batches must have the same reranker identity. Reconstruct all
contexts from original runtime/session/turn mappings and read-only Store records;
require exact prior context hashes and selected positions. Preserve source role,
authority and timestamps. Revalidate corpus before/after preparation and QA.
No new retrieval, embedding, reranking, ingestion, graph, LLM selection, splitting,
summarization, scope/role quotas, scenario-specific rules or production changes.
This intentionally measures the existing affordable baseline, not the newer
whole-pool LLM selector whose input cost dominated the preceding experiment.

Same unchanged Reader v2/attributed context payload and provisional DeepSeek
task-accuracy judge. Reader sees only question/date/context, never reference,
labels or prior grades; judge sees question/reference/answer but no profile or
old grades. No judge recalibration, rescoring to pass, or Reader prompt changes.
Preparation freezes all30 exact Reader request hashes before paid execution.

Paid caps: Reader≤30 calls/max2048 output tokens; judge≤30/max1024; total≤60 new
calls, no retries/repair/automatic extension. Each stage request≤100000 canonical
bytes and cumulative≤3000000 bytes. Environment-only key, durable attempt ledger,
content-addressed stage cache and per-row checkpoints. First failure stops and is
retained; any recovery requires separate explicit frozen authorization. Billing
is not inferred from token counts. Source preparation incurs zero paid calls.

## Reporting

Report30-item provisional task accuracy,26 positive and4 negative questions
separately, by source question type, and27 previously-unanswered vs3 opened
diagnostic questions. Distinguish retrieval/packing omissions from answer-use
failures using unchanged annotations and actual answers; don't equate legal
citations with semantic support or full-turn annotation absence with no usable
evidence. Report actual tokens/calls, stage errors and source integrity checks.
No stable p50/p95 latency claim; no "50 current-version questions complete" claim.

After this run, all50 distinct histories will have at least one answer only if
all27 new items finish. A genuinely uniform50-item score still requires bringing
the other20 histories onto the same frozen baseline, not summing old best arms.
Keep that distinction explicit in the next report.

Runner: `python -m benchmarks.public_memory_uniform_qa --phase prepare` and then
`--phase answers --preparation ...`; both execute only against their exact frozen
preflight, with fresh output paths. Artifacts stay under ignored data/doppel.

Preparation preflight fingerprint:
`0fa037867d3f44e41316aef618f3e4266bde735857211e06ded36b7e94875b4f`.
Local file:`data/doppel/uniform-qa-11-40-prepare-preflight-v1.json`.
Eleven offline tests pass, including a real Store/fake-provider end-to-end check
that Reader input excludes gold and only judge input includes the reference.
New runner Pyright has zero errors; Ruff passes. No paid calls made at freeze.
