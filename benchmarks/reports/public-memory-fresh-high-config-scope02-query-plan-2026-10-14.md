# Fresh scope 02: paired QA frozen before model calls

The full source graph and source-only name schema completed without retry;
five schema calls used 10,607 tokens, preserved all 119 names and left the graph
unchanged. Schema receipt SHA-256:
`39b8c53cac5341768ee41ccd32760fed2033293a6e050f2c338a89bed12814d6`.
Scoped source/Store/vector/graph hashes and all 165 projections were rechecked.

Freeze the existing unchanged two-profile protocol before paid QA:

- Query preflight SHA-256: `18aabfcd0c16c04a00b597b179987bc85eaf0b2859f843cdf9b0d8c0393d031e`.
- Full plan: `e10f300313d541901dc92f6d1859d862c5b244e34c29e5088df0a3a504fb4797`.
- Raw plan: `df2d8c1762596c726ddf3bfa73af62be47e5f78968e39ba9cf65b5f23586604d`.
- Fixed case `gpt4_d31cdae3`, ordinal 2, raw first / full second.
- Full attempt ceiling five: 2 natural V7 planner + Reader v2 + reference-only
  task judge + citation judge. Raw ceiling three: the same answer/judge stages.
- Byte-identical V1 query adapter, source SHA-256
  `c138291d3c132c857ed0b2d4fdbdcafc3e177356e02fabf8566ed932e25dbc24`.
- Same source-bound local 512-dimensional BGE embedding and CUDA
  `bge-reranker-v2-m3`, 8,192 input cap / batch 1 / actual weights/tokenizers bound.
- Same twenty-whole-item / 24,000 UTF-8-byte caps, full cyclic memory/raw/backing
  vs strong raw reranked-prefix comparator, original S reference date and declared
  provided-history horizon. No answer-aware packing or causal-replay claim.
- Same DeepSeek flash/json_object/temperature 0/thinking disabled, stage output
  caps, Reader and provisional judges. No automatic retries, new controls or tuning.
- Zero record/index/graph writes; preserve retrieval and failed model checkpoints.
- Exact empty-key checkpoint replay under the separate existing receipt observer
  may verify outputs without overwriting original live profile receipts.

Graph authoring for scope 03 is independently frozen and can continue concurrently:
scope 02 QA is read-only. Its original query/gold did not enter graph/schema.
The selected fifty-case denominator and all prior results remain unchanged.
This is not an independently blind, official LongMemEval, AML or publication score.
