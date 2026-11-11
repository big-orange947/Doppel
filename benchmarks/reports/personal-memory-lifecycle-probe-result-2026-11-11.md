# Default V8 lifecycle probe: quality gaps reproduced, 2026-11-11

Frozen implementation: `9b25d0f`. [Plan](personal-memory-lifecycle-probe-plan-2026-11-11.md).
Five successful provider responses; four workflow windows completed, the final
window stopped at the evidence gate. Overall runner status is **stopped**, exit 1.
The original outputs, blocked batch, cache and budget ledger remain intact. No
retry, default change, prompt adjustment or rubric modification was made.

This is four synthetic development scenarios, not a quality score or independent
benchmark. Review below is by Codex, based on source wording, actual analyzer
output, schema diagnostics and stored records; no model Judge was used.

## Observations

| Scenario | Actual result | Diagnosis |
|---|---|---|
| New correction, then older arrival | Both opposite preferences remain current; evidence stays in separate records | Cross-batch slot alignment missing |
| Permanent home plus bounded temporary stay | Permanent home current; temporary stay retained as episode; as-of inside/outside uncertain | Occurrence preserved but no bounded residence-state view; one additional episode schema-rejected |
| Intention then cancellation | Cancelled history retained; current/planned views empty | Expected behavior observed on this sample |
| Contact ownership plus owner denial | Two schema-valid drafts, but evidence gate blocks entire batch | Incorrect role/mixed-actor evidence and a semantic attribution error; no derived fact committed |

### Slot alignment

New source `p-new`: “更正一下，我现在更喜欢深色界面，不喜欢浅色界面了。”
Old source `p-old`: “我更喜欢浅色界面。” The older message is deliberately
received after the new one without changing either observation timestamp.

The new draft uses `preference.interface-theme`, `revision_kind=correction`;
the old draft uses `preference.light-interface`, `revision_kind=assertion`.
Both have `temporal_status=current`. The current query returns both:
“我现在更喜欢深色界面，不喜欢浅色界面了。” and “我更喜欢浅色界面。”

There is no evidence loss or timestamp rewrite here. The deterministic
consolidator cannot align distinct slots. Merely swapping in the existing LLM
consolidator would not bypass this: the trusted consolidation runner explicitly
requires identical nonempty topic keys for corrections/conflicts. That gate must
not simply be removed to make this sample pass. A generic, separately validated
slot-alignment proposal is needed; no interface-theme keyword table is justified.

### Time representation and partial schema rejection

Source `s-base`: “我的长期住址在南京，这次出差也不会搬家。” Source `s-trip`:
“我已经结束这次出差了：2026年10月1日到10月10日临时住在北京，10月11日回南京。”

The current view returns “我的长期住址在南京。” and excludes the historical trip.
The trip is retained as an episode with source-bound occurrence coordinates:
2026-10-01T00:00:00Z through 2026-10-10T23:59:59Z. Its `valid_from/valid_to`
are null. Inside (October 5) and outside (October 20) **validity as-of** views
retain the same background candidates as `as_of_match=uncertain`, with explicit
validity/event-normalization warnings. These are not certified wrong current
claims. Occurrence time and continuous state validity are different concepts;
blindly copying every episode interval into state validity would be unsound.
This sample does not establish a usable bounded temporary-residence state view.

The provider emitted a third draft: “2026年10月11日，我结束出差回到南京。” Its
event coordinate has `precision=day`, start October 11 midnight and `end=null`.
The existing schema rejects it with “resolved time requires both bounds and known
precision”. Diagnostics show **3 total / 2 valid / 1 invalid**. The raw draft is
still in the provider-output cache and source text; this is derived information
loss, not deletion of the original event. Calendar-day timezone/precision remains
a separate review concern even for accepted coordinates.

### Cancellation

Source `c-plan`: “我打算报名11月的陶艺培训，目前还没报名，也没参加过。” Source
`c-cancel`: “陶艺培训不报名了，取消这个计划。我没有去上课。” The default miner
does not expose historical agent message `c-agent` to the analyzer.

The single draft says “陶艺培训计划已取消，没有报名，也没有去上课。” with
`memory_type=plan`, `revision_kind=retraction`, `temporal_status=historical`,
both owner source IDs. Current and planned views are empty; prior returns this
cancelled history. No completed attendance was created in this observation.

### Speaker/subject attribution and gate failure

Contact source `o-contact` (sender `contact-alan`): “我是阿岚，我刚买了一辆折叠自行车。”
Owner source `o-owner`: “自行车是阿岚买的，我还没有自行车，也没有买车计划。”
Agent source `o-agent` is again excluded by the default miner, not understood and
rejected by an analyzer that saw it.

The first draft says “阿岚刚买了一辆折叠自行车。” but sets `subject=contact-alan`
(an identity in the role field) and binds **both** contact and owner sources.
The second says “阿岚没有自行车，也没有买车计划。” with `subject=owner` and owner
evidence. That second text reverses the owner statement's first-person denial
into a claim about the named contact. The actor/subject evidence gate blocks the
batch (`errors=[batch_propose]`); neither derived memory is committed. Raw events
remain. No current/contact query views are produced for this blocked window.

The block demonstrates structural defense, not complete semantic safety. The
second draft's wording is wrong even though its role/evidence fields match the
owner. A validator comparing only those fields cannot prove the content's meaning.
An explicitly **post-hoc read-only counterfactual** passed these saved drafts
through the unchanged pure proposal conversion with quarantine enabled: the first
was rejected for `mixed_source_actors`, while the semantically wrong second draft
was accepted as an owner candidate proposal. No Store write/model call or default
change occurred. Artifact: `data/doppel/lifecycle-probe-v1-quarantine-counterfactual.json`.
Do not enable quarantine alone as a semantic fix or describe the default block as
proof that every wrong claim was independently recognized.

## Accounting and replay

Requested/returned model: `deepseek-flash` for all five responses, finish `stop`.
No pinned snapshot claim. All five attempts succeeded at the transport/JSON layer;
one downstream workflow was blocked. Reported usage is complete for all attempts:

| Input | Output | Total | Cached input | Cache-miss input |
|---:|---:|---:|---:|---:|
| 6,811 | 710 | **7,521** | 5,120 | 1,691 |

No Reader/Judge, embedding, graph build, real chat, Docker action or old DB reset.
Reported usage is not an independently reconciled bill.

Fresh-state cache-only reconstruction: **five hits, zero new provider attempts**.
It reproduces the same blocked final window and the same semantic projection
digest: `79a7c2eb299106bb2903739a5e2d0670955a1199198912d78179a16d39c049cb`.
This compares claims/states/selected metadata/evidence/views/analysis, not full
random IDs, complete Store bytes or raw transport timestamps.

Artifacts: `data/doppel/lifecycle-probe-v1-{preflight,live,replay,summary}.json`;
run directory `data/doppel/lifecycle-probe-v1`; original and replay SQLite state
directories `data/examples/lifecycle-probe-v1` and `…-replay`. The summary binds
artifact hashes. The frozen plan binds dataset, provider, runtime source and cap.

Seven new offline controls and 41 related checks pass. Full-repository Ruff,
changed-file formatting and new runner Pyright pass. No full-suite rerun this
round; preceding full suite 2,569 passed / 33 skipped / 3 subtests is a separate
observation. No runtime algorithm or default profile changed this round.

## Next work

Prioritize source-grounded role/content agreement and complete time coordinates,
then generic cross-batch slot alignment. Keep the existing rejected drafts, fail-
batch behavior and exact-scope/authority gates visible. New candidate methods need
fresh prospective controls across unrelated domains and phrasing, not rules for
these four cases or replay-until-pass on the same cached outputs. Any semantic
slot mapping must be an explicit reviewable proposal before correction/transition;
changing the topic-key string without that authorization is not a valid repair.
