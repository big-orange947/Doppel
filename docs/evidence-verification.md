# Optional evidence-support gate (provisional)

The default query path is unchanged. Hosts may supply an `evidence_verifier`
to `PersonalMemoryQueryEngine` or `DoppelClient.query_personal_memory`.
Types currently live in the provisional `doppel_memory.evidence` submodule.

```python
from doppel_memory.evidence import (
    ReferenceEvidenceVerifier, EvidenceVerificationConfig,
)

result = await client.query_personal_memory(
    question, scopes, planner=planner,
    evidence_verifier=ReferenceEvidenceVerifier(model),
    verification_config=EvidenceVerificationConfig(
        max_candidates=64, batch_size=8, timeout_seconds=30,
    ),
    trace_limit=200,
)
```

`model` is a host-provided StructuredOutputModel. Enabling this feature sends
the original question and authorized candidate memory text to that model;
choose a provider appropriate for the data. Opaque item IDs replace database
IDs. Content itself is not anonymized. The adapter owns no credentials or
retries. Provider token/billing limits remain the host's responsibility.

This gate runs after existing eligibility, time, authority and relevance gates,
before final ranking. It only removes candidates: supported passes, unsupported
and uncertain do not. It judges answer-role support rather than similarity;
inferred relation labels are not supplied as authoritative constraints.
It cannot retrieve missing evidence, prove factual truth, or repair faulty
extraction. Multi-record inference and exact-count verification are not supported.
Count queries with a verifier raise NotImplementedError before retrieval.

Every batch must return exactly one closed-set verdict for each requested ID.
Any invalid batch, timeout or provider exception discards all batch decisions,
returns no verified hits, sets `complete=False`, and emits a content-free warning.
The candidate/input-character limits are checked before calls. The timeout covers
all sequential batches; custom providers must cooperate with asyncio cancellation.
No candidates means no provider call. Inspect `result.evidence_verification` to
distinguish completed, not_run, unavailable and limit_exceeded. This summary does
not assert completeness of retrieval. Trace events contain fixed verdicts, not
provider reasoning or errors. Existing conflict diagnostics remain independent.

Fake-provider tests establish protocol and safety behavior only. Before enabling
by default, compare frozen candidates with and without a real verifier, report
false acceptance AND false rejection, abstention, latency, tokens and costs.
Use a new unseen split as well as existing regressions; do not tune against query
IDs, dataset labels or per-question keywords. No quality improvement is claimed
by this implementation alone.
