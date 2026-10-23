# Zero-model packing replay: more messages is not more annotated evidence

Starting commit31dc82a. No paid APIs, local model inference, embeddings, graph,
retrieval/reranking reruns, source writes, old-cache edits or reserved-history
execution. PostgreSQL connections enforce read-only mode. This is opened
development diagnosis, **not** new QA, independent validation or an AML score.

## Cohort and reconstruction

All50 cached contexts bind to the unchanged37/50 summary by case ID and exact
context hash. Saved-stage accounting covers43 answerable cases with76 annotated
turns;7 unanswerable cases are separate. A negative can still carry annotated
source turns: do not count those as positive retrieval success.

Only ordinals11–40 have a saved complete top20 source order available to this
replay. Their26 answerable questions have42 annotated turns;4 negatives remain
in message/byte totals but have no positive evidence denominator. The remaining
20 cases have saved candidate pools/final contexts but not the full rerank order
in the preparation artifacts; they are **unavailable for this paired replay**,
not guessed, reranked again or quietly folded into its denominator.

For each of30, the existing exact-scope source inventory matches its original
full corpus hash. Original event IDs, role/text/time bindings reconstruct all20
ordered items; the unchanged old ranked-fit function reproduces the original
packed objects exactly before any alternative runs. Frozen dataset, manifest,
preparation plans, contexts, payload hashes and negative labels are checked.

## Policies fixed without question/label access

The pure optional packer receives only source-bound ordered JSON objects. It
can factor identical scope/channel/nullable valid-time metadata into a shared
header, preserving per-source actor/role/authority/time/text/IDs/evidence links.
Decode must exactly reproduce original selected objects. Same20-item/24KB bounds;
no source truncation, session expansion, topic-specific branch or answer synthesis.

1. Baseline: unchanged whole-message ranked-fit.
2. Retain+fill: keep all baseline selections, then fill freed bytes in original
   rank order. If the envelope costs more than a plain list, use the plain list.
3. Repack: recompute selection from the same order using factored costs. This
   may fit an earlier long source and lose multiple later small sources.

The packer executes before annotations are used for scoring. Changing annotations
does not change chosen IDs (covered by tests). No parameters were retuned after
observing the losses below, and no question was substituted.

## Actual paired30 results (26 positive,4 negative)

| Policy | All messages | Serialized bytes summed | Positive annotated turns | Complete-positive questions | Gain/loss questions |
|---|---:|---:|---:|---:|---:|
|baseline|344|707690|36/42 (85.7%)|23/26|0/0|
|retain+fill|385|697326|36/42 (85.7%)|23/26|0/0|
|repack|367|703048|33/42 (78.6%)|21/26|0/2|

Retain+fill includes41 more intact messages, but **zero extra annotated turns**.
Unannotated messages are not automatically irrelevant; their answer usefulness
has not been tested. Repack includes23 more messages but loses3 annotations:
ordinal16 goes2→1 hits, ordinal19 goes3→1. These are evidence-delivery losses, not
a measured new QA regression. No Reader or judge was called.

Do **not** promote either policy as a quality improvement. The evidence does not
show a recall gain, and the alternate wire format could affect LLM comprehension.
No default API, Reader request, answer cache or old grade was changed. The pure
codec remains module-only opt-in, with explicit caveats rather than a new default.

## Frozen50 stage accounting, unchanged

| Stage | Positive annotated hits | Coverage |
|---|---:|---:|
|candidate80|72/76|94.7%|
|reranked top20|66/76|86.8%|
|packed24KB|60/76|78.9%|

Four annotated turns are absent before reranking,6 are lost in top20 selection,
and6 more in packing. Metadata factoring did not restore the losses in the
replayable30 subset. Do not extrapolate its result to the unavailable20, or assume
any of the13 QA errors would flip merely because an extra unannotated source fits.

## Preserved accounting mistake and correction

The first local artifact accidentally included4 annotated turns from negative
cases in positive denominators: frozen50 appeared76/80→70/80→64/80, and paired30
appeared40/46. It is preserved as `context-packing-replay-v1.json`, not overwritten.
The corrected v2 excludes negative labels only in scoring, giving the tables
above. V1/v2 IDs, item counts and byte counts match **for every policy and case**;
only accounting changed. A regression test covers annotated negative cases.

Artifacts under ignored `data/doppel/`:

- context-packing-replay-v1.json SHA-256:
  7c6e999ad334e062c79e2e2c5f6cc5a5ced889f69ec2c372ec44c3ea57cd9ac7.
- context-packing-replay-v2.json SHA-256:
  e35e82355a095b324bada3c3706bafbf72e8f5dea4dd8f0b7d45ed35152481af.
- Original50 summary SHA-256 remains:
  a5ecbc7c038a072eb69e73d5024fd53f3ec92800a5aec8c1bbeedd95c7ad8408.

Run with the existing local environment containing asyncpg:

```powershell
& D:\project\.doppel-eval-cu128\Scripts\python.exe -m benchmarks.public_memory_packing_replay `
  --read-only-postgres --output data/doppel/context-packing-replay-next.json
```

Existing output is refused. The report binds input/code hashes; current source
inventory mismatch fails rather than substituting current text into an old score.
Only selected opened30 histories are prepared for paired source reconstruction.
No model API key is required or read by the diagnostic.

## Checks and next decision

25 offline tests pass: exact codec roundtrip, actor/time/source preservation,
monotonic retain selection across budgets, strict bounds, cross-scope/duplicate/
NaN/coercion rejection, malformed-envelope rejection, annotation-independent
selection, exact frozen-context replay and negative-denominator accounting.
Ruff repository clean and new modules Pyright0 errors/warnings. Full regression:
**2253 passed,33 skipped,3 subtests**,217.22s; one existing optional Graphiti/
Pydantic deprecation warning. Pre-existing uv.lock remains unstaged/untouched.

The baseline remains37/50. Next useful comparison is candidate/ranking delivery,
not more metadata-format tuning: test a uniform wider source window against the
same top20/24KB output bounds, recording both recovered and displaced evidence
and real local inference cost before considering any paid answer rerun. Do not
make case16/19 rules, assume a wider window wins or revive eager paid graph builds.
