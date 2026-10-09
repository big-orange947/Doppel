# Consecutive high-config diagnostic: histories 2 and 3

## Selection and immutable prior results

Use the next two complete scopes in the existing ingestion order, after the
completed first scope. Selection reads only ingestion/scope/source metadata,
never question text, answerability, reference answers, annotated evidence or past
scores. Targets are 183 and 222 confirmed eligible personal-memory records.
No reserved history or newly sampled dataset is opened. This is development on
already-opened LongMemEval histories, not independent blind or AML results.

The first natural query's answer/score and V1 `degraded=true` label remain intact.
The new `doppel.high-config-execution-contract.v2` separates execution failure,
bounded retrieval coverage, source coverage and aggregation completeness. Unknown
warnings require review. A correct answer cannot override backend failure, source
loss or an exact count from an incomplete scan. An empty graph path candidate set
does not force a graph reranker call or establish graph benefit. The new contract
does not grant publication acceptance or change task accuracy.

Its zero-call derived first-query receipt SHA-256 is
`c745054865fe6cd988af8e8de0743a3e34ad920298bca81d5cb79088b0be7037`.
That receipt classifies the first query as completed within a bounded top-k
contract and preserves both legacy labels, answers and grades, unmodified.

## Frozen source-only graph batch

Batch plan fingerprint:
`aaea3125f8ce1edb17fd78089857ed1dbfb541714c78ba18db312538a132ab00`.
Preflight receipt SHA-256:
`44cabc168b12566d5d7c7581aee756e534d8df85577e88fb09d9e9d16022f94b`.

| Scope ordinal | Complete targets | Plan fingerprint |
| --- | ---: | --- |
| 2 | 183 | `0326b7b79bba99294468273a71b06ddddf996b5413b845c9458bf15d2bd5c5bc` |
| 3 | 222 | `7ec4a399822d38e9927e08e57d1ad1fcfc3f6e97dad9f85f764da017b1021eb8` |

Each has a new independent durable maximum of 1500 provider attempts,
500000 canonical bytes per request and 32000000 total canonical request bytes;
both together at most 3000 attempts / 64000000 bytes. These are ceilings, not
estimated or promised costs, and not exact monetary/token hard caps. All calls
and usage are retained, including failure and interruption. No automatic retries.
Execute sequentially, starting with scope 2. Stop and report authentication,
balance, provider, graph, scope or provenance errors rather than forcing completion.

Reuse the current real Graphiti writer, fixed DeepSeek 8192-output-token cap and
existing local embedding identity. Project every eligible record in each selected
scope, never a question-targeted subset. No fixture relations, re-extraction,
ontology relabeling or evidence repair. Successful graph data is retained; owned
incomplete slots use the existing journal/cache/resume discipline.

Store and pgvector connections are read-only. Global Store corpus hash must stay
`11aab45f1bdfaebeea23bee822e53e5cdd94aef24f68bb020d90e9eda35e9cc3`;
all 34760 active vector manifests must stay current. Compare every other diagnostic
scope's graph nodes, episodes and edges before/after each write invocation, including
the already-complete first history. One complete scope does not certify full-corpus
graph coverage. No unrelated containers, schemas or graph data are reset.

## Query protocol after projection

Only after graph coverage and schema readiness checks, freeze a separate exact
query plan binding these receipts, dataset/journal hashes, schema definitions,
model identities and implementation sources. Use the existing V7 natural planner,
evidence-rich V8 production composition, local BGE pgvector and CUDA CrossEncoder.
Same fixed memory/raw/backing whole-item packing: 20 items / 24000 UTF-8 bytes.
No query/gold-derived ranking, ontology choice or source selection.

Schema generation sees only distinct graph type names in fixed 24-name batches,
4096 output tokens, no facts, entities, questions or answers. Its actual type count
determines a separate frozen call ceiling before authoring. No silent type slicing.
Definitions remain fallible and are not independently verified.

Each query has at most five calls: two V7 passes, one unchanged Reader v2, one
reference-only task judge and one citation-support judge. Failed stages are retained
without silent retries. Gold enters judges/scoring only, never retrieval or Reader.
Report the existing vector baselines separately; do not merge protocol scores or
attribute an improvement to Graphiti without actual graph contribution evidence.
Do not tune prompts or algorithms between these fixed questions based on outcomes.
Language drift, unsupported/contradictory answers, source coverage and new execution
status are all reported independently. No warm-GPU latency experiment this round.
