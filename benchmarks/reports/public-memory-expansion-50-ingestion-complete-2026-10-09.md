# Fifty-history LongMemEval-S ingestion: complete

## Completion result

- Dataset plan:50 selected histories,2,420 source chunks,24,891 source messages.
- Final status: `complete`;2,420/2,420 chunks completed and revalidated;50/50 histories complete, zero partial and zero untouched.
- Final report: `data/doppel/longmemeval-expansion-50-ingestion-block15-v1.json`.
- Final report SHA-256: `04473ccf3a9defc9709b52c2a737230fe36319a99de321da16a47b0cc832138d`.
- Final Store audit:24,891 raw records,9,746 derived records (including inactive),125 governance records;37,454 provenance checks and zero failures.
- Final report marks `all_histories_ingested=true`, `semantic_truth_verified=false`, and `publication_ready=false`.
- Final block:66/66 calls succeeded;331,860 reported tokens;usage complete for all66;zero new failures.
- Across the full expansion, reported successful-call usage sums to12,223,006 tokens. Two transport failures in earlier bounded blocks had unknown usage; their later separately planned recovery observations succeeded. No exact billing total is claimed.

## Important evaluation boundary

This completes only dataset ingestion through the configured Doppel ingestion,
Analyzer, Miner, consolidator, and provenance checks. It does **not** run
retrieval, Reader, Judge, answer scoring, or an AML submission evaluation.
Accordingly, this report makes no recall, answer-quality, or AML leaderboard
claim. The final report also records `quality_metrics_available=false`,
`retrieval_executed=false`, `reader_executed=false`, and
`aml_academic_model_compliant=false`.

## Reproduction details

The run used the fixed 50-history manifest, local `fastembed:BAAI/bge-small-zh-v1.5`
(512 dimensions), DeepSeek `deepseek-v4-flash` extraction, JSON-object response
mode, and bounded continuation plans. Source data and plans are fingerprinted
in the JSON reports. All reports are local ignored data artifacts; this tracked
document contains aggregate results only.

Original unrelated `uv.lock` changes were not modified or staged.
