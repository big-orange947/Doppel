# Fresh scope 01: paired question plans frozen before QA

Source, vectors, full selected-scope graph and source-only relation schema are
complete and checked. This opens the first actual selected public question only
after source/graph readiness; no query/gold informed source ingestion or graph
record selection. It is prospective to this run, not independently blind.

The seven schema calls succeeded with zero missing usage, using 14,920 tokens.
All 153 distinct relation-name definitions were preserved; the graph remained
unchanged. Descriptions are fallible, not independently verified semantics.
Schema receipt SHA-256:
`603a58690740d551e07832649b1570b19772037b000cc619cacc47f860a439dc`.

Freeze the unchanged question execution:

- Query preflight SHA-256:
  `6fb9f2c5add192bdc45a4aa623a9f3a137f367fbd6c991a5f0c650a8cacc849b`.
- Full plan: `b90c76c578117b43f2f8755979f3077f43b7c7633c55609e9a1f67c4701f93cb`.
- Raw plan: `29d6c592da69a5092e076962f705025ec405c6eb9b94114c956f30ef89f27347`.
- Query adapter SHA-256:
  `c138291d3c132c857ed0b2d4fdbdcafc3e177356e02fabf8566ed932e25dbc24`.
- Source ordinal 1 / case `15745da0`: full first, raw second, per frozen alternation.
- Five full attempts maximum (2 planner + Reader + task judge + citation judge),
  three raw attempts maximum (Reader + task judge + citation judge). No retry.
- No source/graph authoring calls or source/Store/vector writes in QA.
- Unchanged local BGE embedding, CUDA `bge-reranker-v2-m3`, 8,192-token scorer
  input cap / batch 1, twenty whole final items / 24,000 UTF-8 bytes.
- Actual scorer identity: sentence-transformers `6.0.1`, raw-logit-sigmoid.
  Weight SHA-256:
  `d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286`.
  Tokenizer/config hashes are bound in both query preflight plans.
- Original S reference time and declared provided-history observation horizon;
  not a causal-replay or hidden AML question-time claim.
- Existing DeepSeek flash Reader v2 and provisional reference-only task judge;
  citation support assessed separately. No official GPT-4o/AML score.

Preflight made zero QA calls. All selected-scope source/Store/vector/graph hashes
were unchanged. Preserve each profile's retrieval and every model-stage outcome,
including failures, in separately bound run directories. Do not revise core,
config, prompts or packing after seeing this cohort's answers. One pair of results
cannot establish the fifty-case accuracy, graph uplift, or release readiness.
