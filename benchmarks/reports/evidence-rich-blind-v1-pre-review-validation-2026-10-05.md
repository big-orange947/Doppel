# Evidence-rich blind V1: pre-review offline validation

Date: 2026-10-05

Validation implementation: `c15a9dfb7e5ab0636f3e7f7e4811e62193c997bb`

Authored artifact SHA-256:
`b381788d6efa0ee0fe307f452a5895d05ad077ef35ac7983cbb55c5884f0ba37`

## Verified structure and coverage

The completed authored artifact passed the real review loader, host surface validator,
all 48 review-request builders, in-memory corpus projection and dataset validation,
and opened-corpus novelty checks. This validation did not write a compiled corpus or
create a semantic-review acceptance. External calls and retrieval executions were zero.

| Item | Count |
|---|---:|
| Owner scopes | 24 |
| Memories | 4,608 |
| Entities | 384 |
| Relation edges | 240 |
| Query slots | 240 |
| Review batches | 48 |
| Reviewed surface slots | 5,232 |
| Surfaces per review request | 96–122 |
| Largest serialized review request | 46,175 UTF-8 bytes |

Dev, sealed, and adversarial partitions contain 60, 120, and 60 query slots respectively.
Each of the ten frozen categories contains 24 queries. Required-evidence references,
subjects, valid times, edge endpoints, provenance references, count labels, owner
partitions, and bounded route shapes passed the existing dataset validators. The review
requests were checked automatically for private owner IDs, scope strings, memory IDs,
case IDs, answerability fields, and forbidden-evidence labels; none was exposed.

## Effective surface diversity

| Surface | Raw count | Globally distinct text |
|---|---:|---:|
| Memory content | 4,608 | 4,563 |
| Relation edge fact | 240 | 235 |
| Query text | 240 | 170 |
| Entity display name | 384 | 225 |

All text remains unique within its owner scope. Cross-owner equality is permitted by
the corrected scope-local contract and supplies isolation pressure. However, 240 query
slots must not be described as 240 distinct natural-language phrasings. Repeated text
and shared synthetic templates also mean that raw query counts should not be treated
as independent statistical samples. The first retrieval report must retain these
effective diversity counts alongside its aggregate scores.

The corpus remains synthetic; structural validity does not establish semantic
faithfulness. An independent review pass is still required to assess the relation,
entity, temporal, and question wording against the frozen briefs.

## Validation and next step

The targeted review and compile suite passed: 22 tests. The next command is the existing
48-batch review with an explicit 48-call cap. It uses a separate review prompt and
cache, with the same configured model by default; this is an independent pass, not an
independent-model or human audit. Rejections are preserved and block compilation.
The semantic review and all retrieval metrics remain unopened.
