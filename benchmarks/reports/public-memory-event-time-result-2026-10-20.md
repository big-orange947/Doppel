# Opened-eight occurrence-time repair: result

Implementation and protocol were committed and pushed as **dcba516** before paid
execution. This is the same eight already-opened development cases, not an
independent validation set, complete LongMemEval score, AML result or release
gate. No default analyzer/planner promotion.

## Results and interpretation

| Ordinal | Type | Raw | Structured | Actual query behavior |
| --- | --- | --- | --- | --- |
| 02 | temporal | fail | fail | Lookup,4 hits; still refuses relative trip ordering |
| 03 | update | pass | pass | Still count+episode gate,0 hits; raw/all-claims fallback answers5 |
| 05 | multi-session | pass | pass | Count,4 hits; both report4 cuisines |
| 07 | abstention | pass | pass | Lookup,13 hits; neither substitutes niece for uncle |
| 09 | temporal | pass | pass | Now lookup,10 hits; both report6 days |
| 12 | multi-session | pass | pass | Count,2 hits; both report2 appointments |
| 16 | temporal | pass | pass | Now lookup,8 hits; both report4 days |
| 19 | multi-session | fail | pass | Count,3 hits; structured reports3 distinct dates |

Frozen provisional task judge: **raw6/8, structured7/8**, one gain, no regression.
Temporal2/3 each; multi-session2/3 versus3/3; update and abstention controls1/1
each. This is not evidence of general87.5% accuracy or statistically established
superiority. The previous trial had6/8 in both arms; raw answers change across
fresh provider calls despite temperature=0. Do not replace the uniform50-case
baseline of37/50 with this selected development score.

Important grading sensitivity: on ordinal19 the raw answer primarily reports2,
but also explicitly gives **3 if the church food drive is included**. The
structured answer primarily reports3 while acknowledging the same category
ambiguity. The provisional judge distinguishes primary answers; under a rule
accepting any conditional reference value, both could pass. Do not silently
regrade the frozen result or interpret this one-point difference as proven new
answer coverage. Both arms already cite the food-drive source.

## More concrete evidence: same-proposal interval ablation

Ordinal19 extracts3 completed December activities, each quoted from a January
10 recollection: December10,17,24. The actual same-plan query now retains all3.
Remove only typed event_time metadata from exactly those proposals/IDs, and the
unchanged legacy observation-date fallback rejects all3 as outside December.
Other seven cases have the same selected-hit counts under this ablation.

Thus the engine's **observation-time versus occurrence-time membership bug is
repaired on this actual trace**, independently of provisional answer grading.
It does not isolate the downstream QA benefit: the structured Reader also sees
all candidate interpretations and unchanged raw evidence, and both analyzer and
planner versions changed. No extra QA call was made for the metadata-removed
view. Current/as-of state validity and full graph indexing were not evaluated.

## Extraction and planner audit

-78 drafts:77 schema-valid,1 schema-invalid;6 source/subject mismatches
 quarantined,0 low-confidence drops;71 bound candidate claims,16 episodes.
-12 occurrence coordinates:10 resolved day-tagged ranges and2 unresolved;
 basis labels7 explicit,3 resolved_relative,2 unresolved. Four episodes omit
 the new coordinate. All12 retain source quotes, IDs and trusted observation
 anchors; **none has independently verified normalization**.
-71 records scanned,44 hits. No candidate promotion or persistent source writes.
 All16 Reader outputs pass citation/derivation structure checks;39 citation
 links legal. Those checks do not prove semantic entailment or answer quality.
-V3 fixes the two elapsed-duration routes (ord09/16 become lookup without hard
 episode restrictions), but **does not fix ordinal03**: the question alone
 still induces count+episode filtering, excluding all6 state/plan/relationship
 candidates, including reported MCU totals. Raw/all-claims fallback saves QA.
 A query-only planner cannot always know that an answer exists as a reported
 aggregate; merely strengthening its prompt is insufficient.

Source-text inspection also exposes remaining interpretation defects, not hidden
by the successful run:

1. Ordinal16 source says **decided to upgrade** pedals, but one extracted episode
   says **upgraded**. The source is correctly owner-bound, yet action completion
   is not entailed. Candidate state and normalization_verified=false do not cure
   this error; do not advertise plan-to-fact safety as solved.
2. Ordinal05 normalizes **last week** to a seven-day range but labels precision
   **day**. Bounds preserve a week rather than a single invented date, but the
   precision label is inconsistent; the current shape validator does not check
   calendar granularity. Ord09 also labels **today** explicit rather than
   resolved_relative. Exact quote binding is not semantic/time verification.
3. Ordinal02 still over-refuses the supported ordinary-language ordering of
   “a few years ago” and “last summer”. Raw output also has abstained=false while
   saying ordering cannot be determined, and language drift persists. The Reader
   was deliberately unchanged; no claim that answer-layer bugs were repaired.

## Cost, replay and reproducibility

48 new calls,48 succeeded,0 retry/repair, complete usage accounting:

| Stage | Calls | Input tokens | Output tokens | Total |
| --- | --- | --- | --- | --- |
| Analyzer | 8 | 57813 | 7985 | 65798 |
| Planner | 8 | 12872 | 1083 | 13955 |
| Reader | 16 | 146242 | 4679 | 150921 |
| Provisional judge | 16 | 8244 | 780 | 9024 |
| Total | 48 | 225171 | 14527 | **239698** |

Raw Reader requests225436 UTF8 bytes; structured313866 bytes, **+39.23%**.
Not a matched-token/compute comparison. No embedding/graph rerun, eager
full-history analysis, persistent source writes or protected-history access.
Provider tokens are not exact currency billing.

A separate child process cleared DEEPSEEK_API_KEY and used cache-only mode:
zero new calls, all outputs and cumulative usage unchanged, byte-identical files.

- Frozen plan: f83d1b368e99154f6046153f8cf0ecb71c7507a724a8314ab24511c3ede0522f
- Preflight file: data/doppel/structured-event-time-preflight-frozen-v2.json
- Live file: data/doppel/structured-event-time-live-v2.json
- Replay file: data/doppel/structured-event-time-replay-v2.json
- Live/replay file SHA-256:
  288809840186943057b82e9aa50dd31fb49719676cfb73b619afa396e7e49b6d
- Durable run directory: data/doppel/structured-event-time-v2

Artifacts remain ignored; no secrets are staged. Old paired-v1 reports/caches and
their original implementation pins remain unchanged. The new optional wire
fields change JSON schemas/request fingerprints; old inputs still load with
event_time=null, but old request caches are not claimed compatible with new code.

Verification: after explicitly updating the provisional API manifest and wire
field-order snapshots for the additive fields, full suite **2117 passed,
33 skipped,3 subtests**, Ruff clean. The first full pass correctly caught those
two omitted compatibility snapshots (2115 pass/2 fail); no runtime assertion was
relaxed. Nineteen new event-time tests cover actual extraction/query/transient
paths, source/clock/actor/scope gates, legacy fallback and uncertainty.

After live execution/replay, an additional conservative consolidation guard was
added: identical-content episodes cannot merge if bound occurrence metadata
differs, is present on only one source, or is invalid. Two new targeted tests
exercise this guard, along with77 passing event/consolidation/group/API tests.
This post-run guard is not in the dcba516 paid-run source pin and does not alter
its saved answers, metadata ablation or grades. No new paid calls were made.

## Next narrow step

Use the existing candidate pool for two-pass quantity planning: retrieve reported
totals alongside event candidates before deciding whether enumeration is needed.
Keep unknown completeness and raw fallback; never turn event counts into day
counts. Add generic development controls for decision-versus-completion and
precision/bounds consistency, then a bounded new paired run, not full eager
graph construction. Do not add MCU, church, travel or question-ID exceptions.
