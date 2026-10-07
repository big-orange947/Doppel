# Opened LongMemEval pilot: raw / memory / combined retrieval

This plan is fixed before this comparison's scores are opened. The three questions
are already diagnostic, not blind or representative of all 500 cases. No selection,
prompt, alias, channel quota or cutoff will change after seeing these scores.

## Corpus and search

- Same manifest `6f9f0193…`, completed ingestion plan `7c9e31e4…`, schema
  `public_memory_7c9e31e426b2`: all 1513 raw messages, 599 derived memories and four
  governance records. Governance is audited but not returned as a claim.
- Read-only completion/source journal; verify the original transport projection,
  complete histories, exact source text/role/time and derived owner citations.
  Compare authoritative Store snapshots before/after. Do not reingest/reindex.
- Same existing FastEmbed BGE-small-zh-v1.5 / 512-dimensional pgvector profile.
  Verify every existing vector entry's authoritative fingerprint/version.
- Enumerate the small exact-scope corpus in production vector cosine order, then
  take 80 candidates for raw-only, memory-only or their single combined order.
  Combined receives **80**, not 80 per channel. This exhaustive diagnostic is not
  the production query engine, ANN scalability or latency evidence.
- Run each channel without reranking and with the already configured local
  BGE-reranker-v2-m3, CUDA, max length 8192, batch size one. Same plain question and
  authorized item text only; no labels, category, answers or annotated sources.
- Final rank prefix: at most 20 whole items and 24,000 bytes of compact UTF-8 JSON,
  including role, authority, time and citation overhead. Stop at the first item
  that does not fit. No gold-conditioned dropping or free source expansion.
  Byte equality is **not** equal tokenizer usage; reader token budgets will need
  a separate check. Raw messages and summaries are different item units.

## Metrics and limits

Report annotated source-turn/session coverage in the candidate pool, rank five
and packed output. Deduplicate citation positions. Derived-memory citation
coverage is **not** proof that the summary preserved the answer. Raw assistant
text remains attributed agent_output context, never an owner fact. All final
items and cited raw records are reloaded after ranking; changes fail the run.

No new extraction calls, LLM Planner, graph candidate search, source expansion,
reader, QA judge, reserved group or AML-model profile in this run. Keep all failed
and successful artifacts. Next: inspect missing information, then freeze and run
the same reader and judge on the packed channels without leaking gold to either
retrieval or the reader. Do not publish this pilot as full-benchmark performance.
