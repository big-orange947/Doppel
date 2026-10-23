# Final opened50 selection: BGE or fixed RRF60, then stop tuning

All50 fixed opened diagnostic questions, same80 candidates/top20/24000-byte
whole-source contexts. Reuse saved BGE baseline answers/grades and frozen fusion
source report6e6b8c91...; no retrieval, indexing, embedding, GPU reranking, graph,
source writes, new data or question-specific rules. No further weights/threshold
sweep. Commit implementation/tests/this protocol before freezing exact requests.

Unchanged ReaderV2 and provisional task judge, DeepSeek-v4-flash, JSON-object,
thinking disabled, temperature0. Reader2048 tokens, judge1024. Input/code/model
configs, original baseline requests/grades and both contexts bind before any
provider construction. Reader sees only question/reference date/attributed
context; judge sees question/reference answer/candidate answer, not profile or
old grade. Gold/annotations are never part of selection/generation input.

Maximum50 new Reader requests and50 judge requests. Independently enforced
durable reservation-before-send,100000 canonical request bytes per call/5000000
per stage. No automatic retries, output repair or rebilling; failure stops with
immutable checkpoints. Exact old Reader/judge requests reuse prior validated
outputs. Same-answer judging uses exact request identity, not answer similarity.
Fresh run/output paths; complete cache-only replay with no key/no new calls.

## Fixed decision before outcomes

Select fusion only if all100 logical rows complete, net correctness improvement
is at least **3/50**, negative-case correctness does not decrease, and structural
validity does not decrease. Otherwise select BGE. Incomplete run selects neither.
This is a conservative engineering threshold, **not statistical significance**.
No relabeling or new judging cycle to satisfy the threshold. Report gains AND
losses,43 positives/7 negatives and positive-only type breakdown, actual bytes
and paid usage. Structural legality is not semantic support or factual safety.

After selection, stop tuning on opened50. Freeze selected configuration before
preparing/running the manifest's10 reserved histories. Reserved outcomes cannot
trigger another ranking sweep; they are limited validation, not an official500
or AML score. Broader product defaults require separate deployment validation;
this decision identifies a fixed evaluation candidate, not a release gate.

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_memory_rank_fusion_qa --output data/doppel/rank-fusion-qa-frozen-v1.json
.\.venv\Scripts\python.exe -u -m benchmarks.public_memory_rank_fusion_qa --execute --frozen-preflight data/doppel/rank-fusion-qa-frozen-v1.json --run-dir data/doppel/rank-fusion-qa-live-v1 --output data/doppel/rank-fusion-qa-live-v1.json
```

No Docker/API-key file needed. The live key comes only from `DEEPSEEK_API_KEY`.
Optional read-only cache parents must contain compatible reader/judge caches;
they never change prompts/limits. Existing24KB baseline37/50 remains immutable.
