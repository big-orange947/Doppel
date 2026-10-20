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

Only contradicted decisions with confidence >=0.8 are omitted from the returned
proposal analysis. Uncertain or lower-confidence judgments are preserved with
review metadata; supported judgments remain unverified candidates. Original raw
history and previously stored records are untouched. The wrapper changes its
analyzer identity/version; use a fresh checkpoint/journal, not an old miner run.
Ordinary actor/subject/scope/state gates still run after review. Request hash,
model identity, judgments and exact quotes remain auditable; observer failure,
invalid coverage/quotes, excessive size or provider failure stop the operation.
There is no automatic retry, source truncation or model repair.

This can catch a paraphrase turning “decided/intended/cancelled” into “completed”.
It is still an LLM judgment, not a formal entailment proof or independent
verification. Exact quote matching proves provenance, not that the verdict is
correct. False positives can remove useful proposals, so preserve raw fallback,
review rejected items and measure precision/coverage before default promotion.
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
