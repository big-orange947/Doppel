# Reference Planner v12 live run

Date: 2026-09-08. Provider: DeepSeek `deepseek-v4-flash`. Source report:
`relation-planner-v12-v14-deepseek.json`, canonical SHA-256
`7fe9729c61ee80a7553efa64625f3f195820c39cc770d66be39012f98c8ae0bc`.
The raw report remains a local benchmark artifact because it contains model outputs.

This is a first-pass exploratory result over the draft v1.4 dataset, not a
publication-ready score or a concurrent randomized comparison. All 65 questions were
attempted with 65 provider calls and no retries. The provider returned 64 valid
drafts; `rel-q25` returned `intent=as_of` without `as_of` and failed strict validation.
Provider usage was 182,661 input tokens, 6,770 output tokens, and 189,431 total tokens;
104,832 input tokens were reported as provider-cached. Latency was 1,115 ms p50,
1,343 ms p95, and 1,582 ms maximum.

## Raw v1.4 scores

| Metric | Result |
| --- | ---: |
| Valid drafts | 64 / 65 (98.46%) |
| Intent semantic accuracy | 89.23% |
| Temporal plan accuracy | 95.38% |
| Subject binding | 98.46% |
| Entity recall | 93.75% |
| Relation-type exact match | 66.15% |
| Relation-type recall | 92.19% |
| Relation-type precision | 70.24% |
| Relation-hint exact recall | 43.75% |

The 12 v11 cases rejected for unknown provider fields were all valid in v12. This run
alone cannot prove that projection handled those exact responses because the report
did not persist a projection counter; contract tests independently cover projection.

## Post-run gold audit

Inspection found two benchmark-label errors, now corrected in draft dataset v1.5:

- `rel-q49`, “折叠自行车去年在哪家车行维修？”, correctly produced the full
  2025 interval; v1.4 incorrectly expected no interval.
- `rel-q64`, “护照是什么时候续签的？”, correctly used `lookup`; renewal is a
  completed enduring event fact, not a superseded or ended state.

These corrections would make intent semantic accuracy 59/65 (90.77%), temporal-plan
accuracy 63/65 (96.92%), and interval presence/boundary accuracy 64/65 (98.46%) when
the same stored drafts are rescored. They do not change the model inputs or outputs.

The remaining useful failures are cross-field temporal planning (`rel-q25`, `q45`,
`q54`), mutable ongoing-repair intent (`q22`, `q37`), explicit history (`q50`), and
over-broad relation candidates. Relation-hint exact matching failed 36 valid cases,
but that surface-form diagnostic must not drive query-specific prompt rules. The next
decision belongs to end-to-end retrieval: whether vector and Graphiti candidate union
find the right evidence while scope, time, lifecycle, provenance, and Store reload
remain strict.
