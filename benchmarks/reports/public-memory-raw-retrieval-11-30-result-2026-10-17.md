# Twenty new full histories: raw evidence retrieval without graph or LLM calls

The frozen expansion at original prospective ordinals 11–30 completed: **20
LongMemEval-S histories, 9,883 raw messages, eight fixed profiles, 160 rows**.
All source histories are complete S inputs, not evidence-only oracle inputs.
No extraction, Graphiti, Planner, Reader or judge ran. Paid LLM calls, provider
tokens and graph calls are all **zero**; local embedding/reranking still consumes
hardware and time. This is evidence retrieval, not answer accuracy.

The main comparison finds 25/27 answer-support turns with vector plus reranking,
and 27/27 with BM25 plus vector plus reranking, in the first 20 raw snippets.
The latter is not uniformly better: at five snippets it covers 18/27 rather than
20/27. BM25-only plus reranking ties the hybrid on these aggregate metrics.
No production default, core algorithm, prompt or model changed after results.

## Population and denominator

Selection is the exact next twenty diagnostic histories from the existing frozen
fifty-case manifest, excluding the previous ten, with no outcome-based replacement
or access to reserved histories. Public strata: assistant 3, multi-session 3,
preference 3, unanswerable 3, user fact 3, temporal 3, knowledge update 2.

**Primary answer-support recall uses 17 answerable questions / 27 annotated turns
/ 26 annotated sessions.** The three predeclared unanswerable questions still
have related-history `has_answer` annotations in the source. Those are not proof
that the modified unanswerable question has an answer. The existing generic
scorer preserves these annotations in the raw report (30 total annotated turns).
This document uniformly separates rows using their already-frozen
`at_20.abstention_label`; no scorer, annotation, raw artifact or ranking is edited.

The negative cases are `gpt4_c27434e8_abs`, `6456829e_abs` and
`gpt4_70e84552_abs`, each with one related-history annotation. All three remain
in the 160 execution rows and integrity checks, but not the answerable recall
denominator. Without an answer stage, neither correct abstention nor false-answer
rate is measured. Finding a related snippet must not be scored as answering them.

## Results on the 17 answerable questions

Candidate recall is measured in the final candidate window of at most 80;
top-five/top-twenty scores are before any Reader byte-budget packing.
All counts below concern the same 27 annotated turns. The last column counts
questions for which all required annotated turns occur in the first twenty.

| Fixed profile | Candidate hits /27 | Top 5 /27 | Top 20 /27 | All required @20 /17 |
| --- | ---: | ---: | ---: | ---: |
| Legacy Store whole-query substring | 0 | 0 | 0 | 0 |
| Local vector | 25 | 15 (55.6%) | 21 (77.8%) | 12 |
| Legacy substring + vector | 25 | 15 (55.6%) | 21 (77.8%) | 12 |
| BM25 | 27 | 19 (70.4%) | 25 (92.6%) | 15 |
| BM25 + vector | 27 | 20 (74.1%) | 25 (92.6%) | 15 |
| Local vector + reranker | 25 | 20 (74.1%) | 25 (92.6%) | 15 |
| BM25 + reranker | 27 | 18 (66.7%) | 27 (100%) | 17 |
| BM25 + vector + reranker | 27 | 18 (66.7%) | 27 (100%) | 17 |

Session coverage @20 is 24/26 for vector without reranking (including the legacy
hybrid), 0/26 for legacy substring, and 26/26 for every other profile.
The legacy Store search is a full-query substring operation, not BM25 token-based
retrieval; its zero hits must not be generalized to lexical retrieval as a whole.

### What the comparison establishes

- Candidate coverage matters: vector misses two labelled turns before reranking.
  In `00ca467f` it brings one of two required turns into the candidate window;
  in `75832dbd` it brings none of the one required turn. A reranker cannot recover
  a record absent from its input. BM25 brings both missing turns into the window.
- Ordering also matters: vector reranking improves top-twenty coverage from
  21 to 25 turns without changing its candidate coverage. BM25/vector reranking
  improves 25 to 27. These are distinct failure stages, not Reader failures.
- Top-five ordering is unresolved: hybrid reranking reaches 27/27 at twenty but
  18/27 at five, below vector reranking's 20/27. Wider coverage is not necessarily
  better under a short context budget. No post-result weight or prompt tuning ran.
- BM25-only reranking matches hybrid reranking on the reported aggregate scores.
  Incremental vector value is not demonstrated in this sample. This does not
  justify deleting vector retrieval for other semantic tasks or datasets.

## Execution, isolation and accounting

Reuse unchanged `public_context_baseline.run_baseline`, `RawHistoryHost`,
`AttributedContextRetriever`, production BM25/RRF and vector retrieval. Local
embedding is fastembed 0.8.0 / `BAAI/bge-small-zh-v1.5` / 512 dimensions.
Strict local CUDA `bge-reranker-v2-m3` uses maximum length 8192, batch size 1.
Candidate/output limits are 80/20; the auxiliary legacy Store hybrid retains
its declared 320-per-source stage before the final window. BM25 remains a bounded
scoped-scan reference implementation, not a persistent corpus-wide index.

The dedicated PostgreSQL schema is `raw_evidence_df11c519b425`, namespace
`longmemeval-nograph-retrieval-11-30-v1`. No previous schema, graph, journal or
cache is reset or deleted. Conventional provider-key variables are removed from
the child process. Four five-history blocks contain 2,459 / 2,405 / 2,524 / 2,495
messages. Dedicated raw Store/vector data are retained for reproducibility.

All 160 rows completed. Candidate revalidation performs **11,200** authoritative
Store/source checks, followed by **2,800** final Store checks; no rejections or
scope/provenance/runtime failures were recorded. User and historical-assistant
roles remain attributed. These normal-run checks are not an adversarial security
certification. All 60 rerank operations completed, scoring 4,800 pairs with no
reported input truncations across the four blocks.

No exact cache-only replay was run for this experiment. The earlier five-question
QA replay belongs to a different protocol. Recorded latency is not an idle-GPU
or repeated warm-latency benchmark; that measurement remains deferred.

## Limits and next decision

Twenty public questions are a useful expansion, not independent blind validation,
complete LongMemEval-500, an AML score or publication/release acceptance. Histories
may share filler material, and public benchmark exposure is possible. Eight
profiles are repeated measurements on twenty questions, not 160 independent tasks.
Raw-message annotations need not exhaust all sufficient evidence.

The top-twenty result is **not** a 24,000-byte packed-context score or a 100%
answer-accuracy claim. No derived memory quality, graph value, temporal Planner,
personalization policy, answer generation or negative-case abstention is tested.
The next useful bounded step is to measure whether labelled evidence survives
the unchanged practical context-packing budget, before spending on more QA or
whole-history graph construction. Preserve the frozen result rather than tuning
on these opened cases and calling the new outcome independent.

## Verification and artifact bindings

Targeted wrapper/raw-host/context-guard tests: **14 passed**, including seven new
wrapper tests. Full suite: **1,876 passed, 33 skipped, three subtests passed**.
Ruff repository checks and formatting of the new Python files pass. One existing
Graphiti/Pydantic deprecation warning remains. `uv.lock` is untouched and unstaged.

Implementation/run commit: `a11dabb`. Frozen plan:
[twenty-history plan](public-memory-raw-retrieval-11-30-plan-2026-10-17.md).
Local artifacts remain in the ignored data directory, not committed to the repo.

| Binding | SHA-256 / fingerprint |
| --- | --- |
| Source `longmemeval_s_cleaned.json` | `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442` |
| Preflight `longmemeval-raw-retrieval-11-30-preflight-v1.json` | `e5b897414b3455464c6229cecd5abb7eb10f25b5be1922a43b1de5c9fd012dab` |
| Plan fingerprint | `3a05d32254ba6dcc339e7e0127b09acdd1d884c51d5c5b9aa7dbc520c932d405` |
| Child manifest fingerprint | `df11c519b425307d81ede04aa430f4ebc95e29d546b6d1a2c50299a01fcc5f11` |
| Wrapper bytes | `26bf9a9e8fb10c73389ad47649207a835176be1ff34eab89fac00fe03a925440` |
| Reranker artifact | `d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286` |
| Final `longmemeval-raw-retrieval-11-30-live-v1.json` | `10c09984b30b9a89d657b8929bc9f7e2374849338d2c0767a2195b4009db7f4f` |

Four block receipts in `data/doppel/public-memory-raw-retrieval-11-30-v1/`:

- `block-01.json`: `9a71bc86791606e93343107e4556026d03380b6d25994846a1e93185c3592d9b`
- `block-02.json`: `50810f1816bd1c79a5b80fd5e1b7af906cad9b30a0e414cfdbf7486ccc7194df`
- `block-03.json`: `d9f1e7af80e8b8e41eb5dedef1b56ec92c1adb060e44c6815a865dcb9b1cb328`
- `block-04.json`: `59f194bbd6d23409a451c4ee21e794ab1ea018c67cf9551b435513dccfff5ce4`
