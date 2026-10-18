# Optional evidence selection: upper bound, not a quota

`doppel_memory.bounded_selection.BoundedTopKSelector` uses a host-supplied
`StructuredOutputModel` to select up to k already-authorized candidates. It
implements the existing `Reranker` protocol directly, so no all-candidate relevance
scores or invented judgments are required.

```python
from doppel_memory.bounded_selection import BoundedTopKSelector

# Supply your own structured model, budget, cache and transport retry policy.
selector = BoundedTopKSelector(structured_model)
# Pass selector as reranker at an authorized retrieval boundary.
```

Only selected unchanged `RecallResult` snapshots are returned. Unselected IDs in
`last_selection.unranked_ids` are request-local and explicitly unranked, not facts
classified as false, forbidden or irrelevant. Original similarity fields are
preserved; they are not replaced with LLM confidence. Empty/short output is valid
under this contract and must remain visible downstream. Inclusion does not imply
answerability or completeness; omission does not prove a fact absent.

The model receives query, opaque IDs, original text and actor/authority/supplied
time. There are no role quotas or scenario-specific mappings. Scope identifiers
and persistent record/source IDs are not included by this adapter. Sources must
be authorized **before** selection; reload/revocation checks remain the caller's
responsibility. The repo reference attributed-context/passage adapters perform
these checks and consume only the returned order/selection.

Defaults: at most80 candidates/300,000 input characters,120-second adapter timeout.
Oversized inputs fail before a call, not by silently truncating source text. The
host supplies a positive k within the candidate bound. For a shorter pool, the
upper bound becomes min(k, pool size). Empty pools make no call. Output must use
unique input IDs and contain no more than that bound, with no extra fields. Invalid
outputs, request/identity mutation and generation failures do not trigger padding,
repair, retries or a successful fallback. A supplied transport can still retry;
disable it and add durable ledgers when controlling cost. Timeout/unknown usage
must not be reported as zero spend. Prompt separation is not a guarantee against
model ranking errors or prompt injection.

`ReferenceTopKSelector` remains a separate **exact-k** contract for hosts that
explicitly need that cardinality. `ReferencePersonalMemoryReranker` remains the
older complete-permutation scorer. Neither failed smoke is rescored by introducing
the bounded selector. All remain opt-in; no production retrieval/model defaults or
top-level frozen exports change. Network cost and quality require validation on
untouched data before deployment.
