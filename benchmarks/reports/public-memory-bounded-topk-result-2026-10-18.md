# Bounded selection: evidence improved, answer accuracy unchanged

Date:2026-10-18. Frozen implementation/plan commit:`f21ebce`. This is a two-opened-
case development diagnostic, not independent validation, a three-case/full500
score, AML result or a production-default promotion.

## Primary result (unchanged Reader and provisional task judge)

| Case | Immutable content-only passage baseline | Up-to20 LLM selection |
| --- | --- | --- |
| `gpt4_ec93e27f` transport | correct | correct |
| `gpt4_2f8be40d` wedding count | incorrect refusal | incorrect refusal |
| Total | **1/2** | **1/2** |

All8 planned calls completed, no retries/runtime failures. Old contexts/Reader
requests/grades were bound exactly and reused without new baseline calls. The
first case from the original three (`e9327a54`) was not evaluated under this
bounded contract: do not combine its old grade into a supposed new3-case score.

The earlier exact-k smoke remains failed:8 authorized IDs instead of20,
1 call/19,378 tokens, no QA. The prior full-permutation smoke also remains failed:
79 instead of80,1 call/19,290 tokens. Their caches were not imported, truncated,
filled or rescored. Upper-bound selection is a new contract and experiment.

## What changed in the actual evidence

Both source selections chose20 of the same80 candidates, leaving60 explicitly
unranked. Fragment pools were31 and25, neither budget-exhausted; both selected20
fragments. Fixed24KB packing retained19 each, dropping rank20 in each row.

| Case | Old packed owner / assistant items | New owner / assistant | New bytes |
| --- | ---: | ---: | ---: |
| transport | 4 /11 | 12 /7 | 23,870 |
| wedding | 0 /13 | 16 /3 | 22,768 |

Role counts alone are **not a quality score**; no role quota was used. Source
inspection confirms a substantive difference beyond role mix: the wedding
context now retains three complete owner statements describing the reference
events, with `human_self` authority and source hash/offset metadata:

- Cousin: `mem-d212da7da2c84405adaef331e2a7b072`, span `[0,301)`, says
  “my cousin's wedding at a vineyard in August”.
- Roommate: `mem-ccbec41a9b7d4a029cfd07c24413ed07`, span `[0,561)`, says
  “I just got back from my college roommate's wedding”; the same original names
  Emily and Sarah.
- Friend: `mem-0e25f69f33314717be696e6e7ae518ff`, span `[0,393)`, says
  “I just got back from a friend's wedding last weekend”; it names Jen and Tom.

These spans each cover their full original source, not a source-ID proxy for
semantic support. All three survive fragment selection **and packing**; thus the
old loss of these owner statements is no longer the explanation for this row.
This is an observed development-case coverage improvement, not a general recall
percentage or proof that the supplied context uniquely determines the gold count.

## Why the count answer still fails

The Reader lists the cousin, roommate and friend, but also lists a sister's
wedding. That additional item really is an owner statement in supplied context
(`mem-693e318b93cb45c4bb4b2a5052bec430`), not an assistant fact promoted into owner
authority or an invented Reader event. Other nearby source text mentions a cousin
last month and refers to Emily as a cousin rather than roommate. These are real
ambiguities in the returned history; do not silently remove or merge them to fit3.

The Reader then refuses an exact yearly count because effective dates and history
completeness are uncertain. Source observation timestamps **are present**, as are
relative expressions such as August, recently and last weekend; observation time
is not automatically the effective date. The claim of insufficient exact dates
must not be confused with lost timestamp metadata. We have not independently
proved the full context unambiguously entails exactly the reference count.

The primary provisional judge marks the refusal incorrect because it does not
convey the reference answer3. Keep that grade. `abstained=false` nevertheless
accompanies this refusal, a known semantic consistency problem that the structural
checker does not verify. Both English questions received Chinese answers. No
Reader/judge prompt, labels, temporal policy or flag derivation was changed.

Transport uses owner statements about a March3 train trip and a February27 bus
trip, concludes train within supplied records, and adds a completeness caveat.
It is marked correct under the unchanged provisional judge. Previous experiments
already showed hedging sensitivity; these two labels do not establish stable
answer-model or judge performance.

## Integrity and accounting

Both80-candidate pools reproduce prior hashes. Both original scoped Store
inventories reproduce before and after execution. Source prevalidation160 records;
post-selection Store reloads20 per case; passage final-source checks17 and20;
all20 selected fragments per case also resolve to original text/hash/offsets.
Source/passage rejection maps are empty. This demonstrates checks on these paths,
not an adversarial isolation/privacy benchmark.

All12 cited IDs are legal and unique within their respective answers (3 and9).
Structural validity is **not** semantic faithfulness, count correctness, temporal
entailment or consistency of `abstained`. Neither response contained structured
`derived` arithmetic. The source/fragment metadata and agent-output authority
remain unchanged; no new personal facts were written.

| Stage | New calls | Input tokens | Output tokens | Total |
| --- | ---: | ---: | ---: | ---: |
| Selection | 4 | 68,601 | 424 | 69,025 |
| Reader | 2 | 17,572 | 1,267 | 18,839 |
| Provisional judge | 2 | 1,450 | 88 | 1,538 |
| Bounded experiment | **8** | **87,623** | **1,779** | **89,402** |

Usage complete8/8; no retries/missing usage. This turn including failed exact-k:
**9 new calls/108,780 tokens**. Including the previous full-permutation failure:
10 historical+new calls/128,070 tokens. No monetary billing estimate is asserted.
No graph authoring, schema/source/vector writes, database resets, reserved/new-case
access, production-default changes, or changes/staging of the user's `uv.lock`.
The API key remains environment-only.

## Artifacts and next decision

Plan fingerprint:
`f083ccf0b3c34108e4a757418962c8db20d4e9f48cccf3f6be5e73105ab5477d`.
Local ignored files:

- Preflight `data/doppel/bounded-topk-diagnostic-preflight-v1.json`, SHA-256
  `7875893aab58337774cd4df6db1e10adb94bb8fa65385ba3e627ced11379d77a`.
- Live `data/doppel/bounded-topk-diagnostic-live-v1.json`, SHA-256
  `0b47e95b7c18afd217221cbb6241a9dc275c7fc7e33f5b1599bde856085216b3`.
- `data/doppel/bounded-topk-diagnostic-20261018-v1`: provider caches, SQLite ledger,
  four pre-await selection receipts, two context and two answer checkpoints.

Final full regression: **2017 passed /33 skipped /three subtests passed** in235.52s.
Targeted selection/reranking suite62 passed. Repository Ruff and changed-file
format checks pass; Pyright selector/driver implementations have zero errors.
One pre-existing Graphiti/Pydantic deprecation warning remains. No full-pipeline
cache-only replay was performed; no claim of repeated-run quality or latency
stability is made.

The bounded contract works on this run; it does **not** establish a QA gain over
the immutable baseline. Keep it opt-in. Stop tuning these opened examples, do not
force a count or repair corpus ambiguity to match gold, and do not spend more calls
recalibrating the judge here. Next freeze a small untouched non-graph continuation
to compare candidate→selected→packed evidence coverage, actual answer usefulness
and cost against local BGE before considering any deployment or larger500 run.
