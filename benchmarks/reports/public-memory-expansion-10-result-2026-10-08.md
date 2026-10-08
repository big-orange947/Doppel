# Ten-history expansion: live ingestion stopped before retrieval

The implementation and experiment plan were committed and pushed as `e1fa179`
before paid execution. This run actually started production extraction/ingestion
on ten newly selected public LongMemEval-S history groups. It **stopped at the
233rd extraction attempt**. There is no new retrieval, Reader, Judge or QA result.
The four completed histories are not substituted for the frozen ten-history arm.

See the [frozen plan](public-memory-expansion-10-plan-2026-10-08.md) for selection,
full-history protocol, model identities, channel budgets and measurement boundaries.
This is public development data, not an independent blind test or AML result.

## Actual execution

| Stage | Frozen work | Actual result |
| --- | ---: | --- |
| Full-history extraction/ingestion | 482 chunks, 5,037 raw turns | 233 attempted; 232 completed; stopped on extraction |
| Three-channel reranked retrieval | 10 questions x 3 profiles | Not executed |
| Reader v2 | At most 30 new attempts | Not executed; no answer-stage ledger created |
| Auxiliary Judge | At most 30 new attempts | Not executed |
| Complete-run key-free replay | After completion | Not executed; run incomplete |

Completed histories, in fixed order: `gpt4_2312f94c` (45 chunks), `07741c45`
(49), `3a704032` (48), and `0e5e2d1a` (46). The fifth, `86f00804`, has
44 of 46 chunks complete. Its next chunk is global ordinal 233: original session
index 41, turn indices 0–6. Its seven raw events are persisted, but no analysis
observation, proposal plan or consolidation plan exists for that chunk. The last
chunk of that history and the five remaining histories were not processed.

232 successful structured outputs remain in the ignored provider-cache directory;
no output is cached for attempt 233. No automatic retry, paid repair, case swap,
history truncation, prompt change or partial-history scoring followed the failure.
The existing database schemas, old caches/answers and reserved histories were not
modified by this experiment. The new schema and journal are retained for diagnosis.

## Failure evidence and limits of diagnosis

The ingestion report preserves `stage=extraction`, `code=stage-execution-failed`
and write key
`f36cf658b5f8f7feedfb230b9a8b9211841cf33a9acfd81f30a312f0c9b5badd`.
Read-only inspection of the durable call ledger identifies failed call 233, request
SHA-256 `22a4c676fc91f13b92a48328200da19c1cf92d5c0955ee8a04f2cc9a06fa2b18`.
Its provider-reported usage is **4,048 input / 8,192 output / 12,240 total tokens**.
The output equals the frozen completion cap exactly, with zero reasoning tokens.

The provider observes usage only after a successful HTTP status and decoded response
envelope, before validating finish reason and structured content. The ledger marks
this attempt failed inside provider generation, before the raw-output cache returns.
Thus a response was received and accounted for; this is not evidence of a connection,
Docker or no-key failure. Output truncation is the leading explanation, but the
retained artifacts do **not** include the HTTP finish reason or failed raw content.
An invalid content/response shape remains possible. Do not claim a confirmed
`finish_reason=length`, an exact JSON syntax defect, or an account-balance diagnosis.

The privacy-oriented runtime currently redacts the provider exception to a generic
failure and caches only successfully parsed outputs. This is an observability gap:
safe closed error codes and finish metadata could have distinguished truncation
from invalid JSON without exposing secrets or arbitrary response text. No source
change was made after the failure to rewrite this experiment's meaning.

## Accounting and source audit, not quality scores

233 new attempts: 232 succeeded, one failed, zero interrupted/reserved; no retry.
All 233 have complete usage, including the failed call:

| Provider-reported quantity | Total |
| --- | ---: |
| Input tokens | 1,079,040 |
| Output tokens | 128,983 |
| Total tokens | **1,208,023** |
| Cached input tokens | 208,768 |
| Cache-miss input tokens | 870,272 |
| Reasoning tokens | 0 |
| Calls without usage | 0 |

The durable attempt/byte caps were respected. This is usage accounting, not an
exact RMB cost or hard total-token cap. Reader/Judge calls are zero because those
stages were never reached, not because missing provider usage was treated as zero.

The 232 completed chunks contain 985 analyzed drafts: 984 pass draft validation,
one fails with `value_error`. Evidence qualification quarantines 45 valid drafts:
33 `subject_source_mismatch`, 12 `mixed_source_actors`. One additional draft is
below the frozen confidence threshold; none are counted as duplicate drafts.
These rejection observations are preserved and raw source messages remain intact.
They demonstrate enforcement/counting, not that every rejection is semantically
correct or harmless to answer coverage. The failed chunk has no observation and
is not interpreted as zero rejected drafts.

The post-stop Store audit reports 2,420 raw records, 938 derived records (inventory
including inactive), and 11 governance records. All 3,369 records in this partial
inventory have confirmed state; actor counts are owner 2,148 and agent 1,221.
Confirmed raw agent outputs remain agent-attributed, not owner facts. There are
3,646 provenance checks and **zero provenance failures**. The audit explicitly
sets `semantic_truth_verified=false`: provenance does not certify extraction
accuracy, temporal reasoning, retained answer information or retrieval performance.
This is not a complete-ten-history isolation/quality proof.

## Reproducibility and retained artifacts

- Runtime commit: `e1fa179c63bbe00bdbf9a27bd7cdc7e8bad2a4f1`;
  runtime tracked dirty path: only the pre-existing user-owned `uv.lock`.
- Expansion plan fingerprint:
  `0ae31fe478f99db46bed770caf2b8e2cdc751220895c76a1ef2bbb07971869b7`.
- Ingestion plan fingerprint:
  `8704aac0e8a2da75afbca02f43d5cf305c1bf4dca618c90bc3313287e4b7e7c6`;
  dedicated PostgreSQL schema: `public_memory_8704aac0e8a2`.
- Outer report: `data/doppel/longmemeval-expansion-10-live-v1.json`, SHA-256
  `23134afe448bb90b02d733e13a22d791dfe4313221b51e8173ba54892ca3cdea`.
- Stage report: `data/doppel/public-memory-expansion-10-v1/ingestion-live.json`,
  SHA-256 `48db227c90f8c908d26981fd630adbd5b2b0603260851def4ad99d6970a4ad2a`.
- The run directory retains the bound plan, `ingestion/usage.sqlite3`,
  `ingestion/ingestion.sqlite3` and provider-output cache. No retrieval or answer
  report exists. Local artifacts/source content remain ignored, not committed.
- Secret values/authorization headers/DSNs were not printed or persisted. Named
  diagnostic-container credentials were used only in-process. No database reset,
  volume deletion, Graphiti write or default retrieval-strategy change occurred.

Before live execution: full suite **1,265 passed / 33 skipped / 3 subtests passed**,
with one upstream Graphiti/Pydantic deprecation warning; whole-repository Ruff
passed, changed Python files passed formatting, scoped Pyright had zero errors.
The sampler preserves the old default manifest and excludes all six old exact
history groups; the new tests cover three-profile completeness, partial-run stops,
fixed budgets, source binding and inactive-index lifecycle checks. Unit-test success
did not guarantee this real-model output would complete.

## Next bounded recovery, not executed here

First preserve safe provider failure metadata (closed error code, HTTP status,
finish reason and usage) in a separately tested runtime revision. Never persist
arbitrary exception text, API keys, authorization headers or transport configuration.
Do not retroactively fill unknown metadata for call 233.

Then preregister a recovery plan for the **same ten histories** with explicit new
request/budget identities wherever settings change, provenance-bound read-only reuse
of the 232 successful outputs, and aggregate original plus recovery costs. The first
bounded live step should establish that the failed chunk can complete under the
declared general recovery policy, without case-specific prompt rules. If it cannot,
stop and retain that failure rather than silently removing the question. Do not
blindly increase the cap or retry until the relevant failure can be observed.

Only after all 482 chunks and source/index checks complete should the frozen
three-channel retrieval/Reader comparison run. Any resumed run must be labeled a
recovered development diagnostic, not the original uninterrupted arm or an unopened
blind evaluation. No new recall/QA conclusion is available from this stopped run.
