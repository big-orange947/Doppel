# Eighth consecutive opened-history diagnostic

Unchanged highest-config query, provided-history-v1 clock, Reader V2. Not blind,
not full LongMemEval or AML. Complete execution is not answer correctness.

Case `0977f2af` asks which gadget preceded the Air Fryer; reference Instant Pot.
Task judge: incorrect. Reader mentions Instant Pot but abstains because its
acquisition date is not given. Both annotated turns/sessions present (2/2 each),
two legal citations. Citation judge: partially_supported, no contradiction.
188 local CUDA pairs, zero truncation/source failures, one typed graph path
search plus one exploration search, 20 promoted hits. No graph-uplift claim.
Store/vector/selected graph unchanged, execution completed within contract.

Source audit distinguishes observation and purchase time. Owner says “my new
Instant Pot” at 2023-05-21T05:48Z, and “the Air Fryer I got yesterday” at
2023-05-21T22:54Z. The latter suggests May 20; the former does not establish a
purchase date. Citation judge's claim that May 21 is *before* May 20 is invalid.
Do not use that rationale as truth or reverse the retained task score. Resolving
the reference fully needs the surrounding source history, not a forced temporal
heuristic. Reader answered an English question in Chinese: language drift remains.

- Schema: six successful requests/11954 tokens; 127 definitions, graph unchanged.
- QA: planner two/20577, reader one/5510, task one/527, citation one/7438.
- QA total: five successful calls/34052 tokens, no missing usage/retries.
- Eighth whole source pipeline: 736 calls/3040135 reported tokens.
- Live `data/doppel/public-memory-next-query-scope08-live-v1.json`, SHA-256
  `f28b227cb9d8e6d1bac9c7a1e90742ad274d1569c0a4f415a06b6711b7fb082f`.
- Empty-key replay `data/doppel/public-memory-next-query-scope08-replay-v1.json`,
  SHA-256 `56a8253c2acd7e2fc6e0169f8b681bc051241a6bb0bcb1704459a10dc924c127`.
  Zero new calls; plan/retrieval/reader/task/citation/context/packing/evidence
  fields canonically identical. Old answer/cache remains immutable.

Source-window follow-up is separate: opened scopes 5–8, fresh preregistration,
same retrieval checkpoints and Reader, not retrospective baseline score repair.
