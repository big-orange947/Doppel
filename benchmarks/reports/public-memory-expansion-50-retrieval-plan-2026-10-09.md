# Fifty-history LongMemEval-S retrieval comparison

Frozen before opening retrieval scores. This continues the completed fifty-history
ingestion using the existing raw / owner-memory / combined comparison harness.

## Inputs and scope

- Manifest SHA-256:
  `28dc31edbcfc119d5f952d9f0ab3ceeaa123a5e9a5bfef70f82f9febbc120721`.
- Dataset SHA-256:
  `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
- Completed ingestion report:
  `data/doppel/longmemeval-expansion-50-ingestion-block15-v1.json`, SHA-256
  `04473ccf3a9defc9709b52c2a737230fe36319a99de321da16a47b0cc832138d`.
- Journal:
  `data/doppel/public-memory-expansion-50-block04-recovery-v1/ingestion`.
- Authoritative PG schema: `public_memory_03134787d461`.
- All fifty diagnostic questions remain selected; the ten reserved histories are
  excluded by the manifest partition. No replacement or reseeding after results.
- The fixed corpus contains 24,891 raw records, 9,746 derived records including
  inactive records, and 125 governance records. Only one selected question has a
  no-answer label. Shared sessions make this a public development diagnostic.

## Harness boundary correction

The initial comparison failed before producing any row or score. Retain
`longmemeval-expansion-50-memory-comparison-v1.json`, SHA-256
`ec5ffe4e7f7130126e6f709bdf4771c174a77fa54d4544139cb4dff22a886125`.
The failed condition was the harness's assumption that every personal-memory
record is an owner record. The corpus contains five confirmed assistant-derived
records with `subject=agent`, matching agent identity and `agent_output` authority.

Keep the established owner-only memory-channel definition. Validate supported
owner and agent derivatives against subject identity, authority, source scope and
every bound raw source. After validation, omit agent derivatives from the
owner-memory channel and report their count explicitly. Assistant raw messages
remain available in raw/combined profiles with their original attribution.
Invalid identities or evidence still fail the whole run. No Store/index repair
or extraction changes are part of this correction. Synthetic tests cover valid
agent exclusion and invalid subject, identity, authority and evidence bindings.

## Fixed profiles and budgets

Run six profiles for every question: raw_vector, memory_vector, combined_vector,
and their three reranked counterparts, for 300 rows total.

Use the existing FastEmbed BGE-small-zh-v1.5 / version 0.8.0 / 512-dimensional
pgvector entries. Check each entry's authoritative fingerprint/version; fail on
missing, stale or inactive entries. Enumerate exact-scope cosine order before
channel filtering and the shared 80-candidate cap. Combined gets 80 total
candidates. This exhaustive corpus diagnostic does not establish scalable ANN
performance or deployment latency.

Reranking uses the existing local BGE-reranker-v2-m3 artifacts, CUDA, max length
8192 and batch size one. Pass question and source-bound text only. Preserve the
model artifact hashes in the report. Maximum pairs: 50 * 3 * 80 = 12,000.
Record actual pair counts and truncation; do not substitute base order if the
reranker fails.

Pack the unchanged rank prefix: at most 20 whole items and 24,000 compact JSON
UTF-8 bytes, including attribution, time and citations. Stop at the first item
that does not fit. No channel quotas, gold-conditioned changes or free source
expansion. Byte budgets do not imply matched model-token usage.

## Measures and execution

Report annotated turn/session provenance coverage in the 80-candidate pool,
rank five and packed context; state each denominator and separate the single
unanswerable case. Report all-session coverage and per-type groups. Derived
citation coverage measures source coverage, not whether summary text preserves
an answer. Revalidate all packed records and cited raw sources. Require unchanged
Store snapshot hashes before/after. Record/index writes and paid LLM calls are
zero; initialization may run idempotent schema DDL.

Retain failed artifacts. The new successful artifact path is
`data/doppel/longmemeval-expansion-50-memory-comparison-v2.json`. Use the established
GPU Python environment and local models:

```powershell
& D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_comparison `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-50-manifest-v1.json `
  --ingestion-report data/doppel/longmemeval-expansion-50-ingestion-block15-v1.json `
  --run-dir data/doppel/public-memory-expansion-50-block04-recovery-v1/ingestion `
  --output data/doppel/longmemeval-expansion-50-memory-comparison-v2.json `
  --embedding-cache-dir C:/Users/freeze/AppData/Local/Temp/fastembed_cache `
  --reranker-model-path D:/project/.doppel-eval-models/bge-reranker-v2-m3 `
  --reranker-device cuda
```

The local diagnostic DSN is loaded in-process and never stored in the report.
Reader/Judge scoring requires its own frozen request identities and budgets.
This stage provides evidence-coverage observations only; full Doppel Planner /
Graphiti, answer accuracy and AML academic-model compliance are not measured.
