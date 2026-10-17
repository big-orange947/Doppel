# Context budget changes the raw retrieval conclusion

The read-only audit of all twenty fixed histories /160 saved retrieval rows is
complete. Under the unchanged 24,000-byte whole-prefix packer, **BM25/vector
reranking falls from27/27 to23/27 annotated answer-support turns**. Vector
reranking retains25/27; BM25/vector without reranking also retains25/27.
This is a context-selection diagnostic, not an answer-quality result or new core
algorithm. It does not establish that reranking should be removed generally.

## Frozen setup and complete results

Use the original ordinals11–30, full S histories, exact previous ranking positions
and existing context serialization. All9883 raw messages are checked against
source transport events, roles, authority, text and observed dates. Read-only
PostgreSQL sessions perform no ingestion, migration, repair or index operations.
No retrieval/model is rerun. The byte budget includes context metadata, not only
message text. Keep at most20 whole items, stopping at the first overflow; do not
skip long items, truncate, summarize, expand neighbours or inspect gold to pack.

Primary denominator remains **17 answerable questions /27 labelled turns**.
The three predeclared negative questions remain in execution/overflow counts,
not answer-support recall; their related-history annotations are not answers.

| Fixed profile | Before packing /27 | After packing /27 | All required after /17 | Overflow rows /20 | Mean packed items /20 questions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Legacy whole-query substring | 0 | 0 | 0 | 0 | 0 |
| Local vector | 21 (77.8%) | 21 (77.8%) | 12 | 4 | 19.30 |
| Legacy substring + vector | 21 (77.8%) | 21 (77.8%) | 12 | 4 | 19.30 |
| BM25 | 25 (92.6%) | 22 (81.5%) | 14 | 18 | 14.35 |
| BM25 + vector | 25 (92.6%) | 25 (92.6%) | 15 | 9 | 17.60 |
| Local vector + reranker | 25 (92.6%) | 25 (92.6%) | 15 | 17 | 12.80 |
| BM25 + reranker | 27 (100%) | 22 (81.5%) | 13 | 20 | 8.60 |
| BM25 + vector + reranker | 27 (100%) | 23 (85.2%) | 14 | 20 | 9.60 |

The preceding top-twenty result is not invalidated: those evidence turns really
were retrieved. The additional measurement establishes that some do not reach
the supplied context under this fixed benchmark packing policy. This policy is
not a requirement that every Doppel integration use the same context manager.

## Where the hybrid-reranked evidence is lost

| Opened case | Packed items | First excluded rank | Packed bytes | Labelled turns excluded |
| --- | ---: | ---: | ---: | --- |
| `gpt4_e414231e` | 8 | 9 | 22,034 | session1/turn0 |
| `5a7937c8` | 8 | 9 | 22,032 | session22/turn0 and session5/turn0 |
| `1d4e3b97` | 8 | 9 | 20,372 | session40/turn2 |

Positions are zero-based source occurrence ordinals, not ambiguous repeated
session-name strings. These are all four lost annotated turns in this profile.
No claim is made that the excluded message itself is oversized: an earlier item
can cause packing to stop before a later evidence item is considered.

All twenty hybrid-reranked contexts overflow. Their complete retrieved twenty-item
contexts average44,855.9 bytes and only9.6 items fit on average. Vector-reranked
twenty-item contexts average33,802.5 bytes, retaining12.8 items. The observed
rankings select different-length material; this alone does not prove a universal
length bias of the reranker. No causal model ablation or post-result tuning ran.

BM25-reranked loses five turns across four answerable questions; hybrid-reranked
loses four across three. BM25 without reranking loses three across two questions.
No positive labelled turns are lost in vector, vector-reranked, legacy hybrid or
unreranked BM25/vector packing, despite some of their contexts overflowing.
Overflow count alone is therefore not a quality metric.

## Accounting, reproducibility and boundary

- Paid LLM calls0, provider tokens0, graph calls0, GPU/model execution0.
- Each of20 source inventories has identical before/after hashes; total9883
  records. No source/role/authority mismatch or score/ranking mismatch occurred.
- A second independent read-only invocation reproduces the **entire JSON report
  byte for byte**. It is an audit replay, not a new retrieval or QA run.
- Existing retrieval receipts, graph data and the dirty `uv.lock` are preserved.
- The fourteen new offline tests include exact UTF-8 byte boundaries,
  first-overflow/no-skip behaviour, unchanged input text, tampered row rejection,
  negative denominator separation and plan/source bindings. Ruff passes.
- Full regression suite: **1,890 passed, 33 skipped, three subtests passed** in
  202.04 seconds; one existing Graphiti/Pydantic deprecation warning remains.

No Reader/judge means no new answer correctness, groundedness or abstention score.
Whole-message annotation coverage is not the only measure of useful context.
These are twenty opened public histories, not independent blind data, full500,
AML or release acceptance. No repeated idle-GPU latency benchmark was performed.

## Next bounded experiment, not a changed default

Do not buy more whole-history graph construction to fix a loss occurring after
retrieval. First compare generic budget-aware evidence selection with the frozen
prefix baseline. An existing whole-item skip-to-fit policy can be an explicit
experimental arm; it must not silently replace this baseline or receive gold.
It can also fail when important evidence is individually too long, so no gain
should be assumed. Do not enlarge the budget and present it as an algorithm gain.

If a new selection policy is developed on these opened cases, test it on a new
untouched frozen continuation before spending on a small paired QA check.
Broader agent context-management architecture remains out of scope: the immediate
goal is a trustworthy, budgeted evidence handoff for memory-framework evaluation.

## Artifact bindings

Code/plan frozen before execution at `c3bedf5`.
See [frozen plan](public-memory-raw-packing-11-30-plan-2026-10-17.md) and
[parent retrieval result](public-memory-raw-retrieval-11-30-result-2026-10-17.md).
Local ignored artifacts:

- `longmemeval-raw-packing-11-30-preflight-v1.json`:
  `72a8bd4a3946867ab6cd41249248c6a20d1dfaaba28ac3eb1ea68ac63cc89ea8`.
- Plan fingerprint:
  `3d30bacb97a6b61e5fdeba9f279b5f1ff30a7aa8fdd2bb506106be9373d8623e`.
- `longmemeval-raw-packing-11-30-live-v1.json` and
  `longmemeval-raw-packing-11-30-replay-v1.json`, identical SHA-256:
  `4dfa62446a90f61f8bfe0a1ca3648017a6d969b1cc827c3838c9d30309360b9f`.
