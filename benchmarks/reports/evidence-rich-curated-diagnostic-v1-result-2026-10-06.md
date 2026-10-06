# Evidence-rich curated diagnostic: completed V7/V8 comparison

Date: 2026-10-06. This is an **opened, assistant-curated diagnostic**, not an
independently accepted blind result or a release-readiness certificate.
The [preregistered protocol and amendments](evidence-rich-curated-diagnostic-v1-plan-2026-10-06.md)
retain the full attempted-run history. No production retrieval code was changed.

## Population and unchanged runtime

208 query slots across 24 owners; 4,608 memories, 456 entities and 240 graph edges.
All background records remain; only the preregistered 32 questions are excluded.
There are 132 distinct question strings, not 208 independently worded questions.
184 questions have required answers with 205 required evidence records; 24 are
related-context questions with no buyer answer. Queries per owner range from 7 to 9.

| Partition label inherited from parent | Query slots |
| --- | ---: |
| dev | 52 |
| sealed | 105 |
| adversarial | 51 |

The inherited `sealed` name does not make these manually curated/opened queries a
new independent sealed test. Every question is evaluated with oracle intent, time,
subject and entity anchor. V7/V8 do not receive oracle relation routes. Extraction,
natural-language Planner accuracy, final answers and whole-history counts are not
measured. The full parent corpus remains unaccepted and `publication_ready=false`.

Local PostgreSQL/pgvector and Neo4j/Graphiti are live. Cached BGE-small-zh-v1.5
embeddings have 512 dimensions. Cached BGE-reranker-v2-m3 uses CUDA, sigmoid logits,
batch 16 and a 64-candidate window. All existing runner profiles executed; the
predeclared V7/V8 comparison is primary. No paid provider/API-key path was used.

## Observed results, with denominators

| Profile | Evidence recall @5 | Evidence recall @10 | Complete answers @10 | MRR | Related-context recall @10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| V7 semantic paths + memory reranking | 204/205 (99.51%) | 204/205 (99.51%) | 183/184 (99.46%) | 1.000 | 34/48 (70.83%) |
| V8 semantic path-family completion + memory reranking | 205/205 (100%) | 205/205 (100%) | 184/184 (100%) | 1.000 | 34/48 (70.83%) |

V8 also has complete evidence @5 = 184/184. Every answerable category and partition
has complete evidence @10 = 1.0 on this selection. Recall @1 is 184/205 = 89.76%:
MRR measures the first required record, not completion of both records in a two-hop
answer. MRR = 1.0 therefore does not mean every required record is ranked first.

V7's sole incomplete case is `case-blind-23-06`, missing
`memory-blind-23-010`; V8 places that second-hop evidence at rank 2. Candidate-window
required recall is 204/205 for both. V8's completion stage closes this specific
final-evidence gap without changing the window's measured recall. This is a small
one-record benefit, not proof that V8 is universally superior.

Auxiliary unchanged lexical+vector baseline has recall @5 = 0.941463, recall @10 =
0.975610, complete @10 = 0.972826 and MRR = 0.996377. The oracle-path-plus-reranking
control also reaches complete required evidence on this corpus. An isolated graph
path control covers relation cases only; its aggregate score is not a fair full
personal-memory-system comparison.

## Related-context metric requires semantic label review

The initial progress message described 70.8% as 17/24 questions. That denominator
was wrong and is corrected here: the metric is **34/48 related records**. Each
question has two related labels. All 24 directly object-related custody records
appear at rank 1. The second, broader background slot appears in the top 10 for
10/24 questions. Both slots appear for 10/24 questions. Candidate-window related
recall is 37/48 (77.08%). These are post-run diagnostic decompositions, not new gates.

All 14 missing top-10 related records are second background slots. One is rank 11;
the other 13 are outside the final top 20. Some describe generic document-handling,
pet-care or household habits rather than the object or purchaser in the question.
It is not established that all such records should be retrieved as useful context.
This exposes further semantic-gold uncertainty, not fourteen proved product defects.

The original 34/48 metric is retained unchanged. No labels are removed, no queries
are excluded after scores, and no broad-background retrieval rule is introduced to
make it look perfect. The next task is to distinguish directly useful related
evidence from generic personal background in a separately reviewed contract. If
that contract changes, this result remains an opened diagnostic under its old labels.

For related-only cases, the legacy raw summary's required-recall/complete fields
have empty denominators and display neutral defaults. They are NOT 100% answer
accuracy and are not presented as such here. Buyer-answer quality is unassessed.
The absent count population is correctly reported as null / not measured.

## Safety, execution and cleanup

For both primary profiles: zero hard-forbidden hits, scope leaks, subject violations,
ineligible records, temporal violations and orphan provenance. Store revalidation,
path-budget omissions and membership violations are zero. Nonempty retrieval is
actually exercised: average final candidates = 19.677885, maximum = 20.

Memory reranking: 208 completed. Path reranking: 69 completed, 139 not run; no failed
or fallback status. Both primary assemblies retain 180 paths and reject 78 base
filter mismatches as normal eligibility filtering, not Store-revalidation failures.
197 queries use bounded truncation. No selected path is omitted from its budget.

Neo4j's run-specific groups were removed and verified. The dedicated PostgreSQL
benchmark schema was reset; a separate read-only check found zero public tables.
No unrelated graph nodes, Docker volumes or user database were removed. No cleanup
errors. External HTTP = 0, paid LLM calls = 0, provider tokens = 0, persisted secrets
= false.

Observed V7 p50/p95 = 456.247/563.374 ms; V8 = 455.029/569.418 ms. These are one-run
stage-composed latency observations, not isolated repeated warm-latency results.
Offline regression work ran concurrently. The user-deferred idle/contended GPU
latency experiment remains deferred. Average returned content is about 682 Chinese
characters before prompt wrappers; this is not a model-token measurement.

The diagnostic safety gate passes. The legacy full-corpus V9 gate is not used to
approve this selection; missing count/category checks still prevent full acceptance.

## Audit trail and limits

Three attempts are retained, not collapsed into a best-run result:

1. `9ea2e3b`: oracle control rejects new declared relation types; interrupted.
2. `901cb0c`: completed but invalid fixtures classify all owners as contacts, empty
   results; original report and vacuous safety outcome retained.
3. `42b1b15993775437edb56f2d2381aaabd03f41ad`: explicit host identity mapping and
   nonvacuity guard; valid diagnostic run above. No production strategy changes.

The two corrections are generic benchmark adapter fixes, not ID/query-specific
exceptions, changed private labels or lowered isolation requirements. All source
hashes, corpus bytes, membership and algorithm code bindings were checked unchanged
again. The original 23-issue rejected review remains immutable and rejected.

Local valid report: `data/doppel/evidence-rich-curated-diagnostic-v1-live-v3.json`.
SHA-256: `66cf6e1c24f1b6f67c6a0693c92eb01f3c78d22770aac25b0949dee5eb4c6bc0`.
Selection-v3: `4f4fa03488874a4221a9847a269ff37713b69def38f09c5de78e47fe4ab2e458`.
Corpus: `0ef79243695aafe2d9319d94846c35a5cfe08733d526bed7b5d8af1ce0244d26`.
The raw report records pre-existing dirty `uv.lock` and an added offline nonvacuity
test; neither alters the frozen runtime code. Report files themselves are ignored.

Final offline verification: **952 passed, 33 skipped, three subtests passed**; one
existing Graphiti deprecation warning. Ruff and full Pyright pass. The skipped
tests are not claimed as verified. `uv.lock` was not edited or staged.

## Next bounded step

Keep the production algorithm unchanged. Review related-evidence semantics and the
excluded count population, then prepare a separate, explicit semantic acceptance
decision. Known missing-value / question-given-hop cases need text/gold-contract
repair before full acceptance. Do not recycle this opened subset as a fresh blind
test, promise a general 100% recall rate, or infer natural-agent/real-user quality.
