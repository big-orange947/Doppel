# Frozen read-only context-packing audit: original ordinals 11–30

Audit all 160 rows from the completed twenty-history raw retrieval expansion.
No new selection, ranking, embedding, reranking, extraction, graph, Reader, judge
or paid-provider execution. This is a post-retrieval diagnostic on opened public
questions, not a new independent retrieval test or QA accuracy measurement.

Read the existing dedicated raw schema through `ReadOnlyStore` with PostgreSQL
`default_transaction_read_only=on`; no migrations, ingestion, repairs or reindex.
Bind all original messages against deterministic transport events and source
positions, preserving role, authority, observed time and full text. Verify Store
inventory hashes before/after each history. Parent source bytes, complete row set,
block receipts, scoring snapshots and unchanged runtime-source hash must match.

Use unchanged `public_memory_comparison.context_item`, `encoded`, `pack_context`:
at most20 whole ranked items, at most24,000 UTF-8 serialized JSON bytes, stop at
the first item that would overflow. No truncation, skip-to-fit, compression,
gold-conditioned selection, neighbour expansion or larger budget. Metadata counts
toward the byte limit. Scoring labels are passed only to scoring, not packing.

Report per-row before/after annotated-turn coverage, packed counts/bytes, first
excluded rank, lost annotated positions and packed-context hash. Primary aggregate
is seventeen answerable questions /27 labelled turns; preserve the three negative
rows separately, excluding their related-history annotations from answer-support
recall. No Reader means no answer or abstention accuracy. Do not tune after viewing
results. No GPU/latency experiment or graph cleanup. No previous artifact overwrite.

Bindings:

- Retrieval report SHA-256:
  `10c09984b30b9a89d657b8929bc9f7e2374849338d2c0767a2195b4009db7f4f`.
- Frozen preflight `longmemeval-raw-packing-11-30-preflight-v1.json` SHA-256:
  `72a8bd4a3946867ab6cd41249248c6a20d1dfaaba28ac3eb1ea68ac63cc89ea8`.
- Plan fingerprint:
  `3d30bacb97a6b61e5fdeba9f279b5f1ff30a7aa8fdd2bb506106be9373d8623e`.
- Fourteen offline tests pass, including first-overflow behaviour, UTF-8 boundary,
  missing/duplicate/changed ranking rejection and negative-case separation.

Freeze the plan/code before read-only execution. The local report remains under
ignored `data/doppel/`. Preserve `uv.lock` and all existing graph/source receipts.
