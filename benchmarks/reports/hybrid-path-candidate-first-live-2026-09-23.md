# Hybrid path-candidate assembly: first live opened-corpus result

Date: 2026-09-23

Runner: `doppel.hybrid-path-candidate-ablation.v1`

Dataset fingerprint: `dea12fa561160f72cb2d8fcc4b4e467ae2e6556096724125dbd943a5036b094a`

Result SHA-256: `0df133274ce27263bf0a9ad12e885e74908ec960ac619002e4639184736cf0e9`

## Outcome

The pre-registered gate **failed** on one label. The result is retained rather than
rewritten.

| profile | evidence recall | complete evidence | missing | forbidden | related noise | recovery | average candidates | p50 | p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lexical + pgvector | 0.900 | 0.833 | 4 | 1 | 5 | 0.750 | 1.889 | 12.730 ms | 29.893 ms |
| typed path | 1.000 | 1.000 | 0 | 0 | 5 | 1.000 | 1.250 | 19.060 ms | 40.092 ms |
| assembled union | 1.000 | 1.000 | 0 | 1 | 5 | 1.000 | 2.000 | 38.399 ms | 63.716 ms |

The assembly gained `+0.100` evidence recall and `+0.166667` complete-evidence rate
over the independent branch. It matched the typed-path ceiling. All 36 queries ran;
27 paths were retained, no input hit failed Store revalidation, no path was omitted by
the context budget, no output crossed scope, and both Neo4j and PostgreSQL cleanup
completed. External HTTP, paid LLM calls, and provider tokens were all zero.

## Why the gate failed

The sole flagged item was `m-orphan-1` for
`q-orphan-missing-second-provenance` (“护照经由小李最终在哪里？”). The record says
“护照由小李保管。” It is owner-authored, current at the requested time, in the exact
authorized scope, and has valid Store provenance. The graph's second hop (“小李目前在
北京”) deliberately lacks a memory ID, so the typed-path index correctly refuses to
return a complete path.

The old path-only dataset labels the first-hop memory as forbidden because it must not
masquerade as a **complete path answer**. That does not make the same record forbidden
as an **independent related candidate**. Applying the path-completeness label unchanged
to the assembled candidate set conflicts with Doppel's retrieval contract:
`answer_support` is `unassessed`, and a later model is allowed to inspect useful but
insufficient evidence.

No runtime or query-specific special case will be added. Before another run, the
benchmark contract must generically distinguish:

- hard forbidden evidence: wrong scope, inactive at the requested time, disallowed
  authority/lifecycle, or missing authoritative provenance;
- incomplete-but-valid related evidence: safe to retrieve, but not proof of the full
  requested chain.

The second category should be counted like candidate noise/context, not as a security
or temporal failure. The runner version and pre-registration must change before this
opened result is rerun under the corrected semantics.
