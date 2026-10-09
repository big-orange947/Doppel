# First complete diagnostic history: real Graphiti projection results

**Completed:** all 210 eligible memories in the first ingestion scope have real
production graph projections, and post-authoring provenance checks pass. **Not
completed:** natural-query high-configuration QA, the other 49 scopes or AML.

No question/reference answer entered source selection or graph authoring. No
core retrieval algorithm, case-specific dictionary, source memory, vector contents,
reserved history, old score or `uv.lock` was changed by this work.

## Coverage after all writes

The final read-only audit independently rechecks every selected Episode's
fingerprint/version and actual linked edges after later Graphiti merges:

| Measure | Result |
| --- | ---: |
| Selected authoritative memories | 210 |
| Complete matching projections after authoring | 210 |
| Memories with at least one non-fallback relation | 140 (66.7%) |
| Memories with only fallback projection | 70 (33.3%) |
| Distinct non-fallback graph edges | 229 |
| Non-fallback Edge/Episode link incidences | 231 |
| Source-anchored v2 relation/path probes | 231 passed / 231 |
| Post-authoring audit/provider calls | 0 |
| Full Store snapshot changed | No |

The 231 links are not 231 distinct edges, nor a recall denominator. Fallback
coverage preserves an index entry but contributes no rich relationship to the
focused relation adapter. Graphiti occasionally discards a proposed edge whose
entity was absent from the extracted node list; completed projections therefore
do not imply complete or semantically correct relationship extraction.

## Preserved failures and corrected interface check

The first large run remains **partial at 146/210**, with its original 601 successful
attempts and 7,999,092 canonical bytes preserved against the 8,000,000-byte ceiling.
It exposes a Graphiti wrapper failure rather than a nested budget reason. The
separately frozen continuation performs 64 new writes, reuses 146 projections and
completes all 210. Its parent receipt/ledger/cache binding is unchanged; two exact
requests hit the read-only parent provider cache. No old budget was modified.

The original post-authoring probe v1 also remains failed: 25 exact-edge-selection
checks do not match. Read-only follow-up on **all 25** establishes that each expected
memory and Episode provenance is returned through another representative edge.
This is existing per-memory deduplication in the relation API, not failure to
retrieve those memories. Frozen v2 checks the per-memory contract, retains all 25
old edge-selection observations and returned representative IDs, and still demands
the individual edge in a provenance-correct one-hop path. It passes all 231 probes;
no production retrieval algorithm or source fact was changed to obtain this result.

These probes intentionally know the stored source anchor, fact text and type. They
prove production adapter connectivity/provenance, **not natural-language planning,
recall@k, time reasoning, multi-hop reasoning, graph-fact accuracy or answer quality**.
Other scopes currently lack projections, so the negative cross-scope checks are not
a populated multi-owner/adversarial security benchmark.

## Paid authoring accounting, including all parents

| Run | New provider attempts | Reported input | Reported output | Reported total |
| --- | ---: | ---: | ---: | ---: |
| Three-record smoke | 8 | 19,112 | 403 | 19,515 |
| First-history parent (partial) | 601 | 2,460,447 | 39,310 | 2,499,757 |
| Explicit continuation | 259 | 1,098,951 | 18,090 | 1,117,041 |
| **All authoring of this scope** | **868** | **3,578,510** | **57,803** | **3,636,313** |

All admitted attempts succeeded; zero retries, interrupted attempts, invalid cache
entries or missing usage. Provider-reported cached input is 1,574,400 tokens and
cache-miss input is 2,004,110 tokens; reasoning is zero. Tokens are not an exact
currency-charge guarantee. Smoke plus first/continuation writes are 3 + 143 + 64,
not three separately authored copies of the scope.

First-history parent plus child spends 860 attempts under the unchanged aggregate
1,500-attempt ceiling (the prior eight smoke calls are separate sunk work).
Canonical bytes are 11,557,379 across their separately declared byte budgets,
not under the original single-run 8,000,000-byte ceiling. Including the smoke adds
72,199 bytes. Unknown usage is never silently treated as zero.

This first real scope averages approximately 4.13 successful provider attempts per
memory. It is not the empty-graph two-call probe topology: entity/edge deduplication
and temporal resolution become active as the graph grows. Do not extrapolate this
one history into a guaranteed full-corpus token count or price.

## Corpus readiness and next work

The new fifty-scope readiness audit still correctly exits 1: **49/50 scopes have no
Graphiti Episodes**. All 34,760 active vectors remain present and fresh, zero
missing/extra/stale entries; all 34,762 Store records and the full snapshot hash
remain unchanged. Of 9,744 eligible memories, 210 are projected and 9,534 are not.

The next natural-query pilot must bind a host relation vocabulary/semantic
definitions consistent with this actual graph, and bridge the high-config result
to a fixed-budget Reader context with distinct memory, raw dialogue and backing
source attribution. Those integration tasks are still unfinished. Then freeze and
run the first existing diagnostic question through natural V7 planning,
lexical/vector/relations/paths, local rerankers, source-backed packing and the
unchanged Reader/task-grading protocol. Use neither an oracle plan nor reference
evidence for retrieval. Only after that wiring check should graph backfill and
the high-config comparison expand across the remaining scopes.

Earlier provisional fifty-question raw/memory/combined accuracy (35/50, 28/50,
33/50) remains a vector-channel comparison, not a score for this new composition.
This step adds **no new QA accuracy**. It does not approve publication or AML.

## Receipts and verification

| Ignored local artifact | Raw file SHA-256 |
| --- | --- |
| `public-memory-graph-first-history-live-v1.json` | `9df0e5fed4b5ff3aff12c5bfe62a8793140df90c1f7fd9a573e6d4f6d49f37e0` |
| `public-memory-graph-first-history-continuation-live-v1.json` | `7984461969bb3153759ffa39e9616bc4b3a9f28d7ca9eee4088a2af3b873f9dd` |
| `public-memory-graph-first-history-probe-v1.json` | `5eed5e8ce1d0411de85f2963cf3ec7c742678645847dd1235e40691e2aa0d4de` |
| `public-memory-graph-first-history-probe-v2.json` | `d2c7dfacd48575d9e23ee6532108d5a7745c8b3086e0ace2ec6311921733a38b` |
| `longmemeval-expansion-50-high-config-preflight-v3.json` | `b136f1a925d219ebdf5ac0fab879451002dab78985ddab6e2a24c816d7c022a2` |

All are under `data/doppel/`; successful graph data and immutable parent caches are
retained. Snapshot before/after:
`11aab45f1bdfaebeea23bee822e53e5cdd94aef24f68bb020d90e9eda35e9cc3`.

Full regression after parent-budget changes: 1,403 passed/33 skipped, three subtests
passed. After the final probe changes, 68 related runtime/backfill/probe/high-config
tests pass. Ruff passes across the repository and Pyright using the actual venv
reports zero errors in the new modules. The full-suite warning is an upstream
Graphiti/Pydantic deprecation, not a failure. The final three added probe controls
are in the focused verification; do not relabel that as another full-suite run.
