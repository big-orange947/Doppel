# Service readiness/configuration convergence

Starting implementation commit c1a099b. No public server/cloud purchase, paid
provider calls, source import, new QA generation, graph work or benchmark reset.
This is operational work, not a retrieval algorithm or quality-score upgrade.

## Changes

- Authenticated `GET /healthz` responds with process liveness; `GET /readyz`
  requires an explicit probe and returns only status plus opaque profile_id.
  Failed dependency checks/timeout return503 without raw exception text. Liveness
  remains separate when the DB is unhealthy or the request budget is occupied.
- Probe before the CLI opens its listener. Journal/Store accessibility, vector
  table/column access, vector-profile metadata and loaded model objects are
  checked. No history scan/counts, embedding, neural ranking or source writes
  occur inside the readiness probe; normal model startup warmup is separate.
- Keep per-scope unfinished-ingest503 behavior. Readiness is not a certificate
  that every user's history is complete, that future GPU work fits memory or
  that answer quality/temporal selection is correct.
- CLI exposes timeout/concurrency/body/message/result limits. Nonpositive,
  nonfinite, wrong-type bounds and bad port fail before filesystem/DB/model work.
  Message/result caps may be lowered, not raised beyond1000. Token bytes must be
  visible ASCII without whitespace. Defaults remain unchanged.
- Non-loopback bind requires an explicit flag and at least32 token characters.
  Uvicorn ignores forwarded headers. This is a guard, **not TLS, per-user access
  authorization or public-deployment approval**.
- PG target fingerprint requires explicit single host/user/database and allows
  only one valid sslmode query. Target-changing query overrides and fragments
  are rejected. Credentials never enter the fingerprint; URI percent encodings
  normalize. Existing ASCII-URI fixture/profile remains compatible. An older
  encoded-URI profile may require a separate directory; no automatic migration.

## Verification

33 new offline cases plus prior23 service/profile cases: **56 passed**. Existing
real loopback TCP child/restart test is extended to check authenticated health,
readiness and the same profile_id after restart. Tests cover dependency failure
redaction, timeout/capacity recovery, pending-user vs global readiness distinction,
closed/unknown backends, lower transport caps, invalid values, pre-I/O CLI failure,
canonical credential-free DB identities and rejected target overrides.

Real readiness check used the same existing local-model CUDA environment and
six-source synthetic PG schema/state directory from the preceding smoke. It
loaded the existing local models, then exercised the new routes through **in-
process ASGI/httpx**, not a new PG TCP subprocess run. The separate extended
SQLite CLI test supplies real TCP coverage of the new routes. No physical DB
outage or live profile corruption was induced.

Actual real-dependency results:

- Liveness200; readiness200; wrong token401.
- Same stored profile accepted; profile_id:
  b2e646f72f75ab0ae2bd1b747a76d2d3c2a8f76bfdcb5fade976444d77e4b935.
- Still6 raw records and6 vectors; source add0/search0/paid0.
- Local startup does its existing embedding/model warmup; **the readiness probe
  itself** has no model inference. No model download is enabled.
- Local report: data/doppel/aml-service-deployment-preflight-20261023.json.
- Report file SHA-256:
  e1b639e2bc4fa8472bd916770097274c90e7c8cab7019173a2782c1b456024e4.

Ruff repository check clean; changed runtime modules Pyright0 errors/warnings.
Full regression: **2228 passed,33 skipped,3 subtests**,231.31s; one existing
optional Graphiti/Pydantic deprecation warning. A final focused deployment/service
rerun also passes45 tests. Existing uv.lock is not changed/staged; fixture data
and original50 QA receipts remain untouched. The old50 summary file SHA-256 still
equals a5ecbc7c038a072eb69e73d5024fd53f3ec92800a5aec8c1bbeedd95c7ad8408.

## Remaining scope

The [operations runbook](../../docs/aml-deployment.md) covers startup/profile
freeze, matched journal+DB backups, pending-request recovery and public-exposure
requirements. No hosted endpoint, TLS, Linux/GPU image, official model compliance,
official client smoke, load/SLA, backup-restore rehearsal or new QA result is
claimed. The opened diagnostic baseline is still37/50; full structured temporal
and graph HTTP composition remains outside this raw profile.
