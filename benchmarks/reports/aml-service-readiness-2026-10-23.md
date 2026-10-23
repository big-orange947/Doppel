# Delivery convergence: runnable local service and cached50 audit

This work switches focus from further review-prompt iterations to executable
transport, durability and acceptance checks. No paid provider calls, new
extraction/embedding/graph work, production database changes, reserved-history
access, public listener or Docker restart.

## Implemented

`integrations/aml/service.py` supplies an injectable ASGI Textual transport and
a file-backed raw SQLite backend using the existing BM25/attributed evidence
retrieval path. A repository CLI starts it through the optional server extra;
default bind127.0.0.1:8000, service bearer token required, explicit role binding.
No provider API keys are read. Local verification installed uvicorn0.54.0 into
the existing virtual environment, without changing/staging the existing uv.lock.

The service uses a separate durable journal, fixed namespace/role/strategy profile,
deterministic event IDs and persisted arrival clock for missing source timestamps.
Source timestamps are kept as Unix milliseconds, not inferred occurrence dates.
Incomplete ingestion has a durable pending marker; scoped search/new writes fail
closed until that same request repairs. Identical completed retries revalidate
source identity, state, authority and content rather than resurrecting revoked
data. Conflicting payload returns409; incomplete/busy returns503, never Add success.

Search uses user scope across sessions and Store-backed source/actor reloads.
Attribution is in returned content; assistant text remains historical assistant,
not an owner fact. Original strings/opaque user IDs are preserved. The transport
adds bearer auth, body/message/top_k bounds, active-request limit, cooperative
timeout and redacted errors. These do not establish a hard latency SLA under
blocking SQLite I/O or distributed multi-instance correctness.

## Actual acceptance checks

12 new service tests use real temporary SQLite and HTTP serialization:

- Add then search immediately; owner and historical assistant provenance.
- Exact opaque ID echoes, including whitespace; distinct users do not share hits.
- Cross-session same-user recall, completed retry deduplication and409 conflicts.
- Close/reopen SQLite; retained IDs, content, scores and stable missing-time retry.
- Interruption after one source write; scope returns503; same request repairs
  after restart without duplicate sources or pretending partial Add succeeded.
- A different request cannot bypass pending recovery and claim searchability.
- Invalid timestamps fail before pending state, so they do not poison later writes.
- Deleted/expired sources are not resurrected or called searchable on retry.
- Auth, malformed/oversized input, secret-redacted errors, concurrency and timeout
  capacity recovery, immutable service profile.
- A real **loopback TCP subprocess** starts via the CLI, accepts add/search, is
  terminated, restarts on the same files and retains search/deduplication. The
  process has no model keys; it is stopped at test end, not left publicly running.

All AML contract/ingestion/evidence/service tests: **131 passed**. Ruff clean;
new-file Pyright0 errors/warnings. Uvicorn is optional; without it the TCP test
skips explicitly rather than being claimed as network verification.

An early full run had one failure in the existing abrupt-process-death SQLite
coordinator recovery test (WriteNotReady after child exit):2171 pass/1 fail,
33 skipped. The isolated recovery+service rerun passed11 tests, and a subsequent
full run passed2174 tests before the final2 revocation cases were added. No old
recovery test or production coordinator behavior was relaxed to hide the failure.
Final full suite on the completed12-service-test implementation: **2176 passed,
33 skipped,3 subtests**,219.32 seconds. A subsequent pass is not proof that the
initial lock timing failure cannot recur; keep this recovery observation visible.

## Cached50 integrity audit, not a new QA run

The existing summary file is unchanged:

- data/doppel/uniform-qa-fifty-summary-v1.json
- File SHA-256: a5ecbc7c038a072eb69e73d5024fd53f3ec92800a5aec8c1bbeedd95c7ad8408
- Exactly50 unique case IDs/ordinals01–50;37 correct by the existing grades.
- The unchanged30 and20 answer rows recompose exactly into these50 rows.
- All3 parent bindings recheck: original30 uses its file SHA, completion20 and
  completion contexts use their recorded canonical-object hashes. These are
  different hash domains; do not silently substitute one for the other.
- All50 Reader V2 outputs parse and their citation/derivation structures validate
  against their original saved contexts under the current structural checker.

This is artifact/structure regression only: no new retrieval, Reader generation,
independent answer grading, semantic support validation or official AML result.
The development baseline remains37/50 (74%); the new service was not run through
those50 QA tasks. No new score or claim of unchanged live answer quality.

## Frozen scope and remaining delivery gates

The runnable profile is **bm25-raw-smoke-v1**, deliberately isolated from other
data and labelled as a transport/zero-LLM diagnostic. It is NOT the highest-
configuration retrieval backend or an academic-model-compliant submission.
No core retrieval/default planner/reviewer configuration was silently changed.
Installing a server extra or passing TCP tests does not prove index readiness
for another injected backend. The application is repository-only; the library
wheel still packages doppel_memory, not an advertised installed AML server SDK.

Priority next: wire the already-tested high-config production search/index
composition behind the same AMLBackend boundary, with honest immediate-
searchability receipts and no eager full-history LLM analysis. Then check the
fixed runtime/model configuration and external deployment path. Organizer/model
acceptance, compliant model credentials, public hosting/TLS and actual official
Smoke activation remain unverified/unperformed. Do not launch Full or purchase
hosting merely because this local transport passes.

See [startup and limitations](../../docs/aml-service.md). Keep source review
optional/annotation-only; do not spend the remaining delivery window making a
small synthetic reviewer gate perfect or expanding to500 paid QA tasks.
