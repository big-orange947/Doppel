# Frozen local candidate-width comparison

Use the same50 opened diagnostic LongMemEval histories, never reserved ones.
No new QA/LLM calls or source/index writes. Existing PG schemas/indices are read
only. Compare **fresh independently retrieved80 and160** raw BM25/vector RRF60
windows, same weights/no fallback. Do not cut a160 pool to pretend it is80 or
assume that widening RRF preserves every previous candidate.

For each case, validate full source corpus hash, original payload/source bindings
and complete current raw-vector catalog metadata. Query embeddings are symmetric
local BGE-small-zh512/fastembed0.8.0, reused for the same query across arms. Models
must already be present, offline flags on, API-key variables removed. No new graph.

Use unchanged local BGE-reranker-v2-m3 weights/runtime,8192-token cap, CUDA batch1.
Because it is pointwise, score each unique union candidate once and reuse its
score in both arms; ties follow **each arm's own input order**, not union order.
Hard maximum:12000 unique scored pairs/50 actual query embeddings,240 candidates
and2M input characters/case,300s scoring deadline/case. Failure stops and retains
checkpoints; no automatic retries, score repair or lexical fallback.

After scoring, run each arm through authoritative source reload/provenance and
final Store checks. Both return top20, then the unchanged whole-item ranked-fit
24KB packer. No metadata factoring, role preference, topic heuristic, passage
expansion, date rule, label access in selection or output-budget increase.

Save full candidate IDs, **all ordered20 source objects**, packed contexts and
trace per arm/case. Record stage-positive annotated coverage, all-evidence query
coverage, recovered AND displaced turns, per-case gains/losses, source/vector
snapshots, local model/truncation/pair accounting and runtime metadata. Negatives
are separate; annotated negative turns are not positive retrieval success and
returning fewer snippets is not proof of correct abstention.

The fresh80 arm is a controlled comparison, **not a rescore of37/50**. Report its
exact-context agreement with historical inputs. Old41–50 use saved candidate
origins; historical/fresh equality is not assumed. Any evidence gain still needs
a separately budgeted Reader comparison; more candidates alone is not promotion.
Do not promote a result with regressions without reporting them. This remains
opened development, not independent/official LongMemEval/AML or publication-ready.

Commit code/tests/protocol first, then generate a content-bound preflight plan
and require it unchanged at execution. Model/file identities and code/input hashes
are bound; use new report/run directory and refuse overwrite. Existing uv.lock,
old QA caches/grades, protected groups and source/index inventories stay intact.
