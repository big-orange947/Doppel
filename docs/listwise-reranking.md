# Optional listwise relevance ranking

For an explicit **up-to-k** filter that leaves the remainder unranked, see
[bounded evidence selection](topk-selection.md). The complete-permutation scorer
below is a separate contract; its failed smoke is not rescored by that addition.

`doppel_memory.reference_rerank.ReferencePersonalMemoryReranker` implements the
existing `PersonalMemoryReranker` protocol with a supplied `StructuredOutputModel`.
It is opt-in: no retrieval, model, source-diversity or Graphiti default changes.

The model receives a question and an already-authorized candidate window with
request-local IDs. It returns a complete permutation of those IDs. The adapter
validates that permutation and converts rank to a monotone ordinal score in
`[0, 1]`; these scores are **not relevance probabilities or confidence** and should
not be used as an evidence-qualification threshold.

```python
from doppel_memory.reference_rerank import ReferencePersonalMemoryReranker
from doppel_memory.source_aware_rerank import SourceAwareReranker

# structured_model is supplied by the host, including its own budget/cache policy.
scorer = ReferencePersonalMemoryReranker(structured_model)
reranker = SourceAwareReranker(scorer)  # metadata enabled, diversity weight zero
```

Use `reranker` at an authorized retrieval boundary, such as the reference
`AttributedContextRetriever` or `AttributedPassageRetriever`. Those integration
adapters are repo reference code, not part of the packaged SDK. They reload Store
records and consume only returned order. Actor, authority, source text and exact
scope must never come from model output.

The scorer itself does **not** authorize candidates or read/write a Store. Its
default hard bounds are 80 candidates and 300,000 input characters, including
question and IDs. Overflow fails before generation; it does not silently shorten
source text. An empty window makes no call. Generation errors, unknown/duplicate/
omitted IDs, extra output fields and mutated request/model identity fail without
repair or automatic retry. The supplied model may have its own transport policy;
the host must disable retries and use durable accounting when strict cost limits
are required. Input instructions are separated from untrusted evidence, but this
is not a claim that prompt injection cannot affect model ranking.

Unlike a local cross-encoder, this can reason across a small set of complementary
records, but adds network cost and latency. It cannot recover evidence absent from
the candidate pool, guarantee complete counts, resolve all temporal ambiguity or
make an assistant suggestion into an owner fact. Validate on an untouched set
before considering deployment; opened diagnostic examples establish no general
accuracy advantage.
