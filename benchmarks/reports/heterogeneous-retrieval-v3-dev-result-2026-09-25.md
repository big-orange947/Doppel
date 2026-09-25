# Heterogeneous retrieval V3 — opened dev diagnostic

This run opened only the 120 dev queries after the V3 oracle count-plan fields and the
generic literal-entity reservation were committed. No sealed or adversarial result was
opened.

- implementation commit: `15c12791ce209219e1afb24b6f40d724bb97f355`
- dataset fingerprint:
  `ead91761f9da403c31c8b759d427c4551709daf7d29f35d26d786f94ec167f88`
- report payload hash:
  `e009da6e0e854ecec294a767d0086d242d23282e90c4e2a89ffb5a283b53222d`
- ignored raw file SHA-256:
  `4850b7aa66cc502aab27afc0764f4fab2d2af150d4a675a5ae3d4a7f18f3670f`
- external HTTP / LLM calls / provider tokens: `0 / 0 / 0`

The highest-quality profile reached 0.992 evidence recall@5, 0.991 complete
evidence@10, and 0.958 MRR. Exact event-key-aware episode counting reached 1.000.
Every answerable category cleared the unchanged per-category threshold. All structural
safety, Store revalidation, candidate membership, path budget, context bound, and
backend cleanup checks passed.

The only quality check besides the expected dev-only selection failure was
related-evidence recall@10: 5/12. Candidate-window related recall remained 12/12 and
all 12 related records were present by rank 20. `entity_anchor_reserve` fired on all 12
queries, but the corpus deliberately contains several same-entity maintenance notes.
Literal binding can preserve one named-object record; it cannot generically decide
which predicate supplies the most useful adjacent context.

Increasing the literal reservation would trade one arbitrary same-entity record for
several and consume context without using Doppel's typed relation structure. The next
runner revision therefore keeps this result intact and adds bounded Graphiti
exploration as a distinct source/profile. For an unsupported requested predicate such
as buyer, the exact-path branch still abstains while graph exploration may contribute
an existing typed adjacent relation such as holder. That contribution remains
`answer_support=unassessed` and passes the same Store, scope, time, authority, and path
atomicity gates.
