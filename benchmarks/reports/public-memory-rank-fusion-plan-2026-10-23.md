# Fixed local retrieval/reranker rank-fusion comparison

All50 opened diagnostic LongMemEval cases, exact previously saved80 candidate
IDs/order. No new question selection, corpus generation, retrieval, query/document
embedding, source expansion, graph, extraction, Reader or paid API. Read-only
PostgreSQL supplies original source objects under server-enforced read-only
transactions. No Docker start/restart or database repair/reset.

Three declared arms: original retrieval order (diagnostic control), unchanged
content-only BGE order (baseline), and **one** equal-weight RRF60 fusion of these
two complete rankings. No weight/k sweep, thresholds, metadata/MMR/role quotas,
length or date boost, task/answer-specific rules. Same final20 sources and whole-
item ranked-fit24000 UTF-8 JSON bytes in all arms. All50 remain included.

Same BGE-reranker-v2-m3 artifact/runtime as the window80/160 experiment, CUDA
batch1/max8192, raw text only. Score each fixed80 once: maximum50 calls/4000 pairs;
both baseline and fusion use that full order. Fresh baseline must reproduce old
top20 and24KB context exactly in every case; otherwise stop, preserve failure,
do not adjust model/runtime or replace a question. This is a bounded local
inference run, not a zero-model calculation or a stable latency measurement.

Validate original full Store corpus digest, source/scope/provenance before model
work, then revalidate all three final20 selections and the full corpus after each
case. Input/dataset/code/parent plans/model hashes freeze before execution. Store
sources and previous results/caches remain unchanged. Persist all80 complete
source objects and full neural/fusion rankings, not just20 truncated receipts,
so later rank analysis need not rerun local inference. No silent retries.

Only after selection/packing, compute annotation coverage.43 positives/76 source
annotations; negatives excluded from positive denominator, retained in operational
totals. Report top20/packed counts, complete-positive count, paired recovered AND
displaced annotations, source count/bytes and source-validation/model usage.
Do not claim answer accuracy, semantic sufficiency or security scores from source
annotations. No answer/grade rescore or automatic runtime/service default change.

Original source-order top20 contains61/76 annotations versus BGE66/76. Of6
candidate annotations outside BGE top20, initial retrieval ranks are27 (case40),
22/38 (case41),35/1/7 (case44). This opened-data diagnosis motivates retaining an
independent retrieval signal; these case IDs/ranks do not enter the algorithm.
RRF60/equal weights is fixed before new neural scores/fusion outcomes; report
failure as-is instead of searching alternatives. Prior metadata/MMR, paid LLM
selection, neighborhoods and capacity experiments remain separate, not repeated
as if untested.

This is opened development, not independent/official LongMemEval500 or AML,
publication readiness or a release gate. A promising annotation result would
still require a separate frozen downstream QA comparison before promotion.
No new paid QA is authorized by this local-only protocol.

```powershell
D:\project\.doppel-eval-cu128\Scripts\python.exe -m benchmarks.public_memory_rank_fusion --output data/doppel/rank-fusion-preflight-v1.json
D:\project\.doppel-eval-cu128\Scripts\python.exe -u -m benchmarks.public_memory_rank_fusion --execute --frozen-preflight data/doppel/rank-fusion-preflight-v1.json --run-dir data/doppel/rank-fusion-local-v1 --output data/doppel/rank-fusion-local-v1.json
```

Commit this protocol/implementation/tests before freezing the actual preflight.
All output/run paths must be new. No key needed; key environment variables are
removed in the executing child process before source/model work.
