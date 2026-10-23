# Alibaba Cloud text-embedding-v4

Status: implemented with fake-HTTP/fake-PG tests. **No real Alibaba API key or
endpoint is configured in the agent environment.** Remote acceptance, quality
improvement and AML approval are not established. Existing BGE defaults/indexes
and package dependencies remain unchanged.

The [official API reference](https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api)
was checked2026-10-23. This uses **native DashScope HTTP**, not an OpenAI SDK,
with explicit document/query modes, fixed `text-embedding-v4`, dense output,
at most10 unchanged texts per request, and2048 dimensions by default. No custom
instruction, LLM, graph build, answer generation, retry, cache or truncation.

## Configure locally, never send keys in chat

Use the key and native API base URL from the same Alibaba workspace/region.
Copy the actual address from the console; do not guess a workspace ID or use
`/compatible-mode/v1`. Supported documented workspace URL forms:

```text
https://YOUR_WORKSPACE_ID.cn-beijing.maas.aliyuncs.com/api/v1
https://YOUR_WORKSPACE_ID.cn-hongkong.maas.aliyuncs.com/api/v1
https://YOUR_WORKSPACE_ID.ap-southeast-1.maas.aliyuncs.com/api/v1
```

Only explicit HTTPS workspace URLs ending in `/api/v1` are accepted. Userinfo,
query/fragment, other hosts/paths and nonstandard ports are rejected. TLS checking
stays enabled; redirects and environment proxies are disabled. Legacy hosts are
not automatically substituted or discovered.

In PowerShell at the repository root:

```powershell
$aliEmbeddingSecret = Read-Host 'Alibaba Cloud API key' -AsSecureString
$env:DASHSCOPE_API_KEY = [System.Net.NetworkCredential]::new('', $aliEmbeddingSecret).Password
$env:DOPPEL_ALIYUN_BASE_URL = Read-Host 'Native workspace base URL ending in /api/v1'
```

Closing this window loses its environment. Separate running agent/terminal
processes do not automatically inherit changes. No key is written to a .env
file or reused from DeepSeek.

## Verify the channel with only two requests

```powershell
.\.venv\Scripts\python.exe -m scripts.smoke_aliyun_embedding --live `
  --output data/doppel/aliyun-embedding-smoke-v1.json
```

Only normal repository dependencies are needed, no GPU/PostgreSQL/server. One
batch of two fixed public English/Chinese documents and one batch of two queries:
at most2 attempts, no retries, stop on failure. Attempts/reported tokens and
missing usage are explicit; unknown billing is not fabricated as known zero.
The receipt stores no vectors, source texts, remote bodies, URL or keys; provider
identity has an endpoint digest. Safe HTTP status may be recorded for diagnosis.
This is shape/channel verification, not retrieval or QA quality evaluation.

Existing output is not overwritten/resumed. A manual rerun with a new output is
a new paid experiment, not a cache hit. Without `--live`, it refuses before
reading credentials or making requests.

## Explicit service composition

After channel verification, use a **new dedicated schema and state directory**:

```powershell
# Also set DOPPEL_AML_PG_DSN and DOPPEL_AML_BEARER_TOKEN securely.
# Use an existing environment with asyncpg, local reranker and server support.
python -m integrations.aml.service `
  --directory data/aml-aliyun-v4 --namespace aliyun-v4-v1 --bind-owner-roles `
  --profile aliyun-hybrid --pg-schema aml_aliyun_v4_v1 `
  --embedding-dimensions 2048 --embedding-max-calls 5 `
  --reranker-model-path PATH_TO_EXISTING_BGE_RERANKER_V2_M3 `
  --reranker-device cuda --rerank-policy rank-fusion `
  --public-health --omit-search-scores
```

The5-attempt example is a **per-process smoke cap**, including one short startup
embedding and add/search attempts. It resets on restart, is not a durable/global
token/money budget and is not a Full-evaluation cap. Omit it only with a capacity/
cost plan. Startup warmup is paid in this explicit profile; other profiles do not
become paid implicitly. Ready probes check startup verification, client/model
state and DB profile without API requests; not current remote health/balance.

The shared Store/provenance/idempotence path is unchanged. Normal shutdown and
failed startup close the owned HTTP client. API errors do not become BGE/BM25
fallback. Failed index writes retain the pending-write safeguards; do not delete
journal rows to force success. The namespace/journal also binds model identity.

`embed()` sends `text_type=document`; `embed_queries()` sends `query`. Native
`text_index` restores original input order. Missing/duplicate/foreign indices,
wrong dimensions, nonnumeric/boolean/nonfinite/zero vectors, non-200 HTTP and
oversized responses fail. Input strings are never shortened. The model's8192-token
limit is server-enforced: character count is not presented as an exact tokenizer.
Oversized messages still need explicit host chunking/error handling before broad
rollout; this is not a certified all-payload AML profile.

## Index and release boundaries

Identity binds adapter/model, endpoint digest, dimensions, document/query modes
and unchanged normalization. Key rotation/attempt caps do not change semantics.
Endpoint/dimension changes create distinct pgvector profiles; query embedding is
marked dedicated. A vendor model alias is not an immutable remote-weights hash.
Never overwrite/mix old512d BGE vectors or weaken scoped Store reloads.

The current composition uses exact-distance pgvector, not2048d HNSW (Doppel's
vector HNSW contract caps2000 dimensions). Large-history latency/quality is still
unmeasured. The reranker remains explicitly local/device-bound. Model compliance,
public hosting/TLS, official credentials and Smoke are separate acceptance steps.

Core use is module-only: `doppel_memory.aliyun_embedding.AliyunEmbedding`, following
existing embedding protocols. No new root exports or compulsory SDKs.
