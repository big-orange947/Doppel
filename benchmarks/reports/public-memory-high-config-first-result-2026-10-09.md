# First natural high-config query: opened-history diagnostic

## Outcome and boundaries

The first fixed ingestion scope's natural question completed all five live stages.
Reference-only task judge reports correct; citation judge reports supported with
no contradiction, and both quotes are anchored in the actual cited source texts.
The single annotated evidence turn/session is in the packed context. These are
one opened question's observations, not a benchmark accuracy estimate, independent
verification, AML scores, or a demonstrated Graphiti improvement.

Case `ceb54acb` asks which four alternative terms the assistant previously
suggested. The answer supplies all four reference terms and separately mentions
the earlier shorter term. Its two citations are original **assistant** replies,
attributed as `agent_output`, not confirmed owner facts. Manual spot inspection
agrees that those source messages contain the listed terms; this is not an
independent reviewer or an additional model evaluation.

| Observation | Result |
| --- | --- |
| Natural V7 planner | 2 completed provider calls |
| Task correctness | Correct, 1 opened question |
| Annotated evidence coverage | 1/1 turn, 1/1 session |
| Citation legality | 2/2, no unknown or duplicate IDs |
| Citation support | Supported; 2/2 quoted observations anchored |
| Citation contradiction | False (fallible model judgment) |
| Final context | 20 whole items, 18796 canonical UTF-8 bytes |
| Final context channels | 7 owner memories + 13 original messages |
| Original-message roles | 8 user + 5 assistant |
| Scope boundary in final items | All match the authorized first scope |
| GPU reranker | CUDA:0, 2 batches / 180 pairs, 0 truncated pairs |
| Store, vector manifests and graph | Unchanged before/after |

## Which components actually contributed

Production `HighConfigRetrieval` consumed the original natural question, using
V7 planning, lexical/pgvector candidates, typed Graphiti relations, path discovery,
memory reranking and fixed evidence-rich V8 assembly. The raw dialogue branch
independently searched the original question and reloaded authorized source text.
The durable ingestion journal resolved backing sources.

Planner correctly classified the question as non-exact-topology (`path_decision:
abstain`); it did not fabricate a relationship path. The graph exploration call
did run once, but returned no promoted path evidence. Exact path searches: zero;
path reranker: `not_run` because no path candidates were offered, not an error
fallback. This question therefore does **not** show a graph retrieval gain.

Candidate channels before packing were 20 assembled memories, 20 independently
reranked original messages and 21 backing sources. Fixed cyclic memory/raw/backing
packing selected 20 items without text truncation. The two answer-bearing assistant
messages were raw-channel ranks 1 and 2. Backing messages remain original-message
items rather than new facts. Every selection, duplicate and budget omission is
retained in the receipt.

The previous profiles on this same opened question were already correct for
raw-vector-reranked and combined-vector-reranked, and incorrect for owner-memory-
only. New high-config success demonstrates that the raw assistant evidence channel
survives the full composition, **not** that it surpasses those existing baselines.
The earlier 50-question aggregate scores remain unchanged.

## Limitations retained, not repaired after scoring

1. The English question received a Chinese answer with English terms. Reader v2
   already instructs language matching; the model still drifted. Task correctness
   does not mean every Reader instruction was satisfied.
2. Frozen harness conservatively sets `degraded=true` / `full_config_success=false`
   because base query `complete=false` and warns that bounded index-first retrieval
   is not an exhaustive scope snapshot. No backend or memory reranker failed.
   Preserve these flags exactly. A future preregistered reporting revision should
   distinguish ordinary top-k incompleteness from actual backend/scorer degradation;
   do not retroactively turn the current flag into a passing gate.
3. The 142 relation definitions were generated from type names only. They have
   exact vocabulary coverage but their meanings were not independently reviewed.
   No question, endpoint, fact, gold answer or evidence label entered schema
   generation. There was no edge rewrite or gold-conditioned relation selection.
4. Only 1/50 histories is graph-ready. Highest configuration means all dependencies
   are configured and invoked when the generic plan calls for them; it does not
   imply every question needs graph paths or every history has been evaluated.
5. Live retrieval took about 25.96 seconds, including two remote planner passes
   and initial local model loading. This is not a warmed p50/p95 latency result.
   GPU idle/competition latency experiments remain deferred as requested.

## Accounting and replay

| Stage | New calls | Reported tokens |
| --- | ---: | ---: |
| Source-only relation schema | 6 | 12798 |
| Natural planner | 2 | 21599 |
| Reader v2 | 1 | 5065 |
| Reference-only task judge | 1 | 516 |
| Citation-support judge | 1 | 6828 |
| Total this round | **11** | **46806** |

All eleven calls succeeded on the first attempt; no retries or missing usage.
These costs are additional to the already-reported first-history graph authoring.
No token-hard-cap or exact monetary billing guarantee is claimed.

Separate-process cache-only replay supplies an empty provider key. It reuses the
immutable production retrieval checkpoint and validates all three downstream
content-addressed outputs, with 3 cache hits and **zero additional reservations or
HTTP calls**. Plan, retrieval, packed context, answer, grades, deterministic checks
and evidence scores match exactly. This is not a second fresh graph/planner/GPU
execution. All before/after corpus and index snapshots remain unchanged.

## Provenance and verification

Implementation pre-registered in `ecb308a` before the five live query calls;
source-only schema was pre-registered in `a8568b9` before its six calls.
Frozen query plan fingerprint:
`a242e442f01eb05a8690f476694461a68cce397d2bf071e10221fc49bc93a675`.

| Ignored receipt under `data/doppel/` | File SHA-256 |
| --- | --- |
| `public-memory-graph-schema-first-live-v1.json` | `ae33e0781738e435fc0f20ab37792ca77506f15e9960489fea869c4aa799692c` |
| `public-memory-high-config-first-preflight-v1.json` | `3d7016ee5f9c9d8193127ed884ad14f02e559a6f65aa58cc584fec86eb869b84` |
| `public-memory-high-config-first-live-v1.json` | `929d344ec6ed6583ab26a82eaf5782eaca8f64901b76dea871a37ae41bdbb3e3` |
| `public-memory-high-config-first-replay-v1.json` | `08ecb0971ee1a7014380dba25e4e9898e39f2c9e40577849c2d9ff7578f24e7e` |

Store remains 34762 records with corpus hash
`11aab45f1bdfaebeea23bee822e53e5cdd94aef24f68bb020d90e9eda35e9cc3`;
34760 active vector manifests remain bound to current Store fingerprints/version.
All 210 first-scope graph projections were rechecked before live/replay.
PostgreSQL connections enforce read-only transactions, existing vector schemas
are validated without DDL, and graph initialization does not create schema.
Record/index writes: zero. Credentials are not persisted.

Verification: focused adapters/pipeline/high-config tests 21 passed; full regression
1415 passed, 33 skipped, 3 subtests passed. Ruff passes repository-wide. Pyright
with the actual project interpreter reports zero errors for the new modules/tests.
The full-suite warning is an upstream Graphiti/Pydantic deprecation. User-owned
`uv.lock` remains modified and is not staged.

## Next sequence

Keep this answer and all old scores immutable. First freeze a general reporting
contract separating backend/scorer failure, top-k incompleteness and semantic
answer quality. Then extend to a small fixed consecutive ingestion-scope batch,
with explicit source-only graph/schema authoring budgets and the same question-
independent query/packing policy. Include existing vector baselines, record source
and graph contributions, and inspect disagreements only after the fixed run.
Do not immediately graph-author all remaining 49 histories: source projection
costs dominate and this first question adds no evidence of graph benefit. No
question-specific rule or gold-informed selection is justified by this result.
