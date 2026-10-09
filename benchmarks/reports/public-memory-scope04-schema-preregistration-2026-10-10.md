# Fourth history: settled graph and frozen source-name schema

Before paid schema calls. This is source preparation for one opened development
question, not a task score, formal LongMemEval run, blind validation or AML result.

## Settled real graph

- 219/219 eligible projections complete; 154 with rich relations, 65 fallback-only.
- 256 distinct rich edges /256 per-projection provenance links; 169 source types.
- 918 succeeded provider requests, 17 content-cache hits, 0 failed/interrupted
  requests, 0 missing usage, no retries. Reported tokens: 3821098.
- Store/vector fingerprints and all other 49 diagnostic graph scopes unchanged.
- Total ready graph histories now 4/50, 834 projections, not full-corpus coverage.
- Two observed missing-target warnings: HAS_ROUTINE (projection 131),
  TRIES_TO_REDUCE (projection 158). Those proposed relations were unusable despite
  complete projection fallback/provenance. Do not claim perfect extraction.
- Live graph receipt: `data/doppel/public-memory-next-graph-scope04-live-v1.json`.
- SHA-256: `043353a9f5f744b1f4cabf6e626061ed61569d8a32b4c50ee45da0dc2284fe4a`.

## Schema preflight

- Scope: `dpl_3b87559268c4ff5573a475dbd98fbc2ad51cbd4fdad9260129a66ba540c24107`.
- Preflight: `data/doppel/public-memory-next-schema-scope04-preflight-v1.json`.
- SHA-256: `8b5955cfe80123fbc1cfeceec0cc584bfd72e54325e19613fd43f6c95b4115e5`.
- Plan: `47faeb952fe0eea0fc45cfc247c6806ddf1eeaf8cf4ec7ecab65523fe2c6d48b`.
- Run dir: `data/doppel/public-memory-next-schema-scope04-v1`.
- Output: `data/doppel/public-memory-next-schema-scope04-live-v1.json`.

169 names, 24 per batch, at most 8 new requests, 4096 output-token cap per request.
Only distinct relation names reach the model. No questions, facts, entities,
answers, annotations or graph rewrites. Definitions remain fallible inferred
schema, not independently verified relation semantics. Preserve failures and
spent usage; no retries or manual definitions to suit a question.

After completion freeze the current V3 natural-query runner's source hashes,
provided-history clock policy and existing model/context settings before the
five-call QA ceiling. The predecessor-bounded next-history selection and final
source/projection checks remain mandatory. No old QA receipt is rewritten.
