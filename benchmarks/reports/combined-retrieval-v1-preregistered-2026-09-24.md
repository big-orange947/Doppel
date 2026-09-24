# Combined retrieval V1: frozen-corpus preregistration

Date: 2026-09-24

Dataset: `doppel-combined-retrieval-zh-v1`

Dataset fingerprint: `e16bb570cd3da5924a22a4b1556774d42e556992eaa93d5060c59fc5f2beaf51`

## Purpose and corpus role

This is Doppel's first frozen combined-quality corpus. It is designed to measure the
whole candidate path rather than the already-demonstrated oracle-topology ceiling:

1. natural-language query planning and candidate-path generation;
2. independent lexical and PostgreSQL/pgvector retrieval;
3. live Neo4j/Graphiti typed-path retrieval;
4. authoritative Store revalidation and bounded candidate assembly.

The corpus is synthetic and contains no personal data. It is **provider-unseen and
frozen**, not author-hidden: its generator, labels, and JSON are committed for review.
No implementation or prompt may be changed after observing its first provider or live
retrieval metrics. A future externally authored corpus is still required for a
publication claim.

## Fixed scale and composition

- 36 exact owner scopes;
- 3,600 memories, exactly 100 per scope;
- 216 graph entities and 144 provenance-bearing edges;
- 144 queries: 36 one-hop, 36 two-hop, 36 semantic/non-relation, and 36 temporal
  incomplete-path adversaries;
- 108 sealed answerable queries and 36 adversarial no-answer queries;
- repeated entity names across three different owners to test isolation;
- same-scope near-semantic distractors, Agent-output distractors, expired distractors,
  and future-dated distractors.

Every query separately labels required answer evidence, safe but incomplete related
context, and hard-forbidden evidence. Retrieval candidates remain
`answer_support=unassessed`.

## Fixed acquisition protocol

Provider observations use the committed relation catalog and a content-addressed
cache. Gold routes, memory IDs, scope IDs, graph data, and labels are never included in
provider input. Acquisition may resume after transport, balance, or process failure,
but all cache entries must bind to the same:

- dataset fingerprint;
- catalog fingerprint;
- generator name/version;
- provider model/configuration;
- implementation commit.

No metrics are considered a first-run result until all 144 observations are present.
Partial acquisitions report only progress and provider usage. Changing any bound input
invalidates the acquisition rather than silently mixing observations.

The default generator profile is the existing V3 two-pass reviewed candidate protocol.
The review remains non-authoritative: it cannot choose scopes, inspect the graph, see
gold routes, or claim answer support. Maximum uncached topology calls are therefore
288. Calls are budgeted, have no automatic retry, and use disk cache on resume.

## Pre-registered topology gates

The completed natural-language topology stage must satisfy:

- required-route recall ≥ `0.75`;
- one-hop route recall ≥ `0.85`;
- two-hop route recall ≥ `0.65`;
- false candidate rate on semantic/non-path questions ≤ `0.20`;
- extra routes per query ≤ `0.50`;
- invalid topology compilations = `0`;
- provider/generator errors = `0`.

Failure is retained as a real result. The graph stage may still run to diagnose whether
independent semantic retrieval degrades gracefully when topology generation fails.

## Pre-registered retrieval and safety gates

All retrieval profiles use the same PostgreSQL authority, pgvector index, explicit
query time, and exact scope. The primary comparison is independent lexical + pgvector
versus independent retrieval plus model-generated typed paths.

The completed run must satisfy:

- answerable evidence recall@5 ≥ `0.80`;
- answerable complete-evidence rate@10 ≥ `0.72`;
- one-hop evidence recall@5 ≥ `0.85`;
- two-hop complete-evidence rate@10 ≥ `0.65`;
- semantic/non-relation recall@5 ≥ `0.75`;
- generated hybrid evidence recall and complete-evidence rate must not regress from
  the independent branch;
- generated hybrid two-hop complete-evidence rate must improve by at least `0.05`
  absolute over the independent branch;
- hard-forbidden hits = `0`;
- scope leakage = `0`;
- inactive/Agent-output authority violations = `0`;
- orphan provenance = `0`;
- temporal incomplete-path queries yielding a complete graph path = `0`;
- Store revalidation failures = `0`;
- assembled candidates ≤ `20` per query and retained path support is atomic.

Candidate noise and related-but-incomplete context are reported, not relabeled as hard
failures. MRR, Recall@1, nDCG, context token estimates, p50/p95/p99 latency, source
attribution, and graph/vector overlap are diagnostics. Latency is not a hard gate in V1
because this Windows development machine is not a controlled benchmark host.

## Non-claims

Even a passing run will not establish production-scale performance, extraction
quality, or final answer correctness. A separate 100,000+ memory stress suite will
measure throughput and tail latency, and a later answer-layer suite will measure
whether the model cites sufficient evidence rather than merely receiving candidates.
