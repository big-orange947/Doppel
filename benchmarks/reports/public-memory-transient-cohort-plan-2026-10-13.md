# Frozen five-case transient-view expansion

Starting HEAD `424e752`. This is an opened public-data pipeline/Reader diagnosis,
not a blind, independent, complete LongMemEval or AML evaluation. No core algorithm,
default policy, extraction prompt or Reader rule changes. All old artifacts/runners
remain unchanged. Do not adapt this cohort after observing new answers.

## Source-order selection, not success selection

From the previous fifty-case diagnostic partition, scan the original S dataset
order and take two non-abs temporal-reasoning cases, two non-abs knowledge-update
cases and one `_abs` refusal case. Exclude the two preceding view cases and every
reserved ID from current/prior manifests. Public type is sampling metadata only.
Do not use question content, source phrases, prior scores or old answers to select.
Missing quotas fail; no difficulty-based substitution or outcome-based resampling.

| Selected ID, original source order | Stratum | Saved raw items | Analyzer request bytes | Observations after question clock |
| --- | --- | ---: | ---: | ---: |
| `29f2956b_abs` | no-answer | 20 | 20,253 | 0 |
| `gpt4_6dc9b45b` | temporal | 20 | 12,620 | 0 |
| `b46e15ee` | temporal | 16 | 23,874 | 0 |
| `d7c942c3` | update | 20 | 15,762 | 5 |
| `618f13b2` | update | 20 | 21,510 | 0 |

All five histories/questions already had previous QA work, so this is not unseen
or independently validated performance. Their prior outcomes are not inspected
for selection or fed to any model. Prior complete comparison/quality plans bind
source, manifest, all old stage identities/request hashes and exact saved contexts.
Current preparation rebuilds and checks those bindings instead of trusting a pass
flag. The `_abs` case is the only refusal in this fifty-case cohort; one result
cannot estimate a general refusal rate. No oracle file/context is used.

## Shared bounded analysis and paired Readers

Use the unchanged `raw_vector_reranked` sources in original packed order. Validate
text, transport role, trusted dataset actor/authority and observation date back
against this exact S runtime. Analyze only these retrieved windows, not full S
histories. Existing Reference analyzer/miner, candidate state, confidence gate,
subject/source matching and quarantine accounting remain unchanged. Analyzer sees
no question, gold, public category, profile or old answer. Its source-window
analysis is not a question-conditioned extractor.

One shared extraction per case feeds both fresh Reader arms:

- `plain_proposals`: original raw evidence plus unverified gated proposals.
- `temporal_view`: same evidence/proposals plus the unchanged compact read-only
  observation/validity/advisory governance index.

Same schema, model settings and common decoder/instructions; alternate arm order
per case after analysis. The contrast includes added index length, not new
evidence. No quote, topic, relation, date or expected-answer special cases. Keep all
original sources and candidate claims. Cite raw IDs, not transient claim IDs.
Advisory conflict is not a retrieval veto or a verified semantic contradiction;
unknown effective bounds remain unknown. No consolidation action is applied.

Provided-history observation policy with original question clock and explicit
horizon, not causal/as-of replay. The update case with five later observations
must be reported separately. Do not hide that mismatch by changing dates or
filtering one arm differently. Raw source snapshots are fixed diagnostics, not
a live production Store revocation/serving test.

## Frozen budgets and evaluation

Maximum **5 analyzer + 10 Reader = 15 attempted calls**, zero Judge. Separate
durable stage budgets, new cache/receipts/run directory. Each actual dynamic
Reader request is receipted before sending; the generation rule is frozen, its
output-derived hash is not falsely described as known before extraction.
Reference output cap 4,096; Reader 1,024; json_object, temperature zero, thinking
disabled. Requested alias `deepseek-v4-flash`; returned model/finish reasons are
recorded separately, without a pinned-snapshot claim.

100KB per-call byte cap; oversize requests fail without truncation or sampling
replacement. Single attempt, stop on failure, preserve partial rows, interrupted
and invalid receipts. No automatic repair/retry or budget refund. Observe balance
before each stage and stop on empty/unavailable balance or CNY 1 observed decrease;
this is not an exact invoice/token hard cap.

No new graph, embedding, reranker, retrieval, production Store/journal write or
hosting. Existing local embedding choice is unchanged and not newly measured.
Do not restart expensive eager S-wide analysis. Old caches/answers/labels are not
rewritten; user `uv.lock` is untouched.

Report stage usage and all missing usage, actual model receipts, candidate/invalid/
quarantined counts, complete source availability and provenance, per-case Reader
results and added cost. Manual non-independent review anchors decisions to exact
answer/source quotes; legal citations alone do not prove support. Report weak
dates, wrong current values, unjustified refusal, invented fact/completion and
language drift, including null or harmful outcomes. Refusal must be judged against
the reference task, not excused merely because this context lacks an answer.
Do not silently count a missing-evidence failure as correct abstention.

Separate key-removed cache-only process must reproduce complete rows/views,
checkpoints, request identities and outputs with zero new calls. Only after that
review whether broader testing is worthwhile; do not promote a default based on
five opened cases, same-family outputs or same-context correlated arms.

## Preflight and offline verification

Runner `doppel.public-memory-transient-cohort.v1`.
Preflight `data/doppel/transient-cohort-preflight-frozen-v1.json` SHA-256:
`02f14e3b73b545ed3b545b782fb9bb95d99c540c923c2ffa2f9e6b018917fceb`.
Plan fingerprint:
`f2d0f4da2a8f520129ddaf12f57dead47a2bf378ae6c9f56f1756e3447d77ab5`.
Fresh run directory `data/doppel/transient-cohort-v1/`.
Freeze and commit before paid execution.

Six new offline tests pass: source-order/outcome-independent selection, exclusion
and missing-quota rejection, durable 5/10 stage limits, no gold/question to analysis,
source preservation between arms, key-removed fake replay, non-retried failure and
empty-balance network-before-stop protection. New runner Pyright reports zero
errors; source bounds and production temporal view use the existing tested gates.
