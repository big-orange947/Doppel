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

## Isolated speaker review candidate (V2)

`SourceGroundedPersonalMemoryAnalyzerV2` is a separate module-only opt-in:

```python
from doppel_memory.source_grounding import SourceGroundedPersonalMemoryAnalyzerV2

analyzer = SourceGroundedPersonalMemoryAnalyzerV2(base_analyzer, review_model)
```

V2 sends one eligible draft per independent model request, containing only that
draft's cited original messages. Other drafts' sources are physically absent
from the request. A speaker frame binds each cited source to its actor and the
host's owner/agent ID or contact sender ID; identifiers are not display names.
Generic perspective instructions cover first-person clauses, embedded quotations,
negation and predicates about other people. No names or topic dictionaries drive
runtime decisions. Source-quote checks still enforce exact original text, not
semantic entailment. The review remains a model judgment and cannot repair a
claim or authorize an identity.

This adds cost: V1 makes one review call per eligible window; V2 can make up to
`config.max_drafts` calls (default 40). The host must provide attempt budgets and
output caching. All per-request byte limits are checked before the first review
call; each response is validated before proceeding. Failure returns no partial
analysis, although earlier requests may already have incurred cost. A bounded
caller may stop before all drafts are reviewed. Do not represent it as a complete
review or refund its attempts. This does not add a scheduler or automatic retry.

Default policy remains `annotate`: high-confidence disputes retain the original
candidate and source quotes. Supported results do not confirm facts or bypass
miner authority gates. Separate version/checkpoint/cache identities are required;
V1 request shape, prompt/schema and version-binding formula remain unchanged.
The [prospective control plan](../benchmarks/reports/source-attribution-controls-plan-2026-11-11.md)
defines the first comparison. Control success alone does not justify default promotion.
The [first result](../benchmarks/reports/source-attribution-controls-result-2026-11-11.md)
matched 7/8 candidate judgments vs 6/8 for V1, with one remaining quotation-subject
miss in both arms. V2 cost more calls/tokens. It stays an explicit candidate,
without a default change or claim that the prior lifecycle failure is repaired.

Separately, interval queries now flag impossible duration/precision combinations
(e.g. a week labeled day). They retain the candidate and original bounds/label,
mark the precision unreliable, and do not certify an exact interval count. The
duration sanity check tolerates a one-hour DST shift and second/microsecond
closed ends; passing it is only necessary plausibility, not calendar alignment
or semantic correctness. No noun, benchmark ID or entity-specific date rule is
used. Defaults/older prompt/schema bytes are unchanged; diagnostics/engine source
fingerprints change, so prior frozen experiments retain their original Git pins.
