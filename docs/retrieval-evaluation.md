# Retrieval evaluation boundary

Doppel separates candidate discovery from answer judgment. A retrieval hit means an
authorized, structurally eligible Store record was discovered and ranked; it does not
mean that the record proves the requested claim.

## Runtime candidate evidence

`PersonalMemoryQueryHit.candidate_evidence` exposes:

- accepted discovery sources (`lexical`, `semantic`, named composite semantic
  sources, and relation providers);
- entity binding (`literal`, `relation`, `unverified`, or `not_requested`);
- relation source, type, edge ID, and match kind when available;
- whether the candidate was reloaded from the authoritative Store.

`answer_support` is deliberately fixed to `unassessed`. The query engine cannot infer
that `book HELD_BY Lin` proves `book PURCHASED_BY who`; an answer layer, optional
evidence verifier, or future context selector must make that judgment.

The existing `reasons` list remains available for compatibility. New integrations
should prefer the structured object instead of parsing reason strings.

## Evaluation semantics v4

Benchmark gold may assign a `judged_evidence_role` that is never provided to the
runtime system:

- grade 2: `direct_evidence`;
- grade 1: `related_context`;
- grade 0: `non_evidence`;
- missing judgment: `unjudged`.

Reports distinguish accepted-candidate direct-evidence recall at 10/20 from ranked
Recall@1/5 and nDCG@5. A no-evidence query records whether the candidate pool is empty
or nonempty, but candidate presence is not called answer failure. Actual answer
abstention remains `null`/not measured until an answer-generation evaluation runs.

The legacy `no_evidence_abstention_accuracy` output is retained as a deprecated alias
of candidate-empty rate so older report consumers do not break. It is excluded from
the paired Planner promotion gate. Dataset exclusions are also retrieval diagnostics,
not scope or authorization violations.

A trusted-plan dataset exclusion is emitted as the case-level
`candidate_diagnostics=["forbidden_candidate_returned"]` signal rather than a
`retrieval_failure`. A related or contradictory candidate may still be useful context
that an answer model correctly rejects. Only an answer-level evaluation can decide
whether returning it caused a factual error.

Hard safety gates/security gates remain:

- exact authorized scope and subject;
- factual authority and lifecycle state;
- temporal validity;
- provenance checks in the benchmark;
- authoritative Store reload for derived index candidates.

This split prevents a retrieval implementation from improving a supposed
"abstention" score merely by withholding context that a capable model could inspect.
Future context-selection and answer-level suites will measure token-budget precision,
grounded answer correctness, unsupported claims, and genuine abstention separately.
