# Personal relation ablation zh-v2 — draft annotation notes

This file documents the checked-in
`personal-relation-ablation-zh-v2.json` candidate dataset. It is an engineering
artifact, not a publication-ready or genuinely blind evaluation set.

## Size and fixed split

- 12 exact owner scopes
- 72 authoritative memory fixtures
- 240 unique queries
- 72 development queries
- 96 preassigned held-out queries
- 72 adversarial queries
- 14 relation types
- 24 same-entity scenarios; every named entity occurs in two different owner scopes

Each scenario contributes ten query shapes before any runtime result is inspected:

1. canonical current relation;
2. colloquial current paraphrase;
3. prior relation state;
4. explicit historical point-in-time boundary;
5. second relation over the same entity;
6. colloquial paraphrase of that second relation;
7. explicit negated-relation contrast;
8. a predicate with no direct evidence but useful same-entity context;
9. an unknown entity;
10. an explicit historical calendar interval.

The positions deterministically assign dev/held-out/adversarial partitions. This
prevents moving a failed query into an easier partition after seeing scores. Because
the JSON and generator are public, “held-out” means not used for threshold selection;
it is not secret blind gold. A later release needs independently authored sealed
queries after the retrieval configuration is frozen.

## Relevance rubric

Every query explicitly judges every one of the 72 fixtures:

- `2`: directly supports the requested answer;
- `1`: useful related context, but does not establish the requested answer;
- `0`: irrelevant, cross-owner, or explicitly excluded by the question.

The grade is independent of vector, graph, lexical, or reranker scores. Cross-owner
memories are always grade 0 even when entity names are identical. A current and prior
state may be grade 2/1 depending on the requested time. A different true relation on
the same entity is normally grade 1; an explicitly negated relation is grade 0.

The 24 `related_but_insufficient` queries intentionally have no grade-2 evidence and
at least one grade-1 memory. For example, a location/custody memory can be useful
context for a question asking who lent an item, but it cannot prove the lender. These
cases retain legacy `expected_abstain=true` so old empty/nonempty metrics remain
comparable; nDCG is the authoritative signal for whether related context was ranked
usefully. This known tension is why legacy abstention is not answer correctness.

The 24 `unknown_entity` cases have only grade-0 judgments. They test genuine
abstention and are excluded from nDCG when the ideal gain is zero.

## Generation and integrity

The source-of-truth scenario matrix lives in
`benchmarks/build_personal_relation_v2.py`. Regenerate or verify it with:

```bash
python -m benchmarks.build_personal_relation_v2
python -m benchmarks.build_personal_relation_v2 --check
```

The generated JSON is checked in; benchmark execution reads the JSON directly and
does not execute the generator. Semantic validation requires:

- the full fixture corpus to be judged for every query;
- all required answer memories to have grade 2;
- cross-scope memories to have grade 0;
- every related-context case to contain grade 1 and no grade 2;
- a relation-type label for every query;
- the declared minimum partition sizes.

Draft.1 fingerprint:

```text
b899720a02646cf316672dafd1cae3286ff4518a9406127e67cc07f646078d45
```

## Before freezing

The generated wording and initial 0/1/2 labels still require an independent manual
semantic review. Reviewers should inspect the question, memory content, validity
interval, scope, and relation endpoints without looking at model scores. Corrections
must bump the draft version and fingerprint. Only after review should a configuration
be selected on `dev`; held-out/adversarial results must remain untouched until that
selection is fixed.
