# Evidence-bundle judgment V1 — preregistered opened replay

Date: 2026-09-28

Status: implementation and comparison frozen before the first provider result

## Question

V7 is the rank-first control and V8 is the evidence-rich control. Retrieval metrics
show that V8 puts more complete evidence into ten items, but do not show whether a
downstream model can distinguish that support from merely similar graph context. This
replay asks the model only to decide whether the supplied bundle is sufficient and to
select the items that jointly establish the answer.

This is an **opened development replay** over heterogeneous V4. The corpus and its V7
and V8 retrieval results have already been inspected. The run can compare policies and
find integration failures, but cannot become an unseen/publication-quality claim.

## Frozen information boundary

For each query/profile, the model receives at most ten candidates. Candidate IDs are
request-local (`item_01`, `item_02`, ...). It receives the question, question time,
content, kind, source kind, temporal status, and validity interval. It does not receive:

- Store memory IDs or gold labels;
- scope, owner, subject, authority, lifecycle, or provenance fields;
- retrieval source, vector score, graph score, path ID, relation category, or rank
  rationale;
- expected answerability or the expected supporting set.

The model may select supplied items or abstain. It cannot add evidence. A successful
provider response with an unknown item ID is an evaluation error.

## Frozen profiles and metrics

- rank-first: `assembled_semantic_path_exploration_hybrid_memory_reranking`;
- evidence-rich: `assembled_semantic_path_family_exploration_hybrid_memory_reranking`.

Metrics are reported separately for:

1. retrieval sufficiency among source-answerable cases;
2. judgment accuracy conditional on the supplied bundle;
3. abstention on insufficient bundles and source no-answer cases;
4. exact support selection, support precision, and support recall;
5. end-to-end support success among source-answerable cases;
6. related and hard-forbidden items selected as support.

This runner does not score natural-language answer text. “End-to-end support success”
means that retrieval supplied the labeled evidence and the judgment selected all of
it; it is a stricter evidence proxy, not proof that a final answer is fluent or correct.

## Frozen policy comparison

Evidence-rich may be preferred over rank-first only if:

- retrieval sufficiency does not regress;
- end-to-end support success does not regress;
- source-no-answer abstention does not regress;
- overall judgment accuracy regresses by no more than 0.02;
- exact support selection regresses by no more than 0.02;
- no hard-forbidden item is selected and every selected case completes without a
  provider/validation error.

`policy_preference_supported` additionally requires a strict end-to-end support gain.
A tie preserves both controls and does not select V8. No intermediate base guard may
be tuned from this opened replay.

## Budget and reproducibility

Live calls are opt-in. The runner uses the existing OpenAI-compatible structured
provider, a content-addressed raw-output cache, a hard provider-call budget, aggregate
usage accounting, deterministic temperature zero, and no automatic retry. API keys
come only from `DOPPEL_API_KEY` and are absent from requests, caches, and reports.

Dry-run validation:

```powershell
.venv\Scripts\python.exe -m benchmarks.evidence_bundle_judgment `
  --partition dev --max-cases 12 --max-calls 0
```

The first live result must be preserved whether it passes or fails. A later blind
claim requires a newly authored, owner-disjoint corpus frozen before either profile is
run on it.
