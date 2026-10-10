# Query-time proposals: two-case pipeline and cost diagnosis

Frozen implementation: `d546b09`; starting HEAD `beeb792`.
See the [preregistered plan](public-memory-lazy-proposal-plan-2026-10-10.md).
**Six calls complete, zero failures, no retries.** One temporal answer becomes
coherent and matches the reference; the update answer was already correct.
This does not establish a general lazy-analysis gain or a complete temporal view.

## What actually ran

Use the two existing first-opened temporal/update S questions and their saved
raw-vector-reranked contexts: 10 and 13 original messages respectively. No new
retrieval, oracle context, graph, embedding, reranker, production Store writes or
Judge calls. The full S snapshot is used only to validate original sources and
question clocks; only retrieved messages enter the analyzer/Reader requests.

The actual `ReferencePersonalMemoryAnalyzer` and `PersonalMemoryMiner` operate
over these finite windows. Analyzer input is question-independent, with source
actors/IDs/dates and no gold, category, profile or old answer. Sixteen drafts,
eight per case, pass schema and evidence/subject gates. No schema-invalid,
low-confidence, duplicate or evidence-rejected drafts occur in this live run;
offline tests separately exercise quarantine. They remain **candidate proposals**.

Both Reader arms retain all original evidence in the same order, use identical
instructions/schema/settings, and may cite only original source IDs. The candidate
adds unverified proposals; it never substitutes summaries for raw evidence.
There is no consolidation, state transition, persistent memory write or graph.
This is proposal augmentation, not the entire production memory pipeline.

Requested alias `deepseek-v4-flash`; all six response receipts report
`deepseek-flash`, finish reason `stop`. No pinned-snapshot claim. Analyzer/Reader
output limits 4,096/1,024; temperature zero, json_object, thinking disabled.

## Actual answers and attribution

Manual Codex review covers all four answers. The separate bound review artifact
has five exact answer quotations and six exact source quotations, all validated.
This is **non-independent review**; quote anchoring is not an entailment proof,
official scorer or population accuracy estimate.

| Opened case | Direct raw Reader | Raw plus query-time proposals |
| --- | --- | --- |
| Device setup order (`gpt4_d9af6064`) | Starts with thermostat first, notes router's earlier date, then refuses; internally contradictory | Router first, matching reference, with original date citations |
| Current model project (`3ba21379`) | Ford F-150; correctly distinguishes the old Mustang project | Ford F-150; no additional task success |

The baseline temporal answer starts “您先设置了智能恒温器” and ends
“我无法确定哪个设备是先设置的.” It has legal citations but no coherent answer.
Do not score by matching a router word in a caveat. The candidate says
“您先设置的是新路由器” and compares the source dates consistently.

Important support caveat: the thermostat's setup is explicit; the router source
reports acquisition on January 15 and improved functioning Wi-Fi, not an explicit
installation timestamp. Ordinary functional-use inference supports router-first
and matches the benchmark reference, but the candidate's exact-date setup
explanation is stronger than the literal source. Preserve that distinction rather
than describe every derived date as a verified fact.

All four answers are Chinese despite English questions. Both arms retain the
language defect; no new Reader prompt fix is attempted here. Four structural
citation/derivation checks pass, but they do not guarantee semantic correctness.

### Why this is not yet a governed timeline

All 16 proposals have null `valid_from` and `valid_to`. The update case retains
both the old Mustang and the new F-150 in `project.current-model`, both marked
`current`. The analyzer is explicitly instructed not to consolidate old facts;
this is not proof of a new core regression. It exposes the **missing downstream
temporal interpretation stage in this diagnostic route**. The Reader answers
using the original chronology, not a fully governed temporary state view.

Some proposals concern unrelated ISP/paint/details even within a retrieved window.
The existing analyzer is source-window bounded, not question-conditioned. This
cost/utility limitation should be measured, not hidden with case-specific filters.

## Clocks and scope

The temporal case's ten observations occur after its original question timestamp
on the same day. Both arms deliberately preserve the original provided-history
evaluation semantics and question clock, declaring the observation horizon.
This is **not a causal/as-of replay test**. The update case has no observations
after the question. No dates, evidence selection or ranks were modified to make
one arm easier. Do not pool this result with strict-reference temporal metrics.

Each case has an independent exact scope and bounded read-only source window;
memory access outside the window is unavailable. Every proposal is checked back
against that window's scope/actor/evidence. Real runs have zero provenance failures;
the experiment does not validate cross-tenant production deployment.

## Measured cost

| Stage/arm | Calls | Input tokens | Output tokens | Total tokens |
| --- | ---: | ---: | ---: | ---: |
| Direct raw Reader | 2 | 12,604 | 770 | 13,374 |
| Query-time analyzer | 2 | 12,056 | 1,447 | 13,503 |
| Reader with proposals | 2 | 15,262 | 647 | 15,909 |
| All experiment calls | 6 | 39,922 | 2,864 | 42,786 |

Candidate path includes analyzer plus its Reader: **29,412 tokens**, versus
13,374 direct, approximately **2.20x**, or 16,038 extra tokens. Candidate Reader
input alone increases by 2,658 tokens, 21.09%. Its two serialized request sizes
are 30,662/32,353 bytes versus baseline 26,662/28,141. Every request fits the
preregistered 100KB cap; none is silently truncated.

All six calls report complete usage. Provider cached input totals 16,000 tokens;
cache-miss input totals 23,922; reported reasoning tokens zero. These are provider
token counters, not local cache bypasses. Live local cache hits zero.
Immediate balance is CNY 4.94 before/after, **not proof of zero cost** or exclusive
settled billing. No hosting purchases. Two opened short windows cannot project
all 500 questions' cost or the competition bill; no wall-clock latency claim.

## Replay, hashes and regression

Separate child-process replay with `DEEPSEEK_API_KEY` removed completes all
two analyzer/four Reader cache hits, zero misses, zero new calls. Frozen plans,
answer rows, proposals, checkpoints and request hashes match live exactly.
Durable attempts remain 2/4. Returned-model receipts remain in the fresh run
directory; no API key, authorization headers or raw HTTP envelope is persisted.

Artifacts are ignored local files, not an extra tracked dataset release:

| Artifact | SHA-256 |
| --- | --- |
| Frozen preflight file | `7c5046afd51749dea8a9429870f7554dc58230bed3f7fe4b87cfdd6c6eb2b4da` |
| Plan fingerprint | `bbcfac715887602617b60543456ddb00d6a8021908604cac396caeb80f45d7fe` |
| Live file | `76220e823d707cb9a96f72c9a5eb71910ecc130cb57ffd29d23496e227b4167b` |
| Canonical live review binding | `68d9938bf39424ecc152040e9ce2094c5faaa886f600c36ddc16b32054f58c47` |
| Key-removed replay file | `6cb2a4112aab00ea6b66f6d9463487d8efdc6195b6f41b639af6c037d0ca5bb7` |

Paths: `data/doppel/lazy-proposal-{preflight-frozen,live,replay-no-key}-v1.json`,
`lazy-proposal-manual-review-v1.json`, `lazy-proposal-review-validation-v1.json`,
and `lazy-proposal-diagnostic-v1/`. Earlier unfrozen preflight is retained, not
used for paid execution. Old caches/answers/databases/journals remain untouched;
the user's existing `uv.lock` change remains unstaged. No Docker/GPU work.

Validation: **15 new tests**, 34 passed with representation tests; full regression
**1,725 passed, 33 skipped, 3 subtests passed**, with one existing optional
Graphiti/Pydantic deprecation warning. Repository Ruff and new-runner Pyright pass.

## Decision

Keep the route benchmark-only. This result is consistent with temporary
structuring helping a particular Reader error, but one output per opened case
does not isolate analyzer benefit from model variability or extra context length.
There is no measured retrieval recall gain, complete LongMemEval score or AML score.

Next, preserve source observation clocks directly with the temporary interpretation
and reuse existing generic governance/query capabilities to represent old/new
values without automatic newest-wins. Missing effective intervals and unresolved
conflicts must remain explicit; do not guess dates or promote candidate summaries.
Then preregister a modest source-order expansion across temporal/update cases,
including a no-answer control, before judging whether the extra calls pay off.
Keep raw sources available, separate causal from provided-history tests, and do
not resume S-wide eager analysis. Competition lazy mode does not replace the
public framework's persistent analysis/governance pipeline.
