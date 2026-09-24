# Combined retrieval V2 — first bounded-exploration live result

This is the first live result opened after the bounded-exploration protocol was frozen
in `combined-retrieval-exploration-preregistered-2026-09-24.md`. No dataset label,
threshold, graph fixture, authority rule, or candidate limit was changed after opening
the result.

## Runtime and binding

- dataset: `doppel-combined-retrieval-zh-v2` (`f35257ad354f5132c49f152b0b705fbba2cc7ce04dec4635237c91c505a84f6b`);
- 144 queries, 36 exact owner scopes, and 3,600 memories;
- PostgreSQL authoritative Store plus pgvector (512-dimensional
  `BAAI/bge-small-zh-v1.5` embeddings);
- live Neo4j/Graphiti relation index;
- zero external HTTP calls, LLM calls, or provider tokens;
- report SHA-256: `cbbea9613aaa9d5e13f4a4fe2f031f2ff4781426d263bc18d7068bb90589638e`;
- Neo4j fixtures and the dedicated PostgreSQL benchmark schema were cleaned.

## Result

| Profile | Evidence recall@5 | Complete evidence@10 | MRR | p50 | p95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| lexical + pgvector | 0.667 | 0.556 | 0.815 | 72.2 ms | 89.5 ms |
| reviewed typed path | 0.590 | 0.500 | 0.394 | 7.6 ms | 16.5 ms |
| bounded explored path | 0.750 | 0.667 | 0.333 | 13.8 ms | 18.2 ms |
| independent + typed path | 0.785 | 0.713 | 0.815 | 120.5 ms | 145.1 ms |
| independent + typed + explored path | **0.854** | **0.806** | 0.616 | 136.3 ms | 162.8 ms |

The exploration-enhanced hybrid improved evidence recall@5 by 0.069, complete
evidence@10 by 0.093, and two-hop complete evidence@10 by 0.278 over the typed-only
hybrid. Its category results were:

- one-hop relation: 1.000 evidence recall@5 and 1.000 complete evidence@10;
- two-hop relation: 1.000 and 1.000;
- temporal incomplete-path adversaries: 1.000 and 1.000;
- independent semantic non-relations: 0.417 and 0.417.

The low semantic-only score remains a real weakness; graph exploration did not hide or
regress it. The overall MRR decrease versus the typed-only hybrid also remains visible:
the frozen evaluator ranks every required evidence item, while atomic two-hop path
retention deliberately keeps both supporting records and may place the second support
below an independently retrieved item.

## Safety and accounting

The exploration-enhanced profile returned at most 20 candidates and had zero:

- hard-forbidden evidence;
- cross-scope leakage;
- ineligible exposed records;
- orphan provenance;
- temporal complete-path failures;
- omitted complete paths;
- actual Store revalidation failures.

The independent retriever surfaced 94 records that failed the final authority or
lifecycle filter. All 94 were rejected during authoritative Store-backed assembly and
are now reported as `rejected_base_filter_mismatch`; none was a missing Store record or
post-read scope mismatch. The earlier all-or-nothing rejection counter incorrectly
classified these successful policy rejections as Store revalidation failures. The
reason taxonomy and gate accounting were corrected without changing retrieval output.

## Gate interpretation

The separately preregistered exploration gate passed every check. The legacy
typed-only gate remains failed and is still reported: its frozen provider topology
requires a text-only planner to infer hidden temporal hops, and its typed-only profile
retains six temporal incomplete-path failures. This result does not rewrite that
baseline. Use `--gate exploration` to make the additive gate control process status;
the default remains `--gate legacy` for backward compatibility.
