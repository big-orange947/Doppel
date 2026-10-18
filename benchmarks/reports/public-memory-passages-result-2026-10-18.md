# Opt-in passages implemented; first answer comparison shows no accuracy gain

Generic lossless spans and guarded passage retrieval are implemented, tested and
kept opt-in. A fixed diagnostic on three previously opened failures completed:
whole-message and passage contexts both receive **2/3 provisional task grades**.
The implementation makes originals traceable and long messages manageable; this
experiment does **not** demonstrate an answer-accuracy improvement.

## Delivered capability

- `doppel_memory.passages`: model/Store-independent Unicode-code-point spans,
 1200-character windows /160 overlap by default, exact original offsets/text.
- Repository reference `integrations/aml/passages.py`: authorized raw sources,
  round-robin bounded candidate generation, optional existing `Reranker`, unique
  passage IDs, original memory/event/hash/role/authority/time retained.
- Pre/post-ordering Store/source/state checks and `resolve_original`; changed or
  revoked originals are rejected, foreign or invented reranker candidates fail
  closed, and reranker-supplied text/authority is never trusted.
- No fragments are persisted, no migrations or default recall changes. Historical
  assistant content stays `agent_output`, not owner fact. The core utility ships
  in the wheel; the guarded AML reference remains a repository integration.

See [usage and boundaries](../../docs/attributed-passages.md). This is not a new
Agent context manager or automatic cross-scope authorization layer.

## Fixed experiment

Use exactly the saved hybrid-reranked top20 source messages from three opened
cases in the31–40 run. No embedding/vector/lexical search is rerun or expanded.
Read-only corpus hashes match the original receipts before and after; whole-message
fit contexts reproduce exactly. Span generation/ranking/packing receives no gold.
Both arms use the same24,000-byte JSON budget, at most20 items and whole-item fit.
Existing Reader instructions/schema are unchanged; original/excerpt metadata is
included in both arms' input data. Paid task judge sees question/reference/answer,
not profile, context, old grades or annotation-based recall.

| Opened case / task | Whole items / bytes | Passage items / bytes | Whole task | Passage task |
| --- | ---: | ---: | --- | --- |
| `e9327a54` / earlier giant-milkshake suggestion | 19 /22475 | 19 /23997 | Correct | Correct |
| `gpt4_ec93e27f` / most recent mentioned transport | 10 /23549 | 15 /23401 | Correct | Correct |
| `gpt4_2f8be40d` / weddings attended this year | 3 /23631 | 13 /23607 | Incorrect refusal | Incorrect refusal |

Three additional local neural rerank calls score134 passage pairs (28/44/62).
No candidate cap was hit; zero tokenizer truncations, longest pair357 tokens.
This additional local compute is accounted for, not called a free ablation.
More items/shorter sources do not constitute a quality score. No source-turn ID
match is used as fragment answer-support recall; that field remains undefined.

## Inspecting the actual evidence

The dessert answers both identify The Sugar Factory, explicitly attributing it to
the earlier assistant recommendation rather than asserting an owner-confirmed visit.
The cited original/fragment contains the shop, Icon Park and giant milkshakes.
This demonstrates usable assistant-source attribution in this one diagnostic,
not general hallucination prevention.

Both transport answers cite owner statements: the dated March3 train ride and
the earlier February27 bus usage. Those actual texts are present in both contexts.
The earlier packing audit lost the *annotated* turns for this profile, yet these
other sufficient original statements survived. This directly illustrates that
annotation coverage is incomplete as a proxy for answer sufficiency. Do not
retroactively alter annotation scores, and do not optimize solely for them.
The whole-message transport answer is Chinese for an English question; preserve
this Reader language drift, do not label the entire pipeline clean.

The wedding source history has three annotated owner statements at session/turn
6/0,9/0,41/0. Only9/0 and41/0 are in the saved message top20;6/0 is already absent,
so downstream splitting cannot recover a complete three-event history. Moreover,
the passage output contains13 assistant passages and zero owner passages, dropping
the two relevant owner statements that were available. The whole-message context
instead contains an irrelevant16,782-byte owner article plus two assistant replies.
Both Readers lack sufficient supplied evidence for the expected count and refuse.
The passage Reader correctly treats an assistant's wedding characterization as
assistant output, not an owner attendance log. That faithful limitation is still
incorrect for the benchmark's answerable counting task.

Thus there are **two ranking losses**, not merely a long-message formatting issue:
an upstream source window excludes one needed owner event, and content-only
fragment relevance then favours topical advice over the available owner facts.
No entity/wedding/count-specific rule or role-only filtering was added. Dropping
all assistant content would break the correctly answered dessert task.

## Accounting and validation

- Six Reader requests plus six provisional task-judge requests, all successful,
  zero retries/failures and complete provider usage for all12 calls.
- Reader46020 input +1240 output =47260 tokens; judge2846 input +229 output =3075.
  Total **50335 tokens** (48866 input /1469 output), including5888 cached input.
  Attempt/request-byte limits enforced. Output caps are per request; no aggregate
  token hard cap or exact currency-billing guarantee is claimed.
- Citation-ID/derivation structural checks pass6/6. Seven citations across the six
  outputs are source-resolvable. IDs being legal is not proof of semantic support;
  the direct evidence inspection above is not a separate blinded entailment audit.
- Source-only preparation used no paid LLM; graph calls0, source/index writes0,
  no paid judge calibration or additional experiments after the frozen12 calls.
- Forty-two new offline tests pass. Full implementation suite: **1947 passed,
  33 skipped, three subtests passed**, one existing Graphiti/Pydantic warning.
  A later fail-closed type-narrowing guard in the diagnostic wrapper separately
  passes its4 tests; new implementation/wrapper Pyright and repository Ruff pass.
- Existing data/graph and user `uv.lock` preserved. No exact cache-only replay of
  this new QA run is claimed. No stable idle-GPU latency benchmark was performed.

## Decision and next priority

Keep passage handoff as an explicit capability, not a promoted default or claimed
performance win. Stop changing it on these three opened cases. Next prioritize
generic source-aware ranking/diversity: original speaker/authority/time must be
available to the relevance strategy, while both legitimate owner and assistant
channels remain eligible. The current reference BGE adapter scores text only;
the passage API already supplies actor/authority to a host-supplied reranker.
Do not impose an owner-only filter or benchmark keyword rules.

Any new ranking policy needs a frozen comparison on the untouched continuation
before generalization claims. A large graph build, another scoring-model redesign
or counting source IDs as answers would not resolve the measured failure.
This is three opened public diagnostics, not a fresh3/3 gate, LongMemEval500,
official AML, independent validation or release readiness.

## Bindings

Implementation/context execution6cd3c30; QA freeze/execution5ea30dc. See
[pre-execution plan](public-memory-passages-plan-2026-10-18.md).
Ignored local artifacts:

| Artifact | SHA-256 |
| --- | --- |
| Context preflight | `88c2026f6f50583d24d507df8f83a419c331ff4e90f59b244c3f0a688c8c5a2a` |
| `passage-diagnostic-context-live-v1.json` | `1a868e90f303e76a3555563bde610f10abe67b4a7a53cd1b415180ad9e223b7d` |
| QA preflight | `ebfadd661b3c0169959e7d36ae71cbe549ed11c9d4eb07d54b311b2f06da43cc` |
| `passage-diagnostic-qa-live-v1.json` | `4e8c09cce4098416c0783dfbbecc6c1ba1ed4d1be27f73208e12dcb85d09029c` |
