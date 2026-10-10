# Read-only transient temporal view: no new task success in two opened cases

Frozen implementation: `aaad8fd`; starting HEAD `4741162`.
[Preregistered plan](public-memory-transient-view-plan-2026-10-10.md).
**Four Reader calls complete, zero failures/retries, zero new analyzer/Judge calls.**
Both fresh arms give coherent reference-matching answers to both questions under
non-independent manual review. No additional task success or recall gain is shown.

## Framework change, distinct from the experiment

Add opt-in `TransientMemoryViewBuilder` and its source/claim/view/error types.
The builder validates exact-scope candidate proposal provenance and exposes
original observation spans separately from explicit effective dates. Missing
validity stays unknown; a later observation does not supply a fact's start/end.
Plans do not become completed events. All claims remain present and candidates.

The existing pure `DeterministicMemoryConsolidator` attaches unapplied advisory
decisions, without Store/model access, canonical writes, state changes or source
removal. Suggestions are not independently verified semantic conclusions.
Host authorization and source/Store revalidation remain external responsibilities;
messages lack a scope credential, so supplying an analysis scope is not proof of
permission. See [the API contract](../../docs/transient-memory-view.md).

Default availability horizon equals reference time; unavailable observations fail
rather than silently disappear. An explicit later horizon supports retrospective
provided-history diagnostics, with affected claims marked. It is not causal replay.
No query-engine rankings, ingestion defaults, persistent analysis or Reader default
policies change. New root API names are provisional, not stable or released as 1.0.

## Actual input and Reader contrast

Reconstruct the exact prior analyzer requests and replay their existing completed
outputs through real analyzer/miner gates, without a provider or parent-cache
mutation. All 16 proposals/checkpoints match the parent. Building the view uses
no model calls. Original S raw evidence and proposal content/order stay identical
between arms. No oracle context, new retrieval, graph, embeddings or reranker.

Fresh `plain_proposals` and `temporal_view` Readers share schema/config/instructions
including a common decoder. Candidate adds a compact temporal/governance index,
not new evidence. Length is a confound. Do not compare fresh baseline results with
older responses as a clean regression: the common decoder changed. Cite original
raw IDs only, never transient claim IDs. Four structural checks and 18 citations
are legal; arithmetic/entailment is not thereby independently proved.

Requested alias `deepseek-v4-flash`; all four actual responses report
`deepseek-flash`, finish reason `stop`. No pinned snapshot claim. json_object,
thinking disabled, temperature zero, max output 1,024.

## Reviewed outcomes

Four manual decisions bind to the canonical result and exact source/answer quotes.
Six answer and six source quotes validate. Review is **Codex/non-independent**;
quote anchoring verifies provenance, not semantic truth. No automated Judge is run.

| Opened case | Plain proposals | Temporal view |
| --- | --- | --- |
| Device setup order | Router first, coherent and reference-matching | Router first; also explains observations are retrospective |
| Current vehicle model | Ford F-150, coherent and reference-matching | Ford F-150; reasons from explicit project switch despite advisory conflict |

The temporal-view answer says: “这些日期来自在问题参考时间之后观察到的陈述”.
That matches the stored source clocks: the ten supplied observations occur later
on the question's day. It adds an availability caveat, not a new correct answer or
proof the information was available at the original question time.

Both temporal answers still compare router acquisition to thermostat setup. The
router's functioning improved Wi-Fi supports ordinary setup inference and the
reference answer, but acquisition is not an explicit installation timestamp.
Keep exact-date support ambiguity visible; do not declare complete grounding.

The update view suggests a potential slot conflict between old Mustang and new
F-150 `current` proposals, with no canonical source. Reader does not automatically
refuse: it uses original text's explicit switch and chronology to answer F-150.
This one observation supports keeping governance advisory rather than a recall
veto; it does not validate all conflict handling. Both old/new claims remain visible,
with null validity bounds, no forced historical status and no applied correction.

All four outputs still answer English questions in Chinese. Abstention flags are
false and consistent with substantive answers. There is no language fix or general
accuracy claim. All 16 proposals remain without explicit effective intervals; this
view exposes that limitation rather than solving semantic date extraction.

## Tokens and accounting

| Arm | Calls | Input tokens | Output tokens | Total |
| --- | ---: | ---: | ---: | ---: |
| Plain proposals | 2 | 15,502 | 773 | 16,275 |
| Temporal view | 2 | 18,472 | 676 | 19,148 |
| Experiment | 4 | 33,974 | 1,449 | 35,423 |

Temporal index adds **2,970 input tokens, 19.16%**. Total difference 2,873 tokens,
17.65%, includes output variability and is not isolated serialization cost.
Request bytes increase 3,571/3,829 per case. Every request fits the 100KB bound;
no truncation. No new analyzer cost is hidden: previously paid parent extractions
are reused, not counted as free if this route is deployed on a new query.

All four calls report complete usage; provider cached input 17,408 and cache-miss
input 16,566 tokens; reported reasoning zero. Live local disk-cache hits zero.
Immediate balance CNY 4.90 before/after does not prove zero or exclusively attributed
settled charges. No hosting, Docker or GPU work. No latency or large-scale forecast.

## Replay, provenance and verification

Separate process with `DEEPSEEK_API_KEY` removed: four local-cache hits, zero misses
or new calls; plan, complete views, result rows, request/usage/model metadata match
live. Durable attempts remain four. Cached analysis outputs, old reports and parent
receipts are only read. The user's `uv.lock` remains untouched/unstaged.

| Artifact | SHA-256 |
| --- | --- |
| Frozen preflight | `03e8efc10a3384b52206a5645706537a962a88560ca1e20b8be7352a8b639dc3` |
| Plan fingerprint | `19e782fb619ea4cbf18fb31f13fe980c33eeda2d777de7a6a53d73f29d93356f` |
| Live file | `6599317ef78fb5cd4e122a8fe960778e1ef024e0b69a9a1e56bf51fa6fa163cb` |
| Canonical live review binding | `89e8e1324e47cc1bd203d0986f2bc1d83516619cbf45f7140c5d49f7a63b4d24` |
| Key-removed replay | `1a98c539573365ff036396180780b674dc0ed8a2af7d92d3ad87e72bfef40687` |

Ignored local artifact paths: `data/doppel/transient-view-{preflight-frozen,live,
replay-no-key,manual-review,review-validation}-v1.json`, plus the separate
`transient-view-diagnostic-v1/` receipts/cache/ledger. No key/headers/raw HTTP
envelope persists.

New component/harness tests: **31 passed**; with public API compatibility tests,
**36 passed**. Repository Ruff and new-file Pyright pass. First full regression
found a missing public-export manifest registration (1 failure, 1,755 passed,
33 skipped). The explicit provisional manifest entries and new model-field
snapshots are now registered without changing any old entries or loosening tests.
Final full regression: **1,756 passed, 33 skipped, 3 subtests passed** (226.53s).
One existing optional Graphiti/Pydantic class-config deprecation warning remains.
The paid experiment's frozen source and requests did not change during this
manifest/documentation registration; no new provider calls or labels were added.

## Decision and next work

Keep the optional builder as a read-only provisional utility, **not a new retrieval
default**. It adds inspectable time/provenance/governance structure without pretending
unknown intervals are known. The two-case Reader contrast is a null task-success
result with additional input cost; do not tune these cases or keep rerunning them.

Next preregister a modest source-order temporal/update/no-answer expansion with
fixed budgets and unchanged raw evidence. Include genuine changes, unresolved
claims, plans, explicit intervals and retrospective observations, without selecting
by prior success. Measure whether the view helps/hurts answers and time boundaries
across cases before any default promotion. No full S eager extraction restart,
official/independent LongMemEval score or AML score follows from this experiment.
