# Prospective property-atomic extraction contract

This is the design target of opt-in `ReferencePersonalMemoryAnalyzerV10`, not a
new Store schema, default migration or hard semantic guarantee. V8 remains the
default. V9's frozen preservation result remains **7/8 and gate failed**; its coat
fixture and expectation are not changed or rescored under this contract.

## The unit of an updatable memory

A mutable fact, state, preference or relationship describes one independently
updatable property of one subject. Separate properties of one entity remain
separate drafts, with property-specific topic keys when justified. This prevents
a correction of one property from being treated as a replacement of everything
known about that entity. It does not enforce a particular sentence length.

Equivalent mentions of the same property/value can merge with all actual supporting
sources. Different values, modalities or effective periods stay source-bound and
separate. Compatible enrichment means compatible information about the **same
property**, not arbitrary information about the same entity. Omit a key rather than
inventing a stable slot. Topic-key identity is a model interpretation, not verified
ontology alignment or a universal guarantee of conflict detection.

An episode may include several compatible details of the **same proved occurrence**.
Different occurrences must not merge merely because participants or places match.
Use event keys only with supported event identity; leave them absent when uncertain.
This contract is not a requirement to extract noise or every utterance.

## Assertions and revisions

Negative polarity, a different value or disagreement with an agent is not itself
a withdrawal of the subject's prior assertion. Use `assertion` unless the bound
source explicitly corrects or withdraws that subject's prior claim or commitment.
An explicit revision may identify the earlier claim within its own text; an earlier
message need not be supplied. Do not invent it. Cancellation of an expressed plan
can be a withdrawal; a denial that an event occurred does not establish that event.

Keep original assertions and their supporting sources unchanged. A revision binds
sources supporting the revision, not every earlier message it refers to. Existing
schema has no explicit revision-target relation: automatic target resolution still
belongs to audited governance, and remains a limitation. We do not add a keyword
negation detector or claim that prompt instructions are enforceable semantic gates.

Source/subject/authority checks, candidate status and schema diagnostics remain
unchanged. Source quote matches prove binding, not that a model understood a speech
act. Observation timestamps never establish effective dates. Calendar-date precision
and timezone ambiguity remain a separate open issue, not fixed by this contract.

## Compatibility and evidence availability

Raw evidence remains available regardless of draft segmentation or advisory conflict.
Nothing here vetoes RAG candidates, forces a Reader to abstain, changes persistent
lifecycle state, applies consolidation or grants scope access. Hosts may continue
using V8 or V9. V10 uses a new model-bound analyzer/cache identity; do not reuse an
old batch checkpoint as if it had this interpretation.

New unrelated development controls test this contract prospectively. They cannot
retroactively pass the old preservation gate, authorize an old task-cohort rerun,
prove independent accuracy or justify default promotion. Paid runs must first bind
and commit fixtures, requests, source digests and their review rules.
