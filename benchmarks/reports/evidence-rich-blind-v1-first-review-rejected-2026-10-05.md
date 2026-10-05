# Evidence-rich blind V1: preserved first semantic-review rejection

Date: 2026-10-05

Review implementation: `778aeb2e4b671b81f3da6c9de79267cd88907fa9`

Authored artifact SHA-256:
`b381788d6efa0ee0fe307f452a5895d05ad077ef35ac7983cbb55c5884f0ba37`

First review SHA-256:
`5d9fcfe093e2cc050edb49ef12c9c270930da564133ef39748c0819d703ac93d`

## Complete first result

All 48 batches completed, covering 5,232 surface slots. The result is
`reviewed_rejected`, with 126 findings on 121 distinct owner-local surface slots.
Every owner's core batch received findings; all 24 memory-only tail batches received
zero findings. There were 49 provider calls: 48 valid cached responses plus the first
invocation's one provider error. Total usage was 447,429 input, 44,772 output, and
492,201 tokens. The second invocation consumed 34 calls and reused 14 valid caches.
The earlier provider error had no saved subtype, so its root cause remains unknown.

| Reviewer code | Findings |
|---|---:|
| semantic_drift | 48 |
| relation_mismatch | 38 |
| entity_inconsistent | 33 |
| temporal_mismatch | 7 |

These are reviewer allegations about synthetic surfaces, not measured Doppel
retrieval failures. No corpus was compiled and no retrieval result was opened.

## Confirmed contract defects

The original host builder reused a person middle node and organization final node for
every two-hop family. This contradicted issuing-organization/location,
purchase-store/location, storage-container/location, and adoption-organization/operator
families. Its competing branch described a similar object but used the one-hop
anchor's identity. It also reused a shared organization as the final node for location
relations and reused the one-hop object in an independent no-answer custody question,
allowing the host to create conflicting current holders.

The earlier structural validators checked references and private time/subject labels,
but did not check the declared entity types against relation meanings. The new
benchmark-only endpoint catalog detects 105 incompatible endpoint incidences in the
original manifest. This count is a schema audit under explicitly declared endpoint
semantics, not another model score or 105 additional reviewer findings.

## Reviewer limitations

Some findings are demonstrably unsupported: ordinary custody wording was rejected as
not expressing HELD_BY; association wording was rejected for not spelling RELATED_TO;
several correct paraphrases were described as consistent while still flagged; and a
no-answer question was criticized for not declaring the answer unknown. The temporal
review also lacked the private valid-time fields and sometimes demanded a date absent
from the memory brief. Such comments cannot be silently treated as verified defects.

A complete human adjudication of all 126 findings is not claimed. Real surface defects
also exist, including content/edge endpoint divergence and questions that ask for a
document or item identity rather than the requested fact value. The affected core
batches require fresh generation against a coherent contract and a new complete
review; the original first rejection remains immutable.

## Decision

Proceed with a separately fingerprinted pre-retrieval revision under the original
protocol's allowance for demonstrable authoring/label contradictions. Preserve all
original artifacts and caches. Reuse only the 24 byte-identical, issue-free tail
batches, regenerate the 24 core batches, and review all 48 revised batches in a fresh
cache. Every comparison algorithm, retrieval threshold, and runtime memory protocol
remains unchanged. See the separately frozen revision plan.
