# Heterogeneous personal-memory retrieval V1 — preregistration

This protocol was frozen before any retrieval profile was run on the new corpus. The
previous 144-query combined corpus and all of its results were already open before this
dataset was generated. No score from that corpus is used as a result on this one.

## Frozen corpus

- suite: `doppel-heterogeneous-retrieval-zh-v1`
- version: `1.0.0`
- seed: `94720260925`
- scopes: 48 exact owner scopes
- memories: 9,216 (192 per scope)
- queries: 480 (10 per scope; all full query texts unique)
- entities / edges: 144 / 96
- canonical dataset fingerprint:
  `927763a1cb73163f7c494a80a2b9838af1cb558cb3a44e2a6816a97bbbd54e03`
- committed file SHA-256:
  `b4dc5af8bd2b38712c683db3b3706c47ab00198e040d7a01e06a494850005d8a`

The corpus is deterministic, synthetic, Chinese, and contains no real personal data.
It is author-known and not independently hidden, so `publication_ready=false` remains
part of the schema.

Owner scopes, rather than individual questions, are assigned to partitions:

| partition | scopes | queries | wording role |
| --- | ---: | ---: | --- |
| dev | 12 | 120 | explicit development wording |
| sealed | 28 | 280 | paraphrased first-run evaluation |
| adversarial | 8 | 80 | elliptical and contrastive wording |

No owner occurs in more than one partition. Every scope contains one query in each of
the ten categories: current residence after a temporary stay, residence at an earlier
date, corrected current fact, completed-episode count with duplicate and cancelled
events, one-hop relation, two-hop relation, document fact, cross-conversation stable
preference, subject correction, and related-but-insufficient evidence. The seven
domains are residence, career, travel, possessions, documents, preferences, and health.

The committed validator enforces unique IDs and full query texts, exact-scope evidence
labels and graph topology, Episode provenance, timezone-aware non-reversed validity,
one- or two-hop ontology-bound routes, effective required evidence, owner-subject
agreement, event-count labels, cross-conversation origin, and the declared minimum
category/domain/partition densities. Offline mutation tests must demonstrate that the
validator rejects cross-scope labels, duplicate queries, and reversed graph validity.

## Evaluation separation

The first runner must report these layers separately rather than collapsing them into
one score:

1. independent lexical plus pgvector memory retrieval;
2. Graphiti relation retrieval with the frozen gold route, which isolates graph
   execution from natural-language planning;
3. Store-revalidated assembly of independent memories and atomic graph paths;
4. the same assembly with local whole-memory reranking of only the independent branch;
5. an end-to-end natural Planner track, if implemented, whose generated routes never
   receive gold memory IDs, answers, scope authority, or graph contents.

Gold routes are an oracle diagnostic, not a production Planner claim. A planner miss
must not be reclassified as a Graphiti failure, and a graph miss under an oracle route
must not be blamed on the Planner. No query-category string, case ID, answer text, city,
person, item, or document name may trigger a special retrieval rule.

## Frozen metrics and safety accounting

Report overall, per-partition, and per-category results. At minimum include evidence
recall@1/5/10/20, complete-evidence@5/10/20, MRR, exact episode-count evidence after
event-key deduplication, related-evidence recall for no-answer cases, source attribution,
maximum final context size, and p50/p95/p99 latency.

Required, related, and hard-forbidden labels have different meanings:

- required evidence is necessary for the labeled answer;
- related evidence is useful context but is not sufficient proof;
- hard-forbidden evidence is wrong by scope, subject, time, lifecycle, correction, or
  event status.

Retrieving “this book is held by a friend” for “who bought this book?” may therefore
earn related-evidence credit, but it must never be reported as proof of a buyer. Answer
sufficiency remains an explicit downstream judgment rather than a similarity cutoff.

Every profile must also report exact-scope leakage, exposed candidate/expired/superseded
or agent-output facts, temporal violations, orphan evidence, Store revalidation
failures, graph path omissions, reranker candidate-membership changes, and backend
cleanup. These are counts, not rates rounded to zero.

## First sealed-run gate

Implementation may be debugged on the 120 dev queries. Before any sealed or adversarial
result is opened, the runner implementation, profile definitions, candidate bounds,
reranker model/runtime, and report schema must be committed. The first complete
highest-quality profile must satisfy all of the following:

- at least 0.85 overall evidence recall@5;
- at least 0.80 overall complete-evidence@10;
- at least 0.75 evidence recall@10 independently in every answerable category;
- at least 0.75 related-evidence recall@10 on the no-answer category, without counting
  that evidence as answer support;
- no MRR regression relative to the same assembled profile without reranking;
- exact episode-count evidence in at least 90% of episode-count queries;
- zero hard-forbidden hits in the final context;
- zero exact-scope, subject, authority/state, temporal, provenance, Store-revalidation,
  reranker-membership, or graph path-atomicity violations;
- at most 20 final records and at most two graph hops per query;
- successful Neo4j fixture and dedicated PostgreSQL benchmark-schema cleanup.

Latency is recorded but not gated in the first run. A failed gate remains a valid
result and must not be hidden by retuning on sealed/adversarial cases. Any subsequent
opened-corpus tuning is versioned as a regression experiment; it is not another sealed
measurement.
