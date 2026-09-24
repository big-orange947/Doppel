# Combined retrieval V2 — first frozen provider topology baseline

This report preserves the first complete provider acquisition for
`doppel-combined-retrieval-zh-v2`. It is an opened regression baseline, not a claim
that the end-to-end PostgreSQL/pgvector/Neo4j retrieval gate passed.

## Frozen identity

- Dataset fingerprint:
  `f35257ad354f5132c49f152b0b705fbba2cc7ce04dec4635237c91c505a84f6b`
- Acquisition implementation commit:
  `953992e6bcc239d94881b05a87328214357eec15`
- Provider topology report SHA-256:
  `d6786bebd5622e6fc4d33182c1e8ecd05f5004d97473af15d259fd801389fd39`
- Cases: 144/144
- Provider calls: 289
- Total reported tokens: 611,805
- Provider errors: 0

The theoretical two-pass total is 288 calls. One additional call came from a
first-pass self-loop that failed strict validation before review. That raw cache entry
was quarantined and the same frozen implementation retried it. The defect was fixed
after this report was sealed by allowing review of a bounded, authority-free
projection of malformed first-pass JSON.

## Preregistered topology result

| Metric | Result | Gate | Status |
| --- | ---: | ---: | --- |
| Required-route recall | 0.500 | >= 0.750 | fail |
| One-hop recall | 0.917 (33/36) | >= 0.850 | pass |
| Two-hop recall, all partitions | 0.292 (21/72) | >= 0.650 | fail |
| No-path false-candidate rate | 0.000 | <= 0.200 | pass |
| Extra routes per case | 0.257 | <= 0.500 | pass |
| Invalid compilations | 3 | 0 | fail |
| Provider/scoring errors | 0 | 0 | pass |

The overall quality gate failed. This result must not be relabelled as passing.

## Partition diagnosis

The 36 explicit heldout two-hop questions reached 21/36, or 58.3%. Failures were
mostly stable path compression: the model selected only `PURCHASED_AT` for “the shop
that sold it is located where”, only `OWNED_BY` for “the pet adopted from this shelter
belongs to whom”, or only `ISSUED_BY` for “the certificate signed by this organization
belongs to whom”. The problem is missing intermediate-role construction rather than
random ontology drift.

The 36 adversarial temporal-incomplete questions reached 0/36. Their text deliberately
names an anchor and asks whether its eventual location or ownership can be determined,
but does not reveal the hidden first relation. A text-only planner with only an
ontology cannot identify that hidden edge without graph observations. Treating this
as a prompt-only failure would reward memorization or entity-specific rules.

## Decision

Keep the failed baseline and add a separate bounded graph-exploration source:

1. enumerate only one/two-hop paths from the supplied anchor inside exact scopes;
2. allow only host-governed relation types;
3. apply valid-time filtering before exposure;
4. require Episode-to-memory provenance and authoritative Store revalidation on every
   hop;
5. use query-derived hop/terminal preferences for ranking only;
6. union explored paths with independent lexical/vector candidates;
7. leave answer support unassessed for the downstream model.

This is a general retrieval capability, not a case- or entity-specific exception.
The live combined retrieval benchmark remains pending because Docker Desktop 4.69
currently crashes while creating Windows AF_UNIX sockets for its Inference and
Secrets services. No container volume or database data was reset.
