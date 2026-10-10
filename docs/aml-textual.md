# AML Textual preparation

Status: **experimental local contracts, not a submitted or deployed service**.
Decision date: 2026-10-06. Track: Textual; division: academic/open-source methods.
Initial user budget ceiling: **CNY 1,000**. This document grants no authority to
purchase hosting, disclose credentials, start paid calls or launch Full evaluation.
The user can prepare both model API keys; none has been configured or inspected by
this integration. Credential setup is not a blocker for offline development.

## Local diagnostic first (decision updated 2026-10-06)

Before switching embeddings, use the existing local `BAAI/bge-small-zh-v1.5`
512-dimensional embedding and `bge-reranker-v2-m3` configuration to find pipeline
defects on public raw histories. This is a **local development profile, not an
AML academic submission**. Required-model migration and paired embedding
comparisons follow after the raw-history pipeline is working. Do not attribute
any local BGE result to text-embedding-v4 or publish it as an AML score.

The first implementation is [LongMemEval preparation](public-memory-pilot.md):
explicit history/query projection, a separate scoring-only label object,
deterministic source/time identities, and a zero-model preflight. It is not yet
a live ingest/retrieval/answer runner. LoCoMo is a later adapter, not silently
treated as AML's LoCoMo-Refined.

The next local implementation adds a durable host ingestion journal around the
existing Miner, proposal writer, consolidation and index maintenance. Real SQLite
restart/process-death tests use fake model/index outputs; this is not a live
provider/vector/graph validation. Ingestion stage completion is **not** an AML
searchable receipt. Provider accounting, complete production retrieval composition
and HTTP hosting remain pending. Attributed historical retrieval and an opt-in
Search evidence projection now exist locally; neither is a deployed AML backend.
See the pilot document
for fixed complete-history selection, temporal policy and fingerprint compatibility.

Doppel remains a personal memory/context core. The integration adapts a transport
and host identity policy, not a benchmark-specific retrieval algorithm. No dataset
names, expected answers or query-specific exceptions may influence production code.

## Rules and model identity

Recheck official rules before registration: the [competition FAQ](https://agentmemoryleaderboard.ai/competition/)
currently requires `text-embedding-v4` for embedding and `gpt-4o-mini` for LLM
components in the academic division; rerankers are unrestricted. That includes
ingest extraction, consolidation, any Graphiti LLM calls, and natural query planning,
not just one advertised provider. Do not use DeepSeek or local BGE embeddings in
this competition profile, or relabel another provider as the required model.

Rules currently list October 31 at 23:59 as the materials deadline and November 4
at 23:59 as the evaluation stop. A second Full requires 30 days after the first
finishes. Plan for **one prepared Full this cycle**, not repeated tune-and-submit
runs. Fixed code/configuration and a publicly reachable service are required.
Smoke/Full activation and any registration are separate user decisions.

Before obtaining credentials, check provider eligibility and model availability.
[OpenAI's supported-region policy](https://developers.openai.com/api/docs/supported-countries)
does not currently list mainland China. Renting an overseas server or buying a
third-party key is not, by itself, proof of compliant access. If another authorized
provider offers the model, confirm its own terms, exact model/version and acceptance
by the competition; no alternative channel has been verified for this project.
Ask organizers whether they recommend or provide compliant participant model
channels, and what evidence is required for a non-direct provider. Never send
provider credentials by email or commit them. Do not switch the chosen division
or replace the required model without the user's decision.

## What is implemented

`integrations/aml/contract.py` is repository-only, not a frozen SDK API or HTTP
server. It has no providers, model downloads, network calls or service credentials.
It implements the Textual request/response boundary following the
[official API guide](https://agentmemoryleaderboard.ai/api-guide):

- Exact opaque user IDs map to hashed Doppel scopes within a trusted host namespace.
  No parsing of prefixes or dataset names. Hashing precedes SDK string normalization.
- A session is source provenance, not a retrieval filter. Message order, roles,
  original strings and optional Unix-millisecond timestamps are preserved.
- Stable write/event identities and a payload fingerprint let a future persistent
  backend identify retries versus conflicting changes. The boundary **does not
  implement a persistent idempotency ledger**.
- Add success requires a matching backend receipt asserting durable storage and
  immediate searchability. This is a backend obligation, not independent proof.
- Search retains rank order, enforces the requested maximum, checks returned scope,
  requires source IDs, and never pads to 100 or generates an answer. Source-ID
  existence and semantic binding still require authoritative Store verification.

An eventual HTTP host must serialize with `mode="json", exclude_none=True`, so
absent optional scores/dates are omitted and timestamps are ISO strings. Hosting,
authentication and payload-size/concurrency limits are not implemented here.

Run zero-paid local tests from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_aml_contract.py -q
```

These tests use a fake backend. They demonstrate interface behavior, **not**
durability, real cross-session recall, provider compliance, external scores,
authentication, HTTP availability or production deployment readiness.
Initial local verification: 36 boundary tests passed; full repository regression
988 passed, 33 skipped and 3 subtests passed. Ruff lint and Pyright passed; the new
files pass the formatter. A repository-wide formatter check reports 68 pre-existing
files needing formatting with the installed tool (a HEAD-only sample also fails);
they are not reformatted as part of this integration. The existing
Graphiti Pydantic deprecation warning remains; skipped service-dependent tests are
not claimed as live backend verification.

## Attributed Search content (2026-10-10)

`integrations/aml/evidence.py` adds the experimental
`AttributedEvidenceExporter`. The [official API guide](https://agentmemoryleaderboard.ai/api-guide)
states that `content` is passed to Answer and undeclared fields such as `metadata`
are ignored. Attribution is therefore encoded **inside** `SearchItem.content`,
not only in internal objects or extra response fields. Outer Search fields remain
`id`, `content`, optional `score` and `created_at`.

Content is a compact JSON string with format `doppel.attributed-evidence.v1`:

- Historical dialogue contains the original text, transport role, host-bound actor,
  speaker label, source authority, observation time, event/message IDs, source
  session and turn index. `agent` is labelled `historical_assistant`, not the
  current answering model. Unresolved actors remain unresolved even for `role=user`.
- Extracted memory contains the stored interpretation, subject and subject ID,
  source actor/authority, lifecycle state, memory type, temporal status, observation
  and validity times, plus **all** linked original sources. A confirmed lifecycle
  state is not a certification of truth; a planned status is not completed conduct.
- JSON escaping preserves the original source string losslessly, including
  whitespace, newlines and Unicode. It avoids structural header spoofing; it does
  **not** guarantee that an LLM will resist prompt injection or interpret roles
  correctly. Source text is never paraphrased or pronoun-rewritten.

Historical retrieval has an opt-in production-composition entrypoint:

```python
# retriever: AttributedContextRetriever with a real Store and exact-scope resolver
hits = await retriever.search_evidence(scope, query, limit=top_k)
# Return these ScopedEvidence items from the host's AMLBackend.search.
# TextualBoundary.search preserves their ranked SearchItem values.
```

For already authorized and temporally filtered personal-memory query hits:

```python
from integrations.aml.evidence import AttributedEvidenceExporter

exporter = AttributedEvidenceExporter(store, resolve_event=resolve_event)
hits = await exporter.memories(scope, personal_query_result.hits)
```

The exporter does not discover candidates, merge channels, choose scope privileges,
answer questions or judge answer support. It preserves supplied order and scores.
Both routes reload the authoritative Store and resolve original event/message IDs;
changed, revoked, missing, incorrectly attributed or out-of-scope sources fail the
batch with a redacted error instead of silently returning changed evidence. A final
snapshot check catches changes during asynchronous resolution, but is **not** a
cross-record transaction or protection against every subsequent race.

The memory route currently requires original sources in the **same exact scope**,
matching stored source actor/authority and complete miner provenance. Promoted
cross-scope memories, heterogeneous-source summaries, manually entered notes and
attachment-only sources need a separate explicit authorization/provenance policy;
they are not guessed or silently downgraded by this integration. The existing
snippet API, personal query engine, retrieval ranking and default SDK are unchanged.

Zero-paid checks:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_aml_evidence.py tests/test_aml_contract.py tests/test_public_context_baseline.py tests/test_public_context_rerank.py -q
```

These tests cover real temporary SQLite sources through retrieval and boundary
serialization with scripted candidates, not a live neural retrieval benchmark.
They establish transport correctness, not reduced speaker-error rates, AML
compatibility smoke acceptance, production hosting or a competition score.
See [the implementation report](../benchmarks/reports/aml-attributed-evidence-export-2026-10-10.md)
for scope and transport overhead. The subsequent
[paired representation result](../benchmarks/reports/aml-evidence-representation-result-2026-10-10.md)
completes 18 local DeepSeek Reader responses on nine opened synthetic controls:
speaker inversion remains in both arms. Labels survive transport but do not
guarantee the model interprets attribution correctly. Measured input-token
overhead is 8.10%; language observations and manual rubric judgments are not a
retrieval gain, an independent evaluation or the platform's Answer performance.
No default promotion follows. Return to bounded recall-only/lazy-analysis
diagnosis rather than extend this local Reader policy loop.

## Next implementation gates

1. **Local composition first; required providers later.** Keep the existing BGE
   embedding and reranker for early public-data diagnosis. After that, implement
   the required embedding provider with fake HTTP tests for ordering, dimensions, document/query modes,
   batching, failures and usage. Exercise the existing structured-output transport
   with `gpt-4o-mini`, without paid credentials. Audit *all* LLM paths. Choose and
   freeze embedding dimensions before creating a dedicated vector schema; never
   reuse a 512-dimensional BGE index as if it contained the new model.
2. **Real production backend.** Compose raw history ingestion, reference analysis,
   persistent Store/index maintenance and the existing natural retrieval pipeline.
   No oracle plans or imports of benchmark fixtures/private runner helpers. Persist
   `(scope, request ID, payload hash, completion)`; test interrupted writes,
   concurrent retries, changed payloads and service restarts. A queued index write
   is not Add success. Reload graph/vector candidates from the authoritative Store.
3. **Source identity policy.** Preserve both historical roles as attributed source
   evidence. `user`/`assistant` are transport roles, not sufficient proof of a human
   owner's identity or factual authority. Do not silently discard half the history,
   or promote historical assistant claims into confirmed owner facts. Unknown actors,
   third-person attribution and source quotes need generic explicit handling.
4. **Small lawful public-data pilot.** Measure the complete raw-input-to-evidence
   path, including multilingual text, time changes, incremental Add/Search,
   relationships and cross-session evidence. Preregister aggregate metrics and cost
   limits; record planner and ingestion failures separately from recall. Use only
   properly licensed public material, not reconstructed private evaluation data.
5. **Hosting readiness.** Choose a server only after measuring CPU RAM/disk and
   reranker cost. No permanent GPU server is assumed; do not substitute a weaker
   configuration without measuring it. Add HTTPS, a separate Memory System Key,
   constant-time authentication, bounded requests/concurrency, redacted errors,
   unauthenticated minimal Health, backups and recovery tests. Test externally
   reachable endpoints before applying for the formal run.
6. **Freeze, Smoke, Full.** Record commit, dependencies, actual model identities,
   prompts, graph/vector/reranker settings, scope policy, budgets and capacity.
   Obtain a revised cost estimate and user approval before paid evaluation. No
   algorithm changes mid-Full to improve scores. Keep evaluation data isolated
   from personal memories; delete it and derivatives within the official retention
   deadline (currently 30 days after completion, unless written approval extends it).

The schedule is a preparation target, not an assurance of readiness: provider and
backend work first; public pilot next; hosting and smoke only after their gates pass.
If quality, capacity or cost fails, report the blocker rather than submit an unready
service to meet the date.

## Budget: measure first, do not promise a CNY 1,000 Full

As checked on 2026-10-06, [OpenAI's model page](https://developers.openai.com/api/docs/models/gpt-4o-mini)
lists standard `gpt-4o-mini` input/output at USD 0.15/0.60 per million tokens.
[Alibaba Model Studio's model page](https://help.aliyun.com/zh/model-studio/text-embedding-v4)
lists Beijing text-embedding-v4 input at CNY 0.50 per million tokens. Region, taxes,
currency conversion, limits and actual account availability must be confirmed;
prices are not guaranteed. No free quota, discounted cache or batch discount is
assumed in the base budget, and synchronous Add cannot simply be outsourced to a
delayed batch job. The actual paid provider must be identifiable and compliant.

For **measured** millions of LLM input `I`, output `O`, embedding input `E` and
actual settled CNY/USD conversion `R`:

```text
model cost CNY = (0.15 * I + 0.60 * O) * R + 0.50 * E
total cost = model cost + hosting + storage + bandwidth + taxes/fees
```

Include repeated extraction/consolidation/graph prompts, planner calls and retries
in `I`/`O`; include document AND query vectors in `E`. Dataset volume is not a bill.
No model input limit or monthly vendor cap should be mistaken for a whole-run
cost cap. Reconcile provider usage, reservations and actual charges by stage.

Illustrative arithmetic only, using **R = 8 as a planning assumption, not a live
exchange-rate quote**, and excluding hosting/fees:

| LLM input / output / embedding (million tokens) | Model cost CNY |
| --- | ---: |
| 100 / 10 / 100 | 218 |
| 300 / 30 / 300 | 654 |
| 600 / 60 / 300 | 1,158 |

These are scenarios, not workload forecasts or contest charges. A multi-pass
pipeline can exceed the entire initial budget even before renting a server.

Provisional **allocation caps**, not vendor quotes or purchases:

| Purpose | CNY ceiling |
| --- | ---: |
| Controlled public-data pilot calls | 100 |
| Hosting/storage/network provision | 200 |
| Subsequent provider calls (including Smoke/Full if approved) | 550 |
| Reserved contingency | 150 |
| Total | 1,000 |

Before spending: verify legitimate account/model access, count API calls/tokens
and memory/graph/storage expansion on a bounded pilot, project scale with a safety
margin, and stop for user direction if the projected total exceeds the ceiling.
Do not disable useful retrieval or create scenario shortcuts merely to force the
estimate under budget. The initial offline contracts and evidence exporter used
zero provider/hosting spend. Subsequent local Reader diagnostics do use separately
authorized DeepSeek calls; their usage is recorded in the linked result reports,
not an official-model or Full-evaluation cost estimate. No hosting purchase or
official evaluation run is recorded by this integration.
