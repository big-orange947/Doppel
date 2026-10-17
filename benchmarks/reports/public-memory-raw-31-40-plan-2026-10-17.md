# Frozen next-ten continuation: retrieval and packing together

Run the exact original prospective diagnostic ordinals31–40, excluding opened
first30 and all reserved groups. Ten complete LongMemEval-S histories /5103 raw
messages. Public strata: knowledge-update2, multi-session2, assistant2, user1,
preference1, temporal1, no-answer1. No resampling or question-specific rules.
These new evaluation histories were not used to develop the packing comparison;
they remain public benchmark material, not independent/model-unseen blind data.

Three arms only: vector-reranked, BM25/vector, BM25/vector-reranked. Use unchanged
production attributed raw retrieval and RRF60/equal weights/no fallback. Each
receives at most80 candidates, returns20. Both existing prefix and skip-to-fit
packers consume those same20, at most20 whole items /24,000 UTF-8 JSON bytes.
No snippets/metadata rewritten, larger window, extra retrieval or gold-dependent
selection. Preserve source roles, authority, original dates and exact scope.
Score labels only after retrieval/packing. Separate predeclared unanswerable
questions from answer-support recall, retain their execution rows.

Local fastembed BAAI/bge-small-zh-v1.5 /0.8.0 /512 dimensions; strict local CUDA
bge-reranker-v2-m3 max length8192 /batch1. Same artifact as prior experiments.
No paid LLM, extraction, graph, Planner, Reader or judge. No stable idle-GPU latency
claim. New namespace `longmemeval-nograph-retrieval-31-40-v1`, dedicated schema
`raw_next_c3e337f1cbe8`; no existing data reset/deletion or schema reuse. Ingestion
is raw-only. Revalidate Store/source contents and final packed source identities.
Each complete history gets an exclusive receipt; on failure stop and retain all
attempt/data records, no automatic retry or silent second invocation.

Preflight SHA-256 (`longmemeval-raw-31-40-preflight-v1.json`):
`ff26510896b27af26e5702a154818302c6c1db31eff79225850342c5c4419684`.
Plan fingerprint:
`93331b3a68ce2f9d7900e458b9342e6a9c4246eada2ef45c8a601b87d68b9c5a`.
Freeze code/plan before execution. Eight new tests plus existing prefix/fit tests:
29 passed, Ruff passes. One incorrect test-only import was fixed before freezing;
no live evaluation was attempted with that test collection error.

Report all three profiles' candidate/top5/top20 and packed coverage, full-question
coverage, role/provenance checks and accounting. Do not tune on outcomes. This
does not measure QA correctness, negative-case abstention, graph value, extracted
memory intelligence, official LongMemEval/AML performance or release acceptance.

## Entry-point name correction during execution

The new wrapper initially used the already-tracked name
`public_memory_continuation.py`, temporarily replacing a historical wrapper in
commit18bbb1b. The old wrapper and its tests were restored exactly from a87187d;
the new wrapper/test now use `public_memory_raw_continuation.py` and
`test_public_memory_raw_continuation.py`. No database or historical receipt was
changed by this correction. The running Python process keeps its originally
loaded code; there is no repeat evaluation, model change or budget restart.

The moved wrapper's exact SHA-256 still matches the frozen preflight:
`5db1ed4fe853d57148acd09af1ace0874dcb1466fb82117816362cda81abb232`.
The recorded execution commit18bbb1b preserves that code at its original path;
new invocations should use the separate raw-continuation entry point and a new
explicit plan/output, never silently retry the retained attempt.
