# Fresh prospective cohort: first high-config/raw question pair

**The first selected question completed in both frozen profiles and was judged
correct in both.** This is one public question, not a fifty-case accuracy, a graph
uplift result, an independent blind test, an official LongMemEval score or AML.
Three histories are ingested; only **one of fifty** questions is answered/scored.
No core algorithm, model, prompt or packing policy was changed after the answers.

## Source, graph and schema

The graph and query budgets were committed before their paid stages. The source
stage used withheld question/gold projection, default analyzer V8 and deterministic
consolidator V5. Scope ordinal 1 / case `15745da0` follows frozen source order.

All 216 eligible personal memories were production-Graphiti indexed and checked
against the authoritative Store. The rich-edge snapshot has 250 edges / 153
distinct names. Source-only schema authoring preserved all names in seven calls.
Complete projections are **not** semantic-extraction completeness: one captured
missing-target warning remains. All selected-scope source/Store/vector snapshots
and other fresh-cohort graph scopes were unchanged by graph/schema preparation.

## First paired outcome

The question asks the duration of the user's vintage-camera collecting. The
reference is three months. Both answers report the source's three-month duration,
then qualify an extrapolation from the May 21 statement to the May 30 question
reference date. Their assumptions are model reasoning, not proven by the
structural derived-block validator. The same-model task and citation judges
accepted the core answer; no independent human/second-model adjudication occurred.

| Metric | Full high-config | Raw vector + reranker |
| --- | ---: | ---: |
| Completed provisional task grade | Correct | Correct |
| Annotated turn hit / available | 1 / 1 | 1 / 1 |
| Annotated session hit / available | 1 / 1 | 1 / 1 |
| Citation legality | Valid, two IDs | Valid, one ID |
| Provisional citation support | Supported | Supported |
| Judge quotes anchored to cited source | Yes | Yes |
| Citation contradiction reported | No | No |
| Final whole context items | 17 | 11 |
| Context UTF-8 bytes | 23,863 | 23,367 |
| Model attempts | 5 | 3 |
| Reported model tokens | 38,919 | 13,332 |

Both answered in **Chinese despite the English question**. That is an observable
Reader policy defect, not a reason to rewrite the frozen answers, judges, prompt
or cohort. Answer-language compliance is distinct from semantic task correctness.

Full ran the natural V7 planner, current PG vectors, local CUDA BGE reranker,
typed graph retrieval, one graph path search and one exploration search; twenty
path candidates were promoted into evidence-rich assembly. It did not silently
degrade into the raw profile. Source resolution failures were zero. Raw/source
backing remained separate from owner facts. The raw comparator also retrieved the
answer, so this case demonstrates **no marginal answer-accuracy gain from graph**.

## Execution status is not a clean acceptance

The high-config execution assessment is `review_required`, not accepted: there
are zero classified execution failures but two unclassified governance warnings.
They identify existing unresolved conflicts in `plan.amp-purchase` and
`preference.disliked-shows`, not the camera duration. A third informational notice
correctly declares bounded index candidates rather than exhaustive scope coverage.
The warning classifier and conflict handling are unchanged; these warnings are
retained for review, not erased to manufacture a passing hard gate.

Thus both tasks are provisionally correct and source-grounded, while language
compliance and execution-warning qualification remain imperfect. Neither row is
an official/publication acceptance. Final selected-scope corpus/vector/graph/
source-journal hashes are unchanged; no QA record or index writes occurred.

## Reproducibility and accounting

An independent process with `DEEPSEEK_API_KEY` removed replayed immutable
retrieval and model checkpoints. Both answers, context lists, task judgments and
citation judgments exactly match live. Six Reader/judge provider-cache hits,
zero misses; the planner was not re-executed because retrieval was checkpointed.
The durable provider-call inventory and the two original live profile receipts
are unchanged: **zero new attempts**. This is not a repeated GPU retrieval or a
latency experiment.

The V1 query adapter uses exclusive output receipts and cannot overwrite those
during replay. A separate zero-paid replay observer compares only those existing
receipt writes, ignoring per-invocation usage/execution labels; it does not replace
them. The frozen V1 query/graph sources remain byte-identical. Four offline tests
reject changed answers, failures and unexpected writes. No extra live control or
prompt tuning was introduced.

Paid usage for this first scope: 49 source + 920 graph + 7 schema + 8 paired QA =
**984 attempts / 4,099,315 reported tokens**, all successful with complete usage.
The additional two histories used 100 source attempts / 485,905 tokens. Across
the new cohort so far: **1,084 attempts / 4,585,220 tokens**, no retry or missing
usage. Source, graph, schema and QA retain separate durable budget identities.
Observed balance after this run was 1.09 CNY; it is not exclusive settled billing.

Local ignored receipt SHA-256:

- Graph: `78fd8372ba412fb9cb960e4254740152d0171bf5b5405c263c36b6e62d80ed94`.
- Schema: `603a58690740d551e07832649b1570b19772037b000cc619cacc47f860a439dc`.
- Paired QA live: `1597b6742a9bbfb672dd810a3af427a92c64001aee768b18bcf332e2e22871ce`.
- Paired QA empty-key replay:
  `28332dda8673a4629f4fa6e10719dcb0963573d4c7ac322d544261d44f0494da`.

Final verification: **1,840 passed / 33 skipped / three subtests passed** in the
full local test suite (1,812 baseline + 28 new offline adapter tests). Ruff passes
repository-wide; eight new source/test files pass formatting; Pyright reports
zero errors for the four new runtime adapters. A pre-existing Graphiti Pydantic
deprecation warning remains. `uv.lock` stays in its pre-existing dirty state and
is not staged. All schema/query sources were frozen before their paid stages.

## Next fixed steps

Use the already completed second and third source histories; freeze each whole
eligible scope's graph inventory and budgets, then run the same two profiles in
their fixed alternating order. Do not change policy based on this one outcome.
Report the first ten completed case pairs with both selected and completed/scored
denominators. Keep prior opened vector-only results separate. Avoid unbounded
authoring with near-empty provider balance; preserve any provider/budget failure.
