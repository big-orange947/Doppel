# Hybrid path-candidate assembly: preregistered opened-corpus run

Date: 2026-09-23

Runner: `doppel.hybrid-path-candidate-ablation.v1`

Dataset: `doppel-candidate-relation-path-ablation-zh-v2`

## Question

Does bounded typed-path retrieval add evidence to Doppel's independent lexical and
pgvector candidates without suppressing the independent branch or weakening scope,
time, provenance, and lifecycle enforcement?

This is an **opened development comparison**, not a sealed quality claim. The reused
36-query dataset and its oracle exact/candidate path topologies have already been
inspected in earlier Graphiti runs. The experiment isolates retrieval assembly; it
does not measure natural-language path generation or answer correctness.

## Fixed profiles

All profiles use the same exact owner scope, explicit dataset `valid_at`, confirmed
personal-memory filter, and authoritative PostgreSQL Store records.

1. `independent_lexical_vector`: `PersonalMemoryQueryEngine` with Store lexical
   discovery plus local BGE embeddings in PostgreSQL/pgvector.
2. `typed_path`: exact and candidate topology routes through the live
   `GraphitiRelationIndex` on Neo4j.
3. `assembled_union`: the independent hits and typed paths pass through
   `assemble_hybrid_retrieval_candidates`; every record is reloaded from the Store,
   top independent candidates are reserved, paths are retained atomically, and
   repeated overlapping paths cannot stack rank.

The assembly reports candidates only. `answer_support` remains `unassessed`; related
context is not relabeled as factual proof.

## Gates fixed before execution

The run fails when any of these conditions holds:

- assembled evidence recall is lower than either individual branch;
- assembled complete-evidence rate is lower than either individual branch;
- assembled output contains any predeclared temporal/provenance-forbidden memory;
- assembled output crosses an owner scope;
- Store revalidation rejects an input base hit or typed path;
- the 20-record context budget omits an otherwise valid path;
- Neo4j fixture cleanup or the dedicated PostgreSQL benchmark-schema reset fails.

Candidate-noise memories remain a diagnostic rather than a hard failure. They are
related records that an answer model may reasonably need to inspect, not authorization
or temporal violations. The report must keep them separate from forbidden evidence.

## Runtime and cost boundary

- PostgreSQL/pgvector and Neo4j must both be live; unavailable dependencies produce a
  structured non-zero result rather than a degraded profile.
- Embeddings are local (`BAAI/bge-small-zh-v1.5`, 512 dimensions by default).
- External HTTP, paid LLM calls, and provider tokens must all remain zero.
- Passwords are read only from environment variables and must never enter the report.

The first result is a development baseline. A positive result permits a later test
with model-generated candidate topologies on a newly frozen corpus; it does not by
itself authorize wiring the assembly into Doppel's stable default query engine.
