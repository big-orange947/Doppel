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
