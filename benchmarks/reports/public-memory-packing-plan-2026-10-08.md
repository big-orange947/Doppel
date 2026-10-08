# Zero-provider paired rank-fit packing experiment

Freeze code and this plan before executing the local GPU/PG diagnostic. Do not
use a corrected QA score, prompt revision, case-specific rule or selected subset.
The same ten public development histories are already opened; reserved histories
remain unopened. This is an algorithm diagnostic, not independent evaluation.

## Source audit and choice of intervention

Read-only inspection of the exact dataset and preserved answers confirms:

- Plant acquisition at source session 1/turns 0 and 2 includes a peace lily and
  succulent acquired two weeks before May 20; session 16/turn 4 records a snake
  plant from the speaker's sister last month. Raw-only packs only one of the two
  annotated turns. Its Judge explanation about pruning a rose or a fern pest
  issue does not establish acquisition dates. Do not use that explanation as gold.
- Sneaker source session 2/turn 2 reports under-bed storage. Session 31/turn 0
  mixes future closet organization with an awkward shoe-rack phrase; turn 10
  says the speaker is looking forward to storing the shoes in a rack. This is
  unresolved source/reference ambiguity, not authorization to promote plans to
  completed current facts.
- Writing source session 7/turn 0 reports seventeen poems in two weeks; session
  39/turns 0 and 4 reports five short stories. The weekly challenge discussion
  supplies a named piece, but category overlap and the question's exact restart
  date need further semantic adjudication. Do not hardcode sum 23 or override
  all refusals. The previous same-model labels remain untouched.

These observations are bounded source inspection by this agent, not independent
adjudication. Dataset SHA-256 remains
`d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
The current packer has a simpler demonstrable engineering limitation: it breaks
at the first whole item exceeding the remaining serialized-byte budget, even if
later candidates would fit. This is the sole changed variable in this experiment.

## Frozen policies and constraints

- Baseline: unchanged rank-prefix packer, first twenty ranked items, stop on first
  overflow.
- Candidate: scan at most the same eighty ranked candidates, skip a whole item
  that does not fit, continue until twenty items are selected or the pool ends.
- One shared vector candidate pool and one shared full reranker ordering per
  question/channel. Same model artifacts, CUDA/max8192/batch1. Ranking eighty
  rather than returning its first twenty adds no scored candidate; the old
  reranker already scores all eighty.
- Both share final cap20 and serialized-context24,000-byte cap, including JSON
  metadata/multibyte overhead. No text truncation, snippets, query-conditioned
  packing, source expansion, actor filtering changes, gold or category input.
- Normal comparison and all production defaults remain unchanged. The candidate
  is explicitly experimental and gets distinct profile names.

Execute all ten questions x three channels x two packers = sixty rows. Reproduce
every original baseline row exactly after removing only experiment trace fields;
otherwise the paired comparison is invalid. All previously packed items must
remain byte-for-byte intact in the fit arm. Both arms revalidate packed Store
records and raw provenance after ranking; inventory/index checks remain active.
Report skipped rank positions, added item counts, bytes and annotated-turn coverage.
Coverage is source provenance, not retained facts or QA correctness. More context
may add distractors; do not infer an answer benefit without a later controlled
Reader run. No accuracy prediction or minimum improvement gate is set.

## Budget, preservation and binding

**Zero external provider calls/tokens**. No Reader, Judge, extraction, new ingestion,
Graphiti or production Planner executes. Remove the key in the child process to
demonstrate this. Do not start/reset Docker; ask the owner to open it if unavailable.
Keep the completed journal, parent report, dataset and manifest unchanged; no
index repair or Store writes. The shared Store initializer may issue idempotent
DDL, as in the original comparison.

Plan fingerprint:
`96086b1c4fe180e0a3207c84d5dbfc71eb841edcaa1e05c64c00e5750fd27cb7`.
Bound preflight `data/doppel/longmemeval-packing-preflight-v1.json` includes hashes
of the parent report, dataset, manifest, source journal, ingestion plan and source
files, with exact reranker artifact identity. Live requires this unchanged plan.
Preflight SHA-256:
`aef2800fc372fd19560dd2beb32c8f0880fcdd81203cf51f0a44f906d179fd8c`.
Parent report is `data/doppel/longmemeval-continuation-10-live-v1.json`, SHA-256
`6d2bb1f48ed03830c21706afbb8b80d580dfb8ec913e7d00ad903f321e975932`.
Fresh output prevents overwriting old artifacts. Source hashes are checked again
after the experiment. Preserve failed/invalid comparisons, never rename them into
successful results. User-owned `uv.lock` is not edited/staged.

```powershell
& D:/project/.doppel-eval-cu128/Scripts/python.exe -m benchmarks.public_memory_packing `
  --dataset data/public-benchmarks/longmemeval_s_cleaned.json `
  --manifest data/doppel/longmemeval-expansion-10-manifest-v1.json `
  --parent-report data/doppel/longmemeval-continuation-10-live-v1.json `
  --ingestion-dir data/doppel/public-memory-continuation-10-v1/ingestion `
  --output data/doppel/longmemeval-packing-live-v1.json `
  --frozen-plan data/doppel/longmemeval-packing-preflight-v1.json `
  --reranker-model-path D:/project/.doppel-eval-models/bge-reranker-v2-m3 `
  --embedding-cache-dir C:/Users/freeze/AppData/Local/Temp/fastembed_cache --live
```

After this run, publish all six profiles, including a null result if no annotated
coverage improves. Any Reader comparison needs its own later frozen binding and
must separate answer correctness from justified refusal; do not revive the
calibration loop or retroactively relabel prior outputs.
