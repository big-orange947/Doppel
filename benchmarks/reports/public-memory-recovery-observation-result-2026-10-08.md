# Single-attempt recovery: pending chunk completed, no new QA score

The [plan](public-memory-recovery-observation-plan-2026-10-08.md), executable and
tests were committed/pushed as `2761a7d` before live execution. The original
ten-history arm remains stopped; this is an explicit recovery observation on opened
development data, not a replacement of its failure or an independent blind result.

## Execution and accounting

The 232 completed chunks were revalidated through the existing idempotent Store/
index path without another extraction call. The previously pending global chunk
233 completed after **one new provider attempt**, with unchanged model, prompt,
schema, generation parameters, history, scope and evidence policy. The original
and recovery request SHA-256 match exactly:
`22a4c676fc91f13b92a48328200da19c1cf92d5c0955ee8a04f2cc9a06fa2b18`.

| Quantity | Recovery observation |
| --- | ---: |
| New attempts / succeeded / failed | 1 / 1 / 0 |
| Input / output / total provider tokens | 4,048 / 6,340 / 10,388 |
| Cached / cache-miss input tokens | 3,840 / 208 |
| Reasoning tokens / missing usage calls | 0 / 0 |
| Completed prefix replay | 232 chunks |
| Completed ingestion after observation | 233/482 chunks |
| Original plus recovery calls | 234 |
| Original plus recovery reported tokens | 1,218,411 |

The one-call budget is exhausted, and the observer stopped at its declared bound.
Ingestion is still `partial`: four complete histories, 45/46 chunks of the fifth,
and five histories not yet processed. The **249 remaining chunks** were not run.
No retrieval, reranker, Reader, auxiliary Judge or QA score was executed. No
automatic retry occurred. Original billed failed usage is included, not refunded.

The successful output is now cached. The recovery ledger has no failure diagnostic
because this attempt succeeded. The earlier response hit its 8,192 token cap,
but its original finish reason remains unknown: success at 6,340 tokens does not
retroactively prove truncation or establish a transient provider root cause.

## Important coverage observation

This response has **32 schema-valid drafts**, all with subject `contact`. Its
proposals are **zero**: 24 are quarantined as `subject_source_mismatch`, eight as
`mixed_source_actors`. There are no invalid or low-confidence drafts in this chunk.
The model identifies third-party/business information, while the supplied source
actors are owner/agent, not authenticated contact speakers. Current strict
subject/source qualification therefore rejects those drafts.

Do not present this as 32 false claims caught, or as improved extraction accuracy.
This response reveals a coverage boundary: statements about third parties do not
necessarily have the same subject as their speaker. Whether a useful, attributed
third-party claim is lost must be measured separately from preventing an assistant
reply from becoming an owner fact. No source-authority rule is relaxed during this
run, and no semantic adjudication of all 32 claims was performed. All seven raw
messages remain available for the raw/combined retrieval channels; a memory-only
channel cannot retrieve these newly rejected summaries. The ten-history comparison
will quantify answer effects instead of adapting this batch to improve its score.

Post-observation inventory is unchanged: 2,420 raw records, 938 derived records
(including inactive inventory), and 11 governance records. Store audit again reports
3,646 provenance checks, zero failures, and `semantic_truth_verified=false`.
No duplicate raw/derived records were added by prefix replay. These are provenance
and counting observations, not full-sample safety/semantic guarantees.

## Preservation, validation and engineering follow-up

The parent journal and provider-output cache were verified unchanged. The child
journal was produced via SQLite backup to a fresh directory; its usage ledger is
new and independently budgeted. The existing dedicated PG schema remains
`public_memory_8704aac0e8a2`. No reset, volume deletion, Graphiti write, unrelated
Store change, prompt tuning or default retrieval change occurred. Secrets/DSNs/
headers/response body are not persisted in diagnostics. Docker was opened manually
by the owner; future unavailable-engine checks must ask the owner rather than
auto-launching Docker.

Prefix replay is noticeably expensive: the current host reconciles the entire
scope's existing index for each completed chunk. This is database/index repetition,
not 232 new model calls. A later generic recovery optimization should validate
each scope once while retaining raw/proposal/checkpoint identity and complete
index coverage, with separate tests and a new binding. This live arm did not change
validation halfway through to reduce runtime. No latency benchmark claim is made.

Final verification: **1,283 passed / 33 skipped / 3 subtests passed**, one existing
upstream Graphiti/Pydantic deprecation warning; targeted tests 71 passed. Whole-repo
Ruff passed, changed Python files formatted, scoped Pyright zero errors/warnings.
The 18 added tests cover closed diagnostics, unknown legacy failures, prefix/parent
binding, clone preservation, strict one-call caps, no rebilling and aggregate cost.
The user-owned `uv.lock` remains unchanged and unstaged.

Ignored result: `data/doppel/longmemeval-recovery-observe-live-v1.json`, SHA-256
`872d7e3142a49b50799056c22f4d3597404a5234bf7fa1ff7af4a25244d0c9e9`.
Run directory: `data/doppel/public-memory-recovery-observe-v1`; bound recovery plan
fingerprint `2613ff21946f7278fe8ab5be6335fcf91ed4307e891bb36a09543f04e3ab739a`.
Runtime commit `2761a7d`; only pre-existing `uv.lock` was tracked dirty at execution.

Next: separately bind continuation for the same remaining 249 chunks, reuse the
233 successful checkpoints/outputs without regenerating them, retain all parent
costs and stop on failure. Only complete histories/index checks unlock the frozen
three-channel retrieval/Reader comparison. This observation completes its scope;
it is not new recall evidence, a full LongMemEval result or an AML score.
