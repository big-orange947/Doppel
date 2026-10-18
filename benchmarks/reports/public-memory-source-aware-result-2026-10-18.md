# Source-aware BGE/MMR diagnostic: no demonstrated improvement

The opt-in source-aware reranking adapter and frozen three-arm diagnostic are
complete. Reused content-only passage answers retain **2/3** provisional task
grades; the preselected metadata+MMR arm receives **1/3**. Do not promote this
configuration or tune its weight on these opened cases. No fresh continuation was
run after the negative result, and no additional provider calls were authorized
by silently extending the frozen six-call cap.

## Implemented, not enabled as a default query strategy

`doppel_memory.source_aware_rerank` implements the existing `Reranker` protocol.
It can serialize trusted actor/role/authority/candidate-time with text and apply
optional source/token MMR. IDs/scopes are not sent to the scoring provider.
Output payloads and original scores remain unchanged; it cannot authorize scopes,
promote assistant authority, add a candidate or turn top-k into a complete count.
Provider failures/invalid bindings/timeouts are explicit, not silent success.

Following this result, the new adapter's default `diversity_weight` is **0.0**
(disabled). The frozen experimental0.15 arm stays explicit in the diagnostic and
its immutable results remain unchanged. Normal Doppel retrieval defaults never
changed. Metadata-aware scoring is still an explicit adapter choice and requires
a suitable scorer; feeding metadata JSON to a text cross-encoder is not a proven
quality improvement. See [usage and limitations](../../docs/source-aware-reranking.md).

## Frozen comparison

Cases are the same three opened public diagnostics, not a new blind sample.
Reconstruct one production BM25/vector pool80 per case from read-only existing
Store/index, then give exact copied pools to all three arms. The old complete
candidate80 was not persisted; its entire historical identity is not claimed.
Content-only source20 order and packed passage contexts do reproduce exactly,
as do the old Reader request hashes used to reuse prior answers and task grades.

Arms: content-only/weight0; metadata/weight0; metadata/weight0.15. Apply each to
message80→20 and passage≤80→20; use the same local BGE artifact, source safeguards,
1200/160 spans and24KB fit budget. No keyword rules, role quotas or owner filtering.
Only metadata+MMR receives new QA, selected before seeing any arm's output.

| Case / task | Prior content-only passage grade | New metadata+MMR grade |
| --- | --- | --- |
| `e9327a54` / giant-milkshake recommendation | Correct | Correct |
| `gpt4_ec93e27f` / recent bus vs train | Correct | Incorrect by provisional task judge; correct date ordering still present |
| `gpt4_2f8be40d` / attended wedding count | Incorrect refusal | Incorrect refusal |

Metadata-only has context results, **no new answer grade**. No winner was selected
after observing local rankings, and old baseline answers were not regenerated.

## Inspect actual evidence, not speaker counts

The dessert answer still identifies The Sugar Factory, cites the original
assistant recommendation fragment and explicitly says it was not an owner
statement. Keeping assistant evidence eligible remains necessary for this task.

The transport answer cites the March3 owner train ride and the earlier February27
bus trip, explicitly orders the train later, but concludes that the latest actual
transport cannot be confirmed because records between then and the reference date
are absent. It is also Chinese for an English question. This is a conservative
Reader conclusion despite supplied useful evidence; the one-label task-score
drop is not direct proof of retrieval degradation. The grading boundary for a
qualified answer is a known sensitivity. Keep the original primary grade false;
do not run another judge calibration/regrading cycle to obtain a better score.

Wedding metadata+MMR packs11 user and7 assistant passages, versus content-only
0 user/13 assistant passages. This **does not** mean it found better attendance
evidence. Inspection shows owner questions about Gurkha customs, a wish to try
Nepali dishes, game-night reminders, passport/name changes, sports rules, guitar
practice and part of the irrelevant article; the needed attendance accounts are
not delivered. The Reader appropriately refuses the unsupported count, which is
still incorrect for the reference-answerable task. More owner text is not success.

Source-level owner counts for wedding arms are6/20 (content),3/20 (metadata),
12/20 (metadata+MMR). In packed contexts they become0/13,2/14,11/18. There is no
fixed role ratio. Raw topical relevance plus lexical/source diversification can
promote unrelated material rather than evidence useful to the question.
Scores are bounded0..1 but not calibrated probabilities; this run does not record
the full score distribution, so a specific score-scale cause is **not established**.

## Cost, integrity and reproducibility boundaries

- Local scoring18 calls /1100 pairs /zero reported truncations /longest4234
  tokens, within the declared1440-pair bound. All passage budgets unexhausted.
- Exactly the same pool hash per case across arms; authoritative source/provenance
  checks and original inventory before/after hashes pass. No source/index write,
  graph call, migration, cleanup or baseline/data overwrite.
- Backend `model_usage.input_policy` names its default raw-content adapter. The
  effective format here is declared by each arm: serialized metadata is supplied
  to the two opt-in arms. Do not interpret the inherited static label as saying
  this experiment contained no metadata.
- Baseline calls0. New Reader3 and task judge3, all succeeded with complete usage,
  no retries/failures. Reader26078 input /705 output =26783 tokens; judge1481 input
  /138 output =1619 tokens. New total **28402 tokens**, including5760 cached input.
  Original baseline spend remains in its earlier report, not counted as free.
- New citation-ID/derivation structural checks pass3/3, with six citations. Legal
  IDs are not independent entailment or task correctness. No new negative-case
  abstention, complete-count, official AML/LongMemEval or release score is claimed.
- Full pre-safety-default suite: **1964 passed,33 skipped,three subtests passed**
  in242.26 seconds; one existing Graphiti/Pydantic warning. After disabling default
  diversity,31 targeted core/driver/passage tests pass, including a new default
  guard test. Ruff/format/Pyright pass for the new implementation/driver. No exact
  cache-only replay or stable idle-GPU latency result is claimed. `uv.lock` untouched.

## Next decision

Keep this as an experimental integration capability, with diversity disabled by
default; do not ship BGE+metadata+0.15 as a recommended preset. Stop modifying
weights/metadata on these cases. The next useful bounded comparison is a scorer
that can interpret the question's requested information and speaker context,
rather than assuming a text cross-encoder learns that from JSON formatting.
A replaceable listwise LLM relevance adapter is one candidate, not an established
win. It should reorder authorized evidence, not add a hard answer-support gate or
dictate the final answer. Reuse the inexpensive baseline and impose a fresh small
call budget before any paid comparison, then validate promising changes on the
untouched continuation. Do not restart full-history graph construction.

## Artifact bindings

Frozen implementation/context executionca8cf42; QA freeze/executionc3ca50d.
See [pre-execution plan](public-memory-source-aware-plan-2026-10-18.md).

| Local ignored artifact | SHA-256 |
| --- | --- |
| Context preflight v2 | `2277df5123d9bc162cc68bf923aa6d2abc1482a9070ffa8832bdc4027d4189c9` |
| `source-aware-context-live-v1.json` | `4b8cad11b8401402f5d55b6130baee4cb6acc4e916d6d66dfbfd30a27e2aa7df` |
| QA preflight | `6f2cd92789c920aa21b896fa84994520e1d230971f36f07789840c7723fc7396` |
| `source-aware-qa-live-v1.json` | `d643e11bd4a42f290044ead4e2798561234595d8add85517c8cdbd3ca8b0a0a5` |
