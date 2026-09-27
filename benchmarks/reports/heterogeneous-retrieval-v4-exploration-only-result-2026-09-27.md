# Heterogeneous retrieval V4 — exploration-only opened result

This report preserves the first run of the preregistered V4 exploration-only
ablation. The result is an **opened architectural regression test**, not a new sealed
or publication-quality generalization claim. The runner and non-regression gate were
committed and pushed as `a8da537d1f53f3ad923da77cb288f730ae0bc3b9` before the
run.

The result failed the frozen gate. Removing exact relation-path candidates preserved
MRR and related-context coverage, but reduced answer-evidence recall within the bounded
context. The failure is retained rather than repaired by post-result tuning.

## Reproducibility

- dataset: `doppel-heterogeneous-retrieval-zh-v3` (`3.0.0`)
- dataset fingerprint:
  `ead91761f9da403c31c8b759d427c4551709daf7d29f35d26d786f94ec167f88`
- selection: all 480 queries, 48 exact owner scopes, and 9,216 memories
- implementation commit: `a8da537d1f53f3ad923da77cb288f730ae0bc3b9`
- report payload hash:
  `66fc8aa59eed7e2440a722501d86cbcbddcfa24747692e623b29c4899a062689`
- raw JSON file SHA-256:
  `42fb1846a96c529e5c6b266333423d0074dd7dfa80b6f9be22d0468b86e91eaf`
- authoritative Store: PostgreSQL
- independent retrieval: PostgreSQL lexical plus 512-dimensional pgvector cosine
  search using `BAAI/bge-small-zh-v1.5`
- graph retrieval: local Neo4j/Graphiti exact paths and bounded exploration
- reranker: local `bge-reranker-v2-m3`, CUDA, 64-record window
- final context bound: 20 memories
- external HTTP requests / LLM calls / provider tokens: `0 / 0 / 0`
- tracked dirty path disclosed by the runner: the pre-existing user-owned `uv.lock`

The ignored raw result is
`data/doppel/heterogeneous-retrieval-v4-exploration-only-opened-live.json`.

## Result

| Profile | Evidence recall@5 | Complete evidence@10 | Related context@10 | MRR | p50 / p95 ms |
|---|---:|---:|---:|---:|---:|
| independent lexical + vector | 0.871 | 0.843 | 0.646 | 0.898 | 79.1 / 94.0 |
| oracle exact graph path | 0.273 | 0.222 | 0.000 | 0.222 | 0.0 / 18.5 |
| bounded graph exploration | 0.273 | 0.222 | 1.000 | 0.222 | 0.0 / 19.7 |
| assembled oracle hybrid | 0.920 | 0.903 | 0.646 | 0.898 | 177.6 / 225.8 |
| assembled oracle + exploration | 0.962 | 0.954 | 1.000 | 0.898 | 182.9 / 242.4 |
| oracle + exploration + memory reranking | **0.998** | **1.000** | **1.000** | **0.933** | 355.1 / 451.9 |
| assembled exploration-only | 0.920 | 0.903 | 1.000 | 0.898 | 174.5 / 221.1 |
| exploration-only + memory reranking | **0.956** | **0.949** | **1.000** | **0.933** | 340.7 / 436.6 |

The exploration-only final profile passed every absolute threshold and every safety,
Store-revalidation, boundedness, accounting, and cleanup check. It failed the two
frozen comparisons that require parity with the oracle final profile: evidence
recall@5 and complete evidence@10. Its roughly 14--15 ms p50/p95 saving is not a
reasonable exchange for this evidence loss.

## Failure localization

The exploration-only final profile had 23 queries with missing evidence at rank 5.
One is the previously known `q-u46-corrected-role` ranking weakness; its required
memory is present at rank 10. The other 22 are all `two_hop_relation` queries. In each
of those cases the first leg (`object -> holder`) remains at rank 1, while the second
leg (`holder -> location`) falls below rank 10, usually near ranks 12--18.

Consequently, two-hop evidence recall@5/@10 is `0.770833` and complete evidence@10 is
`0.541667`, even though one-hop relation retrieval remains perfect. The failure is
concentrated in the open dev and sealed owner ranges; the adversarial aggregate still
reached 0.989 recall@5 and 1.000 complete evidence@10.

This also explains why aggregate MRR is unchanged: the metric rewards the first
relevant item, and the first leg of every two-hop chain still ranks first. MRR alone
would therefore hide incomplete multi-record evidence. Complete-evidence rate is the
decisive metric for this failure.

The earlier memory-ID containment observation remains true but was insufficient. The
assembly contract retains every memory supporting a selected path atomically and
scores records through their path hits. Exact two-hop retrieval preserves the joined
evidence as one typed route; generic exploration discovers the same individual memory
IDs but does not give the second leg equivalent joined-path priority. Candidate-set
coverage is therefore not interchangeable with path-aware ranking.

## Safety and cleanup

Both final profiles recorded zero hard-forbidden hits, cross-scope leakage, subject
violations, ineligible-state hits, temporal violations, orphan provenance, Store
revalidation failures, path-budget omissions, and reranker membership violations.
Every output stayed within 20 memories. All 480 reranker outcomes were accounted for,
and both Neo4j fixture cleanup and PostgreSQL reset completed successfully.

## Decision

Do not remove exact relation paths from the highest-quality retrieval profile yet.
The next experiment should not add benchmark-specific relation labels or query
special cases. It should test a generic, entity-anchored bounded multi-hop exploration
contract that retains connected path evidence atomically. Exact path planning remains
the quality reference until that generic topology-aware alternative passes a new
versioned opened ablation. Planner time, intent, count, and entity responsibilities
remain separate from this decision.
