# Local hybrid HTTP composition, not a new quality score

Starting commit a7a7bcd on master. No paid calls, model downloads, inference on
real model weights, production DB changes, historical cache rewrites, reserved
history reads, Docker restart or public deployment. Existing uv.lock is preserved.

## Frozen score interpretation

The existing opened diagnostic50 remains **37/50 (74%) QA correctness**, not
retrieval recall or an official/independent LongMemEval/AML score. Positive-only
30/43 (69.8%); negative7/7. Temporal and multi-session4/7 each, personalization2/7.
Candidate annotation coverage72/76 (94.7%) becomes60/76 (78.9%) after ranking and
24KB packing. Nine of13 failed answers already retain every annotated turn.
This does not justify blaming all errors on retrieval, or treating optional graph
and temporal modules as proven QA gains. Old grades and rows are unchanged.

## Delivered implementation

The repository CLI has an opt-in `--profile local-hybrid`: PostgreSQL authoritative
raw events + existing pgvector + existing BM25/RRF60 + local content-only neural
ordering + final authoritative scope/source/actor reload. Fixed80 candidates do
not shrink when the caller asks for top1. The SQLite/BM25 smoke default is unchanged.
The service modules import no frozen benchmark harness. This is stronger raw
retrieval composition, not full structured temporal/graph high-config or academic
model compliance. No question/entity/answer-specific branch is introduced.

Local BGE-small-zh ONNX and cross-encoder load only existing directories with
offline flags. Artifact hashes, library versions, device and retrieval policy
bind to the service journal; invalid scores/shape fail rather than restoring the
base order. The PostgreSQL target fingerprint excludes credentials. Startup must
find an already-enabled vector extension; no graph construction or reset.

Add acknowledges only after batched indexing and exact index-manifest checks for
every source's scope/version/fingerprint. An interrupted initial write remains
pending. Completed-source retries use a distinct pending repair marker: an index
failure cannot convert a previously completed source into a new writable source
and resurrect later revoked records. Search/new same-scope writes fail closed
until repair. Default smoke files/profile remain compatible.

## Verification and limits

11 new offline cases; **23 service/profile tests passed** in3.01s, including the
existing real loopback process-restart case. New composition tests use real HTTP
serialization and file-backed SQLite journals, but deliberately fake vector
catalog/model boundaries. They cover semantic-only query consumption, fixed80
window, ordering without trusting reranker text, assistant attribution, owner
isolation, catalog reopen, failed indexing/manifest recovery, completed repair
without resurrection, no lexical fallback, immutable profile, offline model flags,
model hash drift and invalid embedding/reranker output. Another119 existing
contract/ingestion/evidence tests pass. New service modules: Pyright0 errors/warnings,
repository Ruff clean. Full suite: **2187 passed,33 skipped,3 subtests**,216.06s;
one existing optional Graphiti/Pydantic deprecation warning. No earlier test or
acceptance expectation was loosened.

Docker inspection could not find the Docker Desktop Linux-engine pipe. As the
user requested, no attempt was made to start/restart it. Real PGvector + actual
local-model HTTP add/search/reopen acceptance is therefore **not executed** here.
The default .venv also lacks sentence-transformers; an existing separate CUDA
evaluation environment may be used for that next acceptance instead of reinstalling
GPU packages. Fake inference results are not real model or database results.

No new answer generation, judge calls or50-case QA replay: **37/50 is unchanged**.
Next: user opens Docker manually; verify engines non-destructively, select a new
service-only PG schema/state directory and existing model environment, run a tiny
attributed add/search/restart smoke, then freeze the actual deployment profile.
Only afterward decide whether one bounded QA comparison is worth the remaining
budget. Do not return to eager full-history paid graph building.
