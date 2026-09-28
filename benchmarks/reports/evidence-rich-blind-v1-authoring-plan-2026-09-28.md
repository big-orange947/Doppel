# Evidence-rich blind V1 — authoring and first-run protocol

Date: 2026-09-28

Status: authoring contract frozen; corpus and retrieval results do not yet exist

Implementation baseline: `f52d4cfa905df68d610fea81980e84553f5fc321`

## Purpose

The opened V4 delta diagnostic supports `evidence_rich_v1` as an engineering choice,
but its positive cases were selected after V7/V8 retrieval differences were known.
This protocol defines a new owner-disjoint first-run corpus. No V7/V8 retrieval,
reranking, or evidence-judgment result may be opened until the complete corpus is
compiled, reviewed, fingerprinted, and committed.

The corpus remains synthetic and therefore cannot substitute for a future anonymized
real-agent replay. Its first run can test transfer beyond the V4 entities and topology,
not real-world prevalence.

## Authority split

The host, not a model, freezes all authoritative structure:

- exact owner scopes and owner-disjoint partitions;
- memory IDs, entity IDs, edge IDs, and Episode provenance;
- directed relation types and one/two-hop topology;
- subject, authority, lifecycle, and valid-time intervals;
- required, related, and hard-forbidden evidence labels;
- answerability, count identity, and query-time coordinates.

An external structured-output model may author only:

- new entity display names;
- memory and edge-fact surface text that expresses a supplied host relation;
- natural Chinese questions matching a supplied operation, time view, and topology;
- paraphrase variants for sealed/adversarial wording.

The model must never receive Store memory IDs, V7/V8 candidate lists, ranks, scores,
failures, expected profile deltas, or security labels. Model output cannot select a
scope, relation type, validity interval, evidence label, or answerability value.

## Frozen minimum corpus

- 24 exact owner scopes, none reused from heterogeneous V1–V4 or combined V1–V2;
- 240 unique queries and 4,608 memories (10 queries and 192 memories per scope);
- owner-disjoint partitions: 6 dev, 12 sealed, and 6 adversarial scopes;
- 24 queries in each existing heterogeneous category;
- at least 16 host-catalog relation types overall;
- at least 8 distinct two-hop relation-type pairs;
- at least 6 two-hop pairs not equal to `HELD_BY -> LIVES_IN`;
- one-hop, two-hop, temporal-invalid, competing-branch, repeated-node/cycle,
  related-but-insufficient, and no-answer examples;
- repeated entity display names across different owners to test isolation;
- at least 160 dense lexical/semantic distractor memories per owner scope;
- no exact query, durable fact sentence, owner ID, memory ID, or entity ID copied from
  the opened corpora.

The initial route-family pool must include neutral catalog combinations such as
repairer→employer, issuer→location, caretaker→employer, purchase venue→location,
recommender→employer, storage container→location, borrower→owner, and adoption
origin→owner. The final corpus must not be dominated by one object-holder-location
shape.

## Resumable acquisition

The future acquisition command must be dry-run by default and use the existing:

- OpenAI-compatible structured-output adapter;
- hard per-invocation provider-call budget;
- content-addressed raw-output cache;
- commit- and manifest-bound resume state;
- aggregate usage ledger with no API key persistence;
- temperature zero, no automatic retry, and explicit invalid-output accounting.

Authoring and independent semantic review are separate passes. A cache entry stores
raw surface output only; host projection and validation rerun on every replay. A
reviewer may reject semantic drift but may not rewrite topology or labels. Completion
requires every case to pass structural and semantic review. Partial acquisition emits
progress only and no quality metric.

Maximum planned provider work is 48 authoring calls plus 48 independent review calls.
Calls should be batched per owner when the output schema stays within configured byte
and token limits; batching may reduce the actual count but cannot change case coverage.

## Pre-result validation

Before committing the corpus, offline tests must prove:

- every identifier is unique and every reference resolves;
- partitions and owner scopes are disjoint;
- every required memory matches subject and valid time;
- every graph edge has same-scope endpoints and Store provenance;
- evidence label sets do not overlap;
- no-answer cases contain related context but no required evidence;
- invalid/expired branches are hard-forbidden where appropriate;
- every relation type belongs to the frozen host catalog;
- route length never exceeds two hops;
- corpus minima and duplicate-text exclusions hold;
- rebuild and committed dataset fingerprints are identical.

Corpus review may fix a demonstrable authoring/label contradiction before the first
retrieval run. Any fix changes the dataset fingerprint and is documented. After the
first retrieval result is opened, label, text, topology, and threshold changes create
a new corpus version and cannot replace V1.

## Frozen comparison

Run the unchanged V7 rank-first control and the committed `evidence_rich_v1` helper on
the same local PostgreSQL/pgvector, Neo4j/Graphiti, embedding, and cross-encoder stack.
External HTTP and LLM calls are zero during retrieval. Then run the opaque-item
evidence-judgment boundary with one frozen answer model/configuration.

V8 may remain preferred only if all of the following hold:

- scope leakage, subject violations, ineligible hits, temporal violations, orphan
  provenance, Store-revalidation failures, and hard-forbidden selections are zero;
- complete evidence@10 and retrieval sufficiency do not regress from V7;
- end-to-end support success does not regress from V7;
- source-no-answer abstention does not regress from V7;
- judgment accuracy and exact support selection regress by no more than 0.02;
- every category and partition completes, with all provider/cache usage accounted.

A strict end-to-end gain supports keeping V8 preferred. A tie keeps both named
controls without declaring V8 superior. A failed hard-safety check blocks promotion
regardless of recall. Latency is reported but does not relax quality or safety gates.

## Reporting discipline

The first retrieval and evidence-judgment reports are preserved whether they pass or
fail. Reports must state that the corpus is synthetic, identify the implementation and
dataset commits, include canonical hashes and backend cleanup status, and keep answer
text correctness unmeasured unless a separate claim-level evaluator is preregistered.
