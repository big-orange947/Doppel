# Combined retrieval V2 — bounded exploration preregistration

This protocol was frozen after opening the text-only topology baseline and before
running the new Graphiti exploration profile against live Neo4j. The dataset, graph
fixtures, authority labels, and required evidence are unchanged.

## Compared profiles

1. independent lexical + pgvector;
2. reviewed typed relation paths from the frozen provider report;
3. bounded Graphiti exploration without a text-selected hidden first hop;
4. the existing independent + typed-path assembly;
5. independent + deduplicated typed and explored paths.

The existing typed-only profiles and legacy quality gate remain unchanged. Exploration
has a separate gate because it is designed to compensate for a known text-only
topology limitation, not to rewrite that failed baseline.

## Frozen exploration behavior

- exact caller-provided scopes only;
- one or two hops, with at most 256 scanned paths per query in this run;
- only relation types from the dataset's host ontology;
- no LLM, external HTTP, or provider tokens;
- valid-time filtering inside Neo4j and repeated in Python;
- every hop must resolve Edge → Episode → memory ID → eligible authoritative Store
  record;
- typed and explored duplicates merge by scope, edge IDs, and directions;
- independent candidates retain their reservation in the 20-candidate context bound;
- path discovery is not evidence sufficiency and remains `answer_support=unassessed`.

## Frozen success gate

The exploration-enhanced hybrid must satisfy all of the following:

- overall evidence recall@5 does not regress versus typed-only hybrid;
- complete evidence@10 does not regress;
- semantic-nonrelation recall@5 does not regress;
- two-hop complete-evidence@10 improves by at least 0.15;
- hard-forbidden hits, scope leakage, ineligible hits, orphan provenance, temporal
  complete-path failures, and Store revalidation failures are all zero;
- no complete path is omitted by the assembly budget;
- maximum candidates per query remains at most 20;
- Neo4j fixtures and the PostgreSQL benchmark schema are cleaned after the run.

The old provider topology gate is reported but is not required by this additive
exploration gate. Its failed 0.500 overall and 0.292 aggregate two-hop recall remain
part of the permanent baseline.
