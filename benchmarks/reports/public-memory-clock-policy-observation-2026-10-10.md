# Public-history clock audit: do not confuse task reference and knowledge cutoff

This is a zero-provider-call, read-only diagnostic of the existing opened 50-case
corpus. No question selection, answer score, source timestamp, database or old
receipt was changed. It exposes a protocol distinction to resolve **after** the
already-frozen third natural-query diagnostic, not a rule to fit individual tests.

## Local observations

Comparing derived-record `created_at` against each supplied `question_date` found
794 later-created records across eight of the fifty scopes. All other scopes
have zero. Counts include all stored personal memories, not a new graph-eligible
record count. This inventory does not establish that a record was retrieved or
used in an answer.

| Fixed scope ordinal | Later than question time |
| --- | ---: |
| 2 | 31 |
| 5 | 195 |
| 11 | 191 |
| 17 | 39 |
| 20 | 10 |
| 23 | 111 |
| 29 | 214 |
| 41 | 3 |

All fifty scopes have zero earlier-created personal records with a parseable
later-than-question evidence `at`; no malformed evidence timestamps were found.
That is an observation about this corpus, **not** proof that arbitrary consolidated
records cannot contain later-added evidence. The production limitation remains.

Post-selection inspection of public scoring annotations also found four scopes
whose official evidence sessions themselves occur after the question's minute:
5, 11, 23 and 29. All such examples are on the same calendar day. For example,
scope 11's question timestamp is April 19 at 00:38 while its two designated
evidence sessions are at 02:37 and 03:31. Under the local **strict minute-level
causal replay** protocol those sessions are not yet observable. No increase of
top-k, embedding quality or graph hops can recover legitimately excluded sources.
This is a protocol/annotation-clock mismatch, not automatically a retrieval miss.

Annotations were examined only in this diagnostic after the frozen selection;
they must never choose a cutoff, a context item, graph projection or per-case fix.
Preserve earlier scores with their original rules; do not subtract these cases
post hoc to manufacture a better headline score.

## Upstream task contract and implication

The [official LongMemEval README](https://github.com/xiaowu0162/LongMemEval#-longmemeval-overview)
describes answering after the interaction history, and its system-testing
instructions provide the timestamped history. It defines question and history
timestamps separately; it does not specify the added local rule of discarding
every supplied session after the question's exact minute.

Therefore our strict clock replay is a distinct diagnostic, not a reproduction
of the official complete-provided-history protocol. This interpretation combines
the upstream task description with the actual timestamp/annotation observations;
it is not a claim of a new upstream benchmark defect or official approval.

## Next protocol, not a production exception

Keep real personal-agent defaults strict: sources not known at the host clock
must not influence the query. Design an additive, host-controlled distinction
between **question/valid-time reference** and **observations available through**.
The LLM planner must not grant itself a wider observation horizon.

For an imported complete-history evaluation, derive any supplied-history horizon
uniformly from runtime source timestamps (no gold/labels/answerability), retain
the question reference for relative dates and current/as-of semantics, and declare
that policy explicitly in the frozen plan. Strict replay and complete-history
results remain separate profiles; report all assigned cases, including clock
incompatibilities, rather than selecting a successful denominator.

Do not round times only for temporal questions, use a benchmark-ID allowlist,
shift sessions to precede gold, change `created_at`, or remove the new production
gate. Freeze synthetic independent-clock tests and the new interface/protocol
before another paid query cohort. The current third-history run stays on its
existing protocol and has no later-created records in this audit.
