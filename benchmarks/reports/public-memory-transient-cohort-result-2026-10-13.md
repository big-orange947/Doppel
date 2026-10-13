# Five opened cases: one paired gain, extraction omission remains

Frozen implementation `d99e6e4`, starting HEAD `424e752`.
[Preregistered plan](public-memory-transient-cohort-plan-2026-10-13.md).
**15 calls complete, zero failures/retries: five shared analyses and ten Readers.**
Under non-independent manual review, coherent reference-task completion is
3/5 plain versus 4/5 with the temporal index. This is not an independent,
full LongMemEval, production retrieval or AML result. No core/default changes.

## Selection and what is actually measured

Five previously opened S histories, original source order: two temporal, two
update, one no-answer. Prior two view cases and all reserved IDs are excluded.
Selection does not use prior answer success, question wording or evidence phrases.
The immutable fifty-case manifest/comparison/QA request identities are rebuilt
and checked. All five have prior QA exposure; do not call this unseen validation.

Use the exact saved raw-vector-reranked contexts: 96 original messages. No new
retrieval, full-history extraction, graph/vector/reranker, Store/journal writes or
Judge. Existing source-window analyzer/miner gates, decoder, Reader settings,
proposal projection and read-only temporal builder stay unchanged. Analyzer has
no question, gold, category, profile or old answer. Both Reader arms preserve the
same raw evidence/proposals, schema and instructions; only the added index/length
differ. No parameter/prompt/topic-specific repair after observing results.

Actual model receipts: all 15 `deepseek-flash`, finish `stop`; requested alias
`deepseek-v4-flash`, not a pinned snapshot. json_object, temperature zero, thinking
disabled; output limits 4,096 analyzer/1,024 Reader. All requests stay below 100KB,
none truncated. One shared analysis is paid once per case, not twice for the arms.

## Paired review, not a substring score

Ten Codex manual decisions are bound to the canonical live artifact. Ten exact
answer quotes, twelve source quotes and ten declared source timestamps validate.
This is **non-independent review**: anchoring verifies provenance, not the truth
of semantic judgments. A reference value among rejected/conflicting alternatives
is not a completed unique-answer task. Legal citations do not establish support.

| Opened ID | Task | Plain proposals | Temporal index |
| --- | --- | --- | --- |
| `29f2956b_abs` | Daily violin practice duration | Correct refusal; only guitar duration supplied | Same correct refusal |
| `gpt4_6dc9b45b` | Months since SIFF attendance | About four months, correct qualified derivation | Same qualified result |
| `b46e15ee` | Charity event about a month earlier | Refuses after erroneous day-before claim | Walk for Hunger; correct 30-day calendar difference |
| `d7c942c3` | Mother now using same grocery-list method? | Yes, from explicit update | Same yes with observation caveat |
| `618f13b2` | Cumulative sneaker wear count | Gives conflicting four/six, no unique answer | Same unresolved alternatives |

Strict coherent task completions: **3/5 vs 4/5**; temporal 1/2 vs 2/2, update
1/2 vs 1/2, no-answer 1/1 vs 1/1. One refusal cannot estimate a refusal rate;
one paired gain and correlated same-model arms cannot establish statistical or
general improvement. Merely accepting any mention of the reference would change
the shoe row; that is not the task-completion criterion used here. No official
scorer label is produced or substituted into old scores.

### The observed temporal gain is a reasoning correction, not recall

Both arms contain the same March 19 source: the owner says Walk for Hunger
happened “today.” Question reference is April 18. Plain output acknowledges the
March 19 event yet calls it “提问参考时间的前一天” and refuses. Candidate computes
the 30-day calendar difference and selects the correct event. Evidence was already
retrieved; this is not a candidate-discovery or recall gain. It does not isolate
time-index benefit from additional input length and generation variability.

SIFF source says “today” on June 1 and a week of attendance; October 2 supports
approximate four months. Both outputs qualify absent festival start/end dates,
which is appropriate approximate derivation rather than exact interval extraction.

### Shoe conflict: preserve task failure and faithful reporting separately

Reference expects a unique six. Actual supplied owner statements say six at
May 30 17:45 and four at May 30 22:16, without an explicit correction. Both outputs
show those conflicting counts and decline a unique answer. Count them as task
noncompletion, but preserve faithful conflict reporting. Do not force six, pick
newest four, alter dates or excuse task failure by rewriting the reference.
Full source/projection semantics need separate audit before calling the dataset
wrong; this experiment does not establish the definitive real-world count.

Both shoe outputs use `abstained=false`: under the unchanged Reader policy, a
substantive partial answer may use false. That is not independently labeled a flag
bug merely because the output cannot resolve a unique value. It is not evidence
that the reference task was completed either.

## Extraction and governance limitations

66 schema-valid drafts, zero invalid/low-confidence/duplicate drafts; three are
quarantined for subject/source mismatch in the mother case, leaving **63 candidate
proposals**. These rejections do not prove the mother's reported facts are false:
the extractor's identity qualification differs from Reader access to raw sources.
Original mother statements remain available, allowing both Readers to answer yes.

All **63 proposals lack effective bounds**. Every view remains candidate/read-only;
no correction, expiry or source deletion is applied. Consolidator emits zero
advisory decisions on this cohort, so conflict-decision utility is not measured.

Crucially, shoe proposals retain four but **omit the explicit six-count claim**.
The six-count source ID appears only in an unrelated brown-boots summary. This is
not missing raw retrieval or failed evidence-ID/schema validation: source text is
present, schema is valid, and semantic extraction has lost a relevant assertion.
Reader detects the conflict only because raw sources are preserved. Do not infer
complete source meaning from legal provenance links or high model confidence.

The reference prompt's same-entity enrichment language is a possible contributing
ambiguity, not a demonstrated causal root: sharing an entity does not imply claims
are compatible. Next extraction work should generically preserve incompatible
assertions and their individual evidence/observation provenance before consolidation,
not fix shoe counts or force benchmark answers. Version/prompt changes need fresh
fingerprints/caches and unrelated controls; current results remain unchanged.

All ten answers are Chinese to English questions; language drift persists and is
reported separately, not disguised as extraction/recall failure. Reader is local
diagnostic, not the AML platform Answer model. No new Reader policy tuning here.

## Time and safety boundaries

Only `d7c942c3` has later-than-reference observations (five); both arms retain them
under declared provided-history semantics, not causal/as-of replay. Its cited
explicit update predates the question, but the whole input still is not a strict
causal snapshot. Other four cases have no retrieved observations after reference.

All ten citation/derivation checks pass, 28 citation occurrences with no illegal
or duplicate IDs. All 63 views pass exact-scope source/actor/time/subject binding;
this is an in-process fixed-source diagnostic, not live Store revocation or
multi-instance security validation. Host authorization is not replaced. The
unknown-violin context has zero literal violin/fiddle mentions across twenty
items; this literal check is supporting evidence, not a general absence proof.

## Cost

| Stage/arm | Calls | Input | Output | Total tokens |
| --- | ---: | ---: | ---: | ---: |
| Shared analyzer | 5 | 24,953 | 6,863 | 31,816 |
| Plain Reader | 5 | 36,353 | 1,249 | 37,602 |
| Temporal-index Reader | 5 | 47,456 | 1,391 | 48,847 |
| Complete experiment | 15 | 108,762 | 9,503 | 118,265 |

Index adds **11,103 Reader input tokens, 30.54%**. Reader total increases 11,245
(29.91%), including output variability. If each route paid its own extraction,
path totals would be 69,418 plain and 80,663 indexed; shared experiment extraction
is counted once. No direct-raw-only arm executes here: do not extrapolate gains or
cost relative to raw-only using different old prompts/cases.

All 15 calls report complete usage. Provider cached input 46,592; cache-miss input
62,170; reasoning reported zero. Live local disk-cache hits zero. Balance CNY 4.88
before/after is immediate observation, **not zero-cost or settled billing proof**.
No deployment bill, 500-case estimate or latency claim. No Docker/GPU/hosting work.

## Replay and regression

Separate child process with key removed: five analyzer and ten Reader local-cache
hits, zero misses/new calls, exact plan/rows including all views, proposals,
checkpoints and request identities. Durable attempts stay 5/10. Parent reports,
old cache, datasets, database and journal are untouched; user `uv.lock` unstaged.

| Artifact | SHA-256 |
| --- | --- |
| Frozen preflight | `02f14e3b73b545ed3b545b782fb9bb95d99c540c923c2ffa2f9e6b018917fceb` |
| Plan fingerprint | `f2d0f4da2a8f520129ddaf12f57dead47a2bf378ae6c9f56f1756e3447d77ab5` |
| Live file | `492e3e627205cc812d0e4ebf755dab6210c55fe9941beec1dabfb9b5b2444f21` |
| Canonical live review binding | `db2d5aefa98e45bacbc73c9230d2e134dba7ff32f7850ab604b9ae56faf2a00a` |
| Key-removed replay | `ec1fcb7380a71b9096ff193a324cd04af0c01622587f145624ea8d498a621fdc` |

Ignored files: `data/doppel/transient-cohort-{preflight-frozen,live,replay-no-key,
manual-review,review-validation}-v1.json`, run directory `transient-cohort-v1/`.
Model receipts preserve closed returned-model/finish metadata, no credentials,
headers or raw HTTP envelope. New six tests pass; full regression **1,762 passed,
33 skipped, 3 subtests passed**, with one existing optional Graphiti/Pydantic
deprecation warning. Repository Ruff and new-runner Pyright pass.

## Decision

One positive paired result justifies keeping the opt-in view available, not changing
the default or claiming superiority. The more actionable result is the analyzer's
loss of a conflicting assertion despite correct raw discovery. Prioritize bounded,
generic extraction-preservation controls and versioned analysis changes next.
Do not repeat/tune these five cases, tighten refusal to improve scores, add a
six-count rule, or silently choose newest. Preserve all old artifacts and distinguish
task completion from faithful uncertainty. No expensive full S eager restart or
official/AML score follows.
