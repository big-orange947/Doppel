# Descriptive graph-path contribution, not an ablation

Zero provider calls, no retrieval/reranking/repacking, no changed answers/scores.
The new offline receipt auditor checks complete V3 receipts, frozen plan identity,
Store/vector/graph integrity flags, context/citation uniqueness and agreement
between reported base rank and actual base membership. It reads no gold or
question text for attribution. It cannot independently validate graph semantics,
provenance or answer accuracy; integrity flags are claims in the original receipts.

Fixed source-order fourth/fifth/sixth completed receipts were inspected together,
including the fourth failed answer, rather than selecting successful results.

| History | Path-supported assembled IDs | Added outside base | Path-supported packed IDs | Added outside base and packed | Added outside base and cited |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fourth | 0 | 0 | 0 | 0 | 0 |
| Fifth | 17 | 11 | 6 | 0 | 0 |
| Sixth | 0 | 0 | 0 | 0 | 0 |

Each full run has 100 base and 20 assembled memory candidates. Fifth paths really
expand that base candidate set by eleven memories, but none of those eleven are
packed or cited. One cited memory (thermostat setup) is path-supported but was
already in the base. This does not demonstrate that graph paths improve the final
answer, nor that those additional candidates are irrelevant. Reordering shared
candidates could still change packing. A controlled graph-off run with the same
plan and fresh packing/Reader would be needed to test that effect.

**Base is not pure vector:** it may itself contain graph-relation, lexical and
vector candidates. Do not interpret these overlaps as an ablation of all Graphiti
or use them to remove graph capability. Counts are descriptive membership, not
relevance/recall metrics. A cited path-added record would still not prove necessity
or task correctness. The tool explicitly reports these limits as false claims.

Reproduce without a key:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_memory_path_contribution `
  --receipt data/doppel/public-memory-next-query-scope04-live-v1.json `
  --receipt data/doppel/public-memory-next-query-scope05-live-v1.json `
  --receipt data/doppel/public-memory-next-query-scope06-live-v1.json
```

No production changes or default-profile changes. This additive diagnostic is not
included in already-frozen query/writer source identities. Eleven offline tests
pass, including refusing bad fingerprints, missing integrity flags, duplicate/
illegal citations, inconsistent ranks, and no-uplift claims even when an added
record is cited. Full regression: **1512 passed, 33 skipped, three subtests passed**,
one existing Graphiti/Pydantic deprecation warning, 163.96 seconds. Ruff and new
file formatting pass. `uv.lock` stays user-modified and unstaged.
