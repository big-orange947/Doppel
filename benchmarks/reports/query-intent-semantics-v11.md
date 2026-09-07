# Query intent semantics v11

Date: 2026-09-07. This is a protocol/data correction, not a retrieval-score claim.

## Finding

The cached Reference Planner v9 classified q60 (`who recommended this book?`) as
history while emitting no explicit time. Plan binding then correctly supplied the
domain-neutral historical-status filter. The required memory is a confirmed,
currently known relationship fact, so Store revalidation loaded it and the
structural gate correctly rejected it with `temporal_status_mismatch`.

The same ambiguity existed in q31/q32 gold: both lookup and history were accepted
for currently known recommendation facts. This made the evaluator treat the bad
intent as acceptable while retrieval lost valid evidence. The time gate was not
at fault and has not been loosened.

## Corrected semantics

- `lookup`: an enduring fact or relationship currently known to the memory system,
  including origin, authorship, attribution, recommendation, and who performed an
  action. Grammatical past tense alone does not select history.
- `history`: superseded/ended prior states or completed historical occurrences the
  user actually asks to inspect.
- `as_of`: state at an explicit historical point; explicit intervals retain their
  existing validity-over-status behavior.
- `current` and `planned`: unchanged.

Reference Planner instructions are version 11. The engine still binds omitted
history status to `historical`; a host explicitly selecting history continues to
receive strict historical semantics. This preserves the separation between a bad
plan and safe execution.

Dataset v1.3 removes history from accepted intents for q21/q23/q24/q30 and
q31/q32/q60. The first four are answer-absent relation adversaries; their intent
label still must be correct independently of whether evidence exists. The semantic
validator now rejects a lookup query that accepts history when all required
fixtures are current/timeless and no historical time constraint exists. This is
generic fixture consistency validation, not a query-ID or phrase exception.

The resulting dataset fingerprint is
`07e01ff865db4de156b692f4e31aac96348a1fc23bc4d3659807620dfacc6619`.
Cached v9 drafts belong only to v1.2 reports and
must fail binding against v1.3. Generate fresh Planner results for the next natural
Planner evaluation; do not edit or relabel the historical raw reports.
