# First complete history: natural high-config diagnostic preregistration

This is one already-opened LongMemEval-S history, selected by the existing
ingestion order, not by expected answerability. It is not a new blind evaluation,
the complete LongMemEval benchmark, a comparison-winning claim, or AML results.
Other 49 histories are not graph-ready. No reserved history is executed.

## Stage A: source-only schema

Before loading the question, read every rich edge in the completed first scope.
There are 229 edges and 142 distinct relation names. Preserve all names without
merging or migrating existing graph data. The old exploration ontology cap of
128 cannot express this source; expand that bound to 512 without changing hop,
candidate, time or authority constraints.

The schema author sees only sorted distinct relation names, in fixed batches of
24. It does not see endpoints, edge facts, question text, benchmark identifiers,
answer keys, evidence labels, previous answers or scores. Generated definitions
are fallible inferred meanings, not an independently verified ontology.

Frozen schema plan fingerprint:
`56da2dea66d3ec3e6209fe0167c2e7791bd1c6b68895f8d9f2aac064d6285d8f`.
At most six single-attempt DeepSeek requests, 4096 output tokens each, 100000
canonical request bytes each / 600000 total. Preserve failures and cached outputs;
no automatic retries or prompt changes. Require exact coverage of every name.
Graph snapshot must remain identical before and after schema preparation.

## Stage B: first natural query

Freeze a separate plan before execution, binding the source dataset, manifest,
ingestion receipt/journal, complete first-scope graph receipt, generated ontology,
model identities and source code. Use production HighConfigRetrieval with V7
natural planner, lexical and existing local BGE pgvector, Graphiti typed relation
and one/two-hop exploration, local BGE CrossEncoder on CUDA, and source backing.
Backend and reranker degradation is reported and must not be described as full
success. No reference answer, evidence label or source position drives retrieval.

Fixed Reader budget: 20 whole items / 24000 canonical UTF-8 bytes. Pack memory,
independent raw dialogue and backing sources in cyclic rank order; deduplicate
by memory ID, skip oversized whole items, never trim source text. Preserve role,
authority and effective/observation dates. Report each packing decision. This
host policy is not claimed optimal or equivalent to the older vector profiles.

Reuse Reader v2 unchanged instructions and schema. A requested exact count, if
present, is supplied separately as structured retrieval aggregation; it is not
recomputed from top-k or invented as a source memory. Keep gold outside planner,
retrieval, reranking, packing and Reader. Reference-only task judge grades the
answer; separate citation judge audits support. Both are fallible same-provider
judgments and are not independent validation. Maximum five single-attempt calls:
two planner passes, one Reader, one task judge and one citation judge. No adaptive
prompt tuning based on this question's answer or score.

Read-only Store/graph snapshots before and after; report no record/index writes.
Keep prior 50-question scores and all prior failed graph probes intact. Cache-only
replay may verify request/answer stability, not substitute for a fresh benchmark.
