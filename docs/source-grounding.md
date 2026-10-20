# Source-grounded extraction review (experimental)

`doppel_memory.source_grounding.SourceGroundedPersonalMemoryAnalyzer` decorates
an existing analyzer with one optional, bounded, source-only review. It is
module-only experimental and does not replace the default analyzer or write
directly to Store.

```python
from doppel_memory.source_grounding import SourceGroundedPersonalMemoryAnalyzer

analyzer = SourceGroundedPersonalMemoryAnalyzer(base_analyzer, review_model)
# Supply analyzer to the ordinary PersonalMemoryMiner or PersonalMemoryExtractor.
```

The review receives candidate content, type, subject, status, cited IDs and the
original cited messages with actor/observation time. It receives no query, gold
answer, old grade, new scope authority or permission to repair memories. Every
eligible draft needs exactly one decision; its quotes must match exact original
text belonging to that draft's citations. Unknown evidence IDs stay with the
ordinary miner fail_batch/quarantine policy and are never repaired.

The default `contradiction_policy="annotate"` retains every proposal, including
high-confidence contradictory reviews, with source-grounding metadata. Transient
claims preserve the typed annotation and exact source quotes; queries retain
disputed candidates with explicit warnings and do not certify an exact count
from them. Supported judgments also remain unverified candidates. Original raw
history and previously stored records are untouched. The wrapper changes its
analyzer identity/version; use a fresh checkpoint/journal, not an old miner run.
Ordinary actor/subject/scope/state gates still run after review. Request hash,
model identity, judgments and exact quotes remain auditable; observer failure,
invalid coverage/quotes, excessive size or provider failure stop the operation.
There is no automatic retry, source truncation or model repair.

Explicit `contradiction_policy="withhold"` omits only confidence>=0.8 model
contradictions. It is experimental, not recommended as a default: the first
real-window test caught2 completion errors but also rejected a valid owner claim
because it used an unrelated assistant statement as counterevidence. Keep that
failure visible; source quote validation does not isolate model reasoning.

This can flag a paraphrase turning “decided/intended/cancelled” into “completed”.
It is still an LLM judgment, not a formal entailment proof or independent
verification. Exact quote matching proves provenance, not that the verdict is
correct. False positives can mislead a Reader even when recall is retained, so
preserve raw fallback and measure precision/coverage before any promotion.
The wrapper reviews content entailment, not every structural type or normalized
date. It does not certify event identity, calendar arithmetic or exact counts.

Separately, interval queries now flag impossible duration/precision combinations
(e.g. a week labeled day). They retain the candidate and original bounds/label,
mark the precision unreliable, and do not certify an exact interval count. The
duration sanity check tolerates a one-hour DST shift and second/microsecond
closed ends; passing it is only necessary plausibility, not calendar alignment
or semantic correctness. No noun, benchmark ID or entity-specific date rule is
used. Defaults/older prompt/schema bytes are unchanged; diagnostics/engine source
fingerprints change, so prior frozen experiments retain their original Git pins.
