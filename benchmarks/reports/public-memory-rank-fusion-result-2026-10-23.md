# Fixed RRF60 retrieval/neural fusion: small evidence gain, no QA claim

All50 opened diagnostic cases completed. Implementation/protocol/tests committed
and pushed as **cb67acc** before model preflight/execution. Frozen fingerprint:
74a3e768266dcd019849e420f18f755b2d305fa7d1b282680a38718e7cee18a4.
One equal-weight RRF60 setting, no parameter sweep, case replacement, retry,
question/entity/role/time rule or outcome-dependent source adjustment.

## Fixed-budget evidence result

Same saved80 candidates per case, final20 sources, whole-item ranked-fit24000
UTF-8 JSON bytes. First-stage order is the existing BM25/vector RRF order, not
keyword-only retrieval. Second-stage order is the same content-only BGE model.
The new arm fuses these two complete rankings; it adds neither source evidence
nor model metadata.43 answerable cases/76 annotated original turns;7 negatives
excluded from positive denominators and included in item/byte totals.

| Arm | Candidate annotations | Top20 annotations | Packed annotations | Complete positives | Packed items, all50 | Actual bytes, all50 |
|---|---:|---:|---:|---:|---:|---:|
|original retrieval order|72/76|61/76|60/76|32/43|921|1036634|
|BGE-only baseline|72/76|66/76|60/76|36/43|574|1176639|
|equal retrieval/BGE RRF60|72/76|**68/76**|**62/76**|36/43|742|1149353|

Relative to BGE, fusion raises top20 annotation coverage86.8%→89.5%, and packed
coverage78.9%→81.6%, both+2.6 percentage points. Same declared item/byte budget;
actual serialized bytes2.3% lower. These are **annotation retention**, not answer
accuracy, semantic sufficiency, event-count completeness or relevance probabilities.
No new Reader/judge has run. Historical **37/50 QA remains unchanged**.

Paired changes matter more than net totals:

- Top20:2 recovered/0 displaced,1 question improves/0 regress. Both recoveries
  are case44, initial retrieval ranks1/7 but BGE ranks25/32; fusion ranks7/15.
- Packed:3 recovered/1 displaced,3 questions improve/1 regresses. Case20 gains
  one annotation,37 gains one,44 gains one, **13 loses its only annotation**.
- Complete-positive count stays36/43:20 becomes complete while13 loses full
  coverage;37/44 remain incomplete. Do not present net+2 as uniform improvement.

Simply removing BGE is not supported: original retrieval order loses7 top20
annotations that BGE supplies and recovers only2. Its packed net count equals
BGE60, but5 recovered/5 displaced annotations affect different questions and
complete-positive coverage falls36→32. Equal totals do not mean equivalent answers.

## What remains missing

Full original orders now expose the six annotations originally lost by BGE:

| Case | Initial retrieval rank | BGE rank | Fusion rank |
|---|---:|---:|---:|
|40|27|27|28|
|41|22|37|26|
|41|38|22|28|
|44|35|27|30|
|44|1|25|7|
|44|7|32|15|

Fusion repairs two strongly ranked first-stage candidates discarded by the
neural top20, but cannot fix evidence that neither order ranks in its top20.
It still lacks4 of72 candidate annotations in top20 and drops6 more at packing;
4 further annotations remain outside the fixed80 candidates. Do not choose a
new top-k, k/weight or role quota to scoop these particular known ranks into a
passing result. Complementary-event coverage remains unresolved.

The complete candidate80 snapshots and all three80-item orders are saved for
every case. Future analysis does not need to repeat GPU inference just to recover
the order. This closes a prior observability gap, not a new benchmark score.

## Implementation boundary

`doppel_memory.rank_fusion.RankFusionReranker` is an optional existing-Protocol
wrapper, not enabled in runtime/service defaults or package-root exports. It
requests the delegate's full bounded order, preserves scoped identities and
original source fields/scores, and rejects partial/duplicate/unknown/modified
outputs, input mutation, invalid scores and timeouts. Similarity scores may be
changed by a delegate but are neither fused nor exported as truth probabilities.
Caller authorization and final Store reloads remain required. It does not make
all supplied scopes authorized, upgrade assistant statements or resolve time.

Identical memory-ID strings in different authorized scopes stay distinct via
scoped keys. No lower-rank filtering, source expansion, actor preference or hard
answer-support gate is added. See [usage/boundaries](../../docs/rank-fusion-reranking.md).

## Actual work and integrity

- Local BGE50 calls/**4000 pairs**, one complete80-candidate scoring per question,
  reused for both neural and fusion arms. Device `cuda:0`, batch1, max8192;
  zero truncated pairs, longest4107 tokens. Same artifacts/runtime as before.
- **All50 fresh BGE top20 and packed contexts exactly reproduce the historical
  baseline**, not just the annotation count. No silent runtime fallback.
- Zero paid API, Reader/judge, embedding, graph, retrieval or source/index writes.
  The existing80 order is reused; only current source objects are read from PG.
  Key environment variables are removed in the executing child before work.
- Original full Store corpus hash validated before and after every case;
  candidate attribution/provenance checked before scoring. Three final20 arms
  yield **3000 final Store checks**, with no rejected source/order mismatch.
  This is validation of these reads, not a newly measured security benchmark.
- All50 checkpoint JSON objects equal final report rows. Every candidate set
  has80 unique IDs in its exact scope; every arm is a complete permutation of
  that set, all contexts respect24KB. Code/input hashes and frozen preflight
  match after completion; no old report/cache/database modifications.
- GPU warm/contended latency was not benchmarked; tests ran concurrently. No
  latency or deployment-cost advantage is claimed from shared experimental work.

Ignored local artifacts:

- `data/doppel/rank-fusion-preflight-v1.json`, SHA-256:
  b73f049f16369ab832e91a864aad19cdd2c2bc5641d46b41882b3fb8e3894f7b.
- `data/doppel/rank-fusion-local-v1.json`, SHA-256:
  6e6b8c911ace18b75fe8a0d64efa9c9af8f304d8af0a8a625cb3600bf7c85208.
- `data/doppel/rank-fusion-local-v1/case-01.json` through `case-50.json`, plus
  immutable `attempt.json`. Complete candidate payloads preserve original actor,
  role, authority, text, observed/effective bounds and source-event IDs.

27 new offline tests:24 adapter/permutation/isolation/payload/timeout cases and3
annotation-independent packing/positive-denominator/paired-accounting checks.
Full suite **2314 passed,33 skipped,3 subtests**,236.01s; one existing optional
Graphiti/Pydantic deprecation warning. Ruff/format and new core/runner Pyright
pass (0 errors/warnings). Preexisting uv.lock1025 additions/1025 deletions remains
untouched/unstaged. No Docker restart, volume deletion, schema repair or reset.

## Decision

Keep fusion **opt-in and unpromoted**. The small fixed-budget source-retention
gain is a legitimate reason for one separately frozen downstream QA comparison,
not a claim of improved user-facing memory intelligence. Include all50 rather
than selecting recovered questions, reuse exact baseline requests/grades and
separate provisional judge ambiguity from source loss. Keep k/weights unchanged;
do not start another tuning sweep or eager graph build. Do not let this single
opened-data gain consume the reserved cohort before a configuration is fixed.
