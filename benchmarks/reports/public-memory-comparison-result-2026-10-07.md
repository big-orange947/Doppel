# Opened LongMemEval pilot: real raw / memory / combined retrieval

## Execution and scope

The [pre-score plan](public-memory-comparison-plan-2026-10-07.md) and runner were
committed as `83de280bd4b607e11e6e7da3c54cbb4d25ca8990` before this run. Actual
source binding includes comparison module SHA-256
`dd453b6a4a09eaf9045b93f2d375cad66273e59c76dfe6f8db87bdc99e0fc7e5`.
Only the existing user-owned `uv.lock` was tracked-dirty. No score-conditioned
selection, quota, alias, prompt, ranking adjustment or core default change.

Local ignored artifact: `data/doppel/longmemeval-memory-comparison-v1.json`.
SHA-256: `a152356232524db418bcdcc9b6104f9ce90c8d94627338effd379440e7195ae7`.
Input completed-ingestion report SHA-256:
`3b899f08aa9dabbb15a89e455a2907046228a81abd776407eff0348c809b7d1c`.

Actual corpus: all 1513 raw messages, 599 owner-derived memories and four
governance records across the same three complete diagnostic histories. Governance
records were not returned as claims. All 2116 vector entries passed existing-entry
fingerprint/version checks. The corpus snapshot before and after was identical:
`8e64ecd29a6807d028d77f124e336505ca9459a529d2b628e3798008a86301e5`.
No record or vector-entry writes/reindexing; normal backend initialization may run
idempotent DDL. The completion/source journal was opened in SQLite read-only mode.

Production pgvector + existing local FastEmbed 0.8.0 BGE-small-zh-v1.5, 512 dimensions.
Small-corpus exhaustive cosine ordering with channel selection before the 80-item
candidate cap. Combined gets one cap, not two. Local BGE-reranker-v2-m3 actually ran
on `cuda:0`, 9 calls / 720 query-item pairs, zero tokenizer truncations, longest
pair 812 tokens. Its reused provider report calls its input `raw-text-only`; in this
comparison the adapter supplies raw **or derived item text**, with no labels or
metadata included in the CrossEncoder input. Model-file hashes are in the artifact.

Six profiles × three opened questions = 18 rows. Maximum final context: 20 whole
items and 24,000 compact UTF-8 JSON bytes including attribution/time/citations.
There was no source expansion or reader execution. Bytes are not reader tokens.

## Annotated source coverage

There are only **five annotated source turns in three questions**. Counts below
are micro-aggregated over those five, not 500-case scores, answer accuracy or
generalization evidence. Memory-channel values measure **citation provenance**,
not whether a summary retained every relevant detail. Ranks also use different
item units: messages versus memories. Alternative valid sources may be unlabeled.

| Profile | Candidate provenance coverage | Top-5 provenance coverage | Packed provenance coverage | Total packed JSON bytes |
| --- | --- | --- | --- | --- |
| raw + vector | 5/5 | 2/5 | 4/5 | 44,980 |
| memory + vector | 4/5 | 3/5 | 4/5 | 33,448 |
| combined + vector | 5/5 | 3/5 | 4/5 | 43,215 |
| raw + vector + reranker | 5/5 | 5/5 | 5/5 | 65,201 |
| memory + vector + reranker | 4/5 | 4/5 | 4/5 | 33,025 |
| combined + vector + reranker | 5/5 | 5/5 | 5/5 | 51,684 |

The raw reranked second/third outputs pack 19 and 15 messages respectively due to
the byte bound; all other outputs pack 20 items except the combined reranked third
output, which packs 15 raw messages. No truncation, oversized-item skipping or
unlimited evidence expansion was used to improve scores.

## Findings, without changing the experiment

1. **Ordering matters even when candidate coverage is complete.** Raw vector-only
   finds all five annotated sources somewhere in the 80-candidate pool, but only
   two are top five. Content-only reranking moves all five into top five.
2. **Personal facts do not replace conversational context.** `cc539528` asks for
   backend languages the assistant previously recommended. Its one labeled source
   is an assistant reply. The 599 accepted memories are owner/HUMAN_SELF facts;
   memory-only returns no citation to this assistant source. This is not evidence
   that an owner fact was lost, or a reason to relabel agent_output as a fact.
   Raw and combined retrieval preserve the correctly attributed assistant context.
3. **The combined route is useful here, not proven universally superior.** It
   matches raw reranked annotated coverage with 51,684 versus 65,201 bytes across
   these three outputs, **20.7% less JSON**. This is not yet equal answer quality,
   tokenizer usage, monetary saving or a reason to change the default strategy.
4. **Retrieval coverage is not temporal/governance correctness.** In `50635ada`,
   the reranked memory text includes both Premier Gold and earlier Premier Silver,
   but both memories carry `temporal_status=current` and null valid bounds. Their
   observation times remain in the packed context. The reader must still correctly
   resolve “previous before current”; this run has no temporal-answer score and
   does not silently treat these metadata as validated temporal truth.

496 final item/source Store reloads matched the pre-search authoritative snapshots.
All raw and derived source bindings were checked during inventory. These checks
are not a separate adversarial security benchmark or semantic entailment score.

## Verification and next stage

- New synthetic boundary/composition tests: **23 passed**. Cover read-only complete
  journal binding, runtime/source mapping, question-independent ingestion binding,
  role/authority, cross-scope references, missing/revoked evidence, citation
  deduplication, shared candidate cap, complete serialized-byte prefix budgeting,
  poisoned candidate text, stale indexes and post-ordering revocation/invention.
- Full suite: **1152 passed, 33 skipped, 3 subtests passed**, existing upstream
  Graphiti Pydantic deprecation warning. Ruff lint and changed-file formatting pass;
  Pyright has zero errors. Pre-existing whole-repo format differences not rewritten.
- Zero new paid LLM calls/tokens; no Planner, graph retrieval, reader or judge.
  Production PersonalMemoryQueryEngine was not substituted with an oracle: it was
  explicitly not run. AML models and the three reserved groups remain unexecuted.

Next freeze a single reader request/schema, question/reference-calendar handling,
token measurement and answer/citation judging contract for the already packed
outputs. Gold is available to the scoring stage only, never retrieval or the reader.
Preserve failed answers and distinguish correct answer / valid provenance / adequate
information. Then run a larger unchanged diagnostic/reserved evaluation. Do not
optimize the personal-memory policy for this assistant-reply question or report
these five-source results as a publication-ready full benchmark.
