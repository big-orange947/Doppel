# Fixed-budget whole-item packing comparison

## Frozen before execution

Use all160 saved rows from original ordinals11–30, twenty full public S histories.
Compare the unchanged prefix baseline with the existing `pack_ranked_fit`, using
only the exact saved top20 items, not the broader80-candidate pool. Both policies
use the same24,000 UTF-8 JSON-byte budget, at most20 whole items, identical source
metadata and ordering. No text truncation, summarization, new retrieval, model,
graph, neighbourhood expansion, gold-dependent selection or changed defaults.

The baseline must reproduce every previous row exactly, not just its aggregate
score. Read-only Store/source inventory must match the preceding audit before
execution and remain unchanged afterwards. Skip-to-fit must preserve every prefix
item byte for byte and keep selected ranks ascending. Individually oversized
evidence may still be lost; no gain is presumed. Report all eight profiles, with
seventeen answerable questions /27 annotated turns; three negative questions are
separate. This is an opened-data diagnostic, not independent QA/AML validation.

Preflight `longmemeval-raw-packing-fit-11-30-preflight-v1.json` SHA-256:
`b5a345b73da5ae3b731f39ce77f306ea0d65ee2219333512c172002a3abcf984`.
Plan fingerprint:
`ef70909053d9cdfa48f269e05d07e417a5285278aca9c76dd750bd0bc0cd122c`.
Targeted comparison/prefix/packing tests:36 passed, including seven new tests.
Ruff passes. No paid-provider calls are permitted. Preserve `uv.lock` and all
existing receipts. Freeze this code/plan before executing the comparison.

## Completed result

Code/plan frozen at `f9a8d3b` before execution. All160 prefix rows reproduce the
preceding audit exactly, including context bytes/hashes. Both policies then
consume the same saved top20 source-bound items. All9883 raw records match the
preceding inventory hashes and remain unchanged after comparison. No paid calls,
GPU/model execution, graph writes or production-default change occurred.

| Profile | Prefix hits /27 | Skip-to-fit hits /27 | All required, prefix → fit /17 |
| --- | ---: | ---: | ---: |
| Legacy whole-query substring | 0 | 0 | 0 → 0 |
| Local vector | 21 | 21 | 12 → 12 |
| Legacy substring + vector | 21 | 21 | 12 → 12 |
| BM25 | 22 | 23 | 14 → 14 |
| BM25 + vector | 25 | 25 | 15 → 15 |
| Local vector + reranker | 25 | 25 | 15 → 15 |
| BM25 + reranker | 22 | 25 | 13 → 15 |
| BM25 + vector + reranker | 23 | **26 (96.3%)** | 14 → **16** |

All profiles preserve every prefix item unchanged and in order. This structural
property prevents loss of existing labelled evidence, but does not prove that
adding more text improves Reader accuracy, precision, distraction or abstention.
The three negative questions remain separate; there is no new answer-stage score.

Hybrid-reranked recovers the one lost turn in `gpt4_e414231e` and both lost turns
in `5a7937c8`. It still misses session40/turn2 in `1d4e3b97`: the greedy policy
retains the original eight-item prefix and admits rank10, then lacks room for
the excluded evidence. Skip-to-fit does not evict higher-ranked items to optimize
global evidence coverage. No rule was added for this opened failure.

Hybrid-reranked packs217 items over20 questions (10.85 average), vs192 (9.6) for
prefix; no bigger byte/item budget or80-candidate expansion was used. The small
sample does not establish a universally best retrieval/packing composition.

### Decision and immediate next step

Keep the generic existing skip-to-fit policy as an explicit experimental option,
not a silently changed default. Stop tuning these opened cases. Next run one
bounded untouched continuation with both policies and only the useful non-graph
retrieval arms; then, if evidence coverage holds, a small paid QA comparison can
test whether the additional context helps answers. Do not launch another judge
calibration campaign or full-history graph build for this issue.

Verification:36 targeted comparison/prefix/packing tests passed, including seven
new tests; repository Ruff and new-file formatting pass. The previous full-suite
receipt remains1,890 passed/33 skipped/three subtests; **the full suite was not
rerun for this benchmark-only addition**. One existing optional Graphiti/Pydantic
deprecation warning remains. No independent replay of this fit report is claimed.

Local ignored output `longmemeval-raw-packing-fit-11-30-live-v1.json` SHA-256:
`259f5ccf23be353f4701ac66936e4a94f865665e33317a018561c0a334594590`.
