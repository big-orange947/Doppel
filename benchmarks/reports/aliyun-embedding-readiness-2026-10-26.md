# DashScope embedding integration readiness

Recorded 2026-10-26; implementation and regression receipt from 2026-10-23.
Runtime commit: `65ea33bd93bf9bd56d50dda7de3f85dee3bd2577`.

## Result and limits

Native Alibaba DashScope `text-embedding-v4` support is implemented as an explicit
provider and `aliyun-hybrid` service profile. Default dimensions are 2048. Document
and query embedding use separate request modes; batches contain at most 10 texts.
The provider validates and reorders response vectors, binds endpoint/model/dimension
identity to indexes, redacts errors, closes its HTTP client, and supports an atomic
process-local request-attempt cap without retries or fallback to another model.

Existing BGE defaults, indexes and package dependencies are preserved. This does
not establish a retrieval-quality improvement, official AML compliance or release
readiness. No real Alibaba credentials or native workspace URL were available in
the agent environment; no live Alibaba requests were made in this work.

API contract source: [Alibaba native text embedding API reference](https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api),
checked during implementation on 2026-10-23. Configuration and limitations are in
[the integration guide](../../docs/aliyun-embedding.md).

## Verification

- Full offline regression: 2437 passed, 33 skipped, 3 subtests, about 255 seconds.
- Full-repository Ruff passed. Pyright on the provider, retrieval factory, service
  and canary reported no errors or warnings.
- Fake HTTP tests cover native request shape, query/document modes, batching,
  response ordering, invalid vectors, status/error redaction, redirect rejection,
  request budgets, usage accounting and provider identity.
- Fake PG/local-model factory tests cover startup verification, readiness without
  extra remote calls, failed startup cleanup and the existing shared Store path.

These tests do not substitute for real DashScope channel or quality validation.

## Existing BGE live regression

The refactored shared service factory was also exercised against real PostgreSQL
and HTTP using the existing local BGE embedding and local reranker. Both initial
startup and process restart passed, including owner isolation, attribution,
idempotence/conflict handling, authentication, result limits and profile pinning.
This was a BGE regression test, not an Alibaba acceptance test.

- Receipt: `data/doppel/aml-provider-refactor-live-20261023.json` (ignored local artifact).
- Receipt SHA-256: `336e94fe4dd1f206b927ea508ae794da84cdb3ea6dc6a675832897da1cf119d9`.
- Profile ID: `2e059c7c1e8d141929b5fa703ea618fb77fd14c7caee3ad6ecfb932710dbc516`.
- Existing BGE vector identity: `pgvector:dplv_69f382ac9fc73401`.
- Dedicated schema: `aml_provider_refactor_smoke_20261023`.
- Six synthetic records/index entries retained in the dedicated schema and journal;
  previous schemas, volumes and caches were not reset. Both test servers stopped.
- Paid provider calls: zero. Model downloads: disabled.

This two-process smoke run is not a latency benchmark or a new QA score.

## Next acceptance steps

1. In the same local PowerShell window, set `DASHSCOPE_API_KEY` securely and set
   `DOPPEL_ALIYUN_BASE_URL` to the actual native workspace URL ending in `/api/v1`.
2. Run `python -m scripts.smoke_aliyun_embedding --live --output
   data/doppel/aliyun-embedding-smoke-v1.json`. This sends at most two requests,
   performs no database writes and records no key, raw vectors or source text.
3. If the channel passes, exercise `aliyun-hybrid` against a new dedicated schema
   and state directory, then run the locked retrieval comparison. Preserve old BGE
   artifacts rather than overwriting or mixing vector profiles.
4. Resolve long-input handling, capacity/cost planning, public deployment and
   official AML Smoke independently before claiming competition readiness.

The two-request canary is channel/shape verification only. It is opt-in, has no
retry or cache, refuses to overwrite an existing receipt, and is not an embedding
quality evaluation. Service request caps reset per process; they are not durable
token or currency budgets.
