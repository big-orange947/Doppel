# Scope 05: graph complete, source-only schema freeze

All 211 eligible scoped personal records have Store-bound Graphiti projections.
856 successful attempts / 3,660,896 tokens, complete usage, no retry/failure or
owned-slot repair. Store/vector/source and other cohort graph scopes unchanged.
No observed allowlisted endpoint warnings; semantic completeness is not certified.
Graph receipt SHA-256:
`19d2a399c83aea9d3d66a283b4b7eb8c156f8076ed5a6af0f83f9a525e4aa914`.

Actual snapshot: 214 distinct rich edges / 135 distinct names (writer's 222
per-episode edge associations are not 222 unique edges). Freeze before schema:

- Plan: `8f9ded892391fee44e83148cd558f9c826fb3cf0dc9cfb03b064349a0944441c`.
- Preflight SHA-256:
  `c42151ab8f65b206fca6c7d46dbbc2326e1457c3c2711ce03589460f217c9e08`.
- Rich-edge snapshot:
  `3d5c5bf63b35b3c2898b99f40ef6fdde28deef86c5a6503cd680b027a3881650`.
- Six calls maximum, 24 source names/batch, 4,096 output cap, 100,000 canonical
  bytes/call and 600,000 total. Unchanged schema source/instructions/provider,
  names only; no facts/entities/question/gold/labels. Zero Store/vector/graph
  writes, graph must stay unchanged. Preserve failures; no automatic retry.

After schema, freeze the unchanged paired query plans: ordinal 05 / `d23cf73b`,
full first then raw, five plus three calls maximum, same Reader/judges/context
caps/local BGE/CUDA reranking. Scope 06 graph can run concurrently; it writes a
different scope and verifies this one stays unchanged. No tuning, resampling,
new live calibration, official/independent/AML/publication score claim.
