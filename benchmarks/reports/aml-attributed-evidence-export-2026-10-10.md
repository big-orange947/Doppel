# Attributed AML evidence export: offline implementation, not a Reader fix

Starting implementation: `b7bac92` on master. Decision: prioritize the participant's
Search evidence handoff over further local Reader policy tuning. No production
retrieval algorithm, planner, Reader prompt or expected answer is changed.

## Why this boundary

The [official AML README](https://github.com/AML-memory/agent-memory-leaderboard)
assigns Add/Search to participants and Answer/evaluation to the platform. The
[API guide](https://agentmemoryleaderboard.ai/api-guide) says `content` is passed
to Answer and extra fields such as `metadata` are ignored. Internal attribution
is insufficient unless it survives into the actual declared Search content.

Existing `AttributedContextRetriever` already carries role/actor/authority and
authoritative raw text. Existing local Reader inputs already carried role and
authority and nevertheless exhibited speaker inversion. This work therefore does
not claim that missing roles explain all earlier failures or that more labels
guarantee a semantic fix. It closes a transport/composition gap.

## Implementation and scope

- `integrations/aml/evidence.py`: versioned compact JSON content for raw historical
  snippets and existing personal-memory query hits. Original text is stored as a
  reversible JSON string, not paraphrased, shortened or rewritten into third person.
- `AttributedContextRetriever.search_evidence`: opt-in search -> attributed export
  route. The normal `search` method and candidate/reranking logic are untouched.
- Historical actor identity comes from the host binding, never inferred from
  transport `user`/`assistant` alone. Embedded multi-speaker text remains original;
  unresolved speaker identities remain unresolved. An agent source is explicitly
  `historical_assistant`, not the current answering model.
- Personal subject and source actor are separate. Stored interpretation and all
  evidence links are exported, including planned/unknown temporal status and
  observation versus validity times. No completion or current-state inference.
- Lifecycle confirmed is not a truth label. Agent-output material is not rewritten
  into an owner fact. This exporter does not decide whether an item answers the
  question or replace the query engine's evidence-eligibility checks.
- Scope, Store snapshot, source identity/text/role/authority/time, duplicate IDs,
  revocation and asynchronous source changes are checked before return. Arbitrary
  Store/resolver errors are redacted; cancellation propagates. Invalid batches
  fail rather than being silently filtered, reordered or padded.

Current memory-source composition supports exact-scope, homogeneous source
actor/authority records with complete miner evidence metadata and resolvable raw
sources. Cross-scope promoted memories, heterogeneous summaries, manual notes and
attachment-only evidence require an explicit later policy. No cross-record atomic
snapshot or external HTTP deployment is claimed.

## Offline evidence and overhead

Tests use real temporary SQLite ingestion/Store reads and the existing retriever,
scripted candidates and AML boundary serialization. They do not call models,
download weights, open Docker or touch personal databases/journals/caches.

An illustrative InMemory export measurement used this 50-byte ASCII source:

> I suggested trying rowing on a stationary machine.

With generated memory ID, explicit demo event/message/session IDs and source clock,
the compact `content` was **445 UTF-8 bytes**, an additional **395 bytes**. Parsing
the content recovers the original source string exactly. This is one short example,
not an average over a corpus, a latency benchmark or a tokenizer measurement.
No token estimate or zero-cost inference claim is made. Identity lengths, escaped
characters and multiple linked sources change overhead; these fields consume the
downstream context budget and must be accounted for before deployment.

The tests establish content/identity preservation, rank/score stability and scope
checks, not model comprehension or resistance to prompt injection.

Final verification on the completed implementation:

- New exporter tests: **33 passed**.
- Exporter + AML boundary + raw context baseline/reranker: **81 passed**.
- Full regression: **1,691 passed, 33 skipped, 3 subtests passed**, 178.80 seconds.
  One existing Graphiti/Pydantic class-config deprecation warning remains; skipped
  backend-dependent tests are not claimed as live service verification.
- Whole-repository Ruff check and changed-Python formatting check pass.
- Pyright on exporter, context integration and new tests: **0 errors**.
- Provider calls: **0**. No credentials read, Docker/GPU action, model download,
  production database/journal/index mutation or old-answer/cache rewrite.
- `uv.lock` remains the user's pre-existing modification and is not staged.

This is an implementation result, not a formal AML smoke run. No new recall,
faithfulness, speaker-attribution accuracy or LongMemEval score is reported.

## Next bounded experiment (not executed by this offline implementation)

Before any paid run, freeze a separate plan, implementation/configuration hashes,
input hashes, model identity, call ceiling and independent cache/ledger identity.
Use a small fixed diagnostic set; no reserved/blind cases or adaptive selection.

Compare one source-evidence baseline representation with the new attributed
content, holding source selection, ordering, time information, question, response
schema and answer instructions constant. Declare the exact baseline serialization:
do not erase its existing role labels and claim a win over the current system.
Use source IDs for citation binding in both arms. If representation requires
different decoder instructions, report that as a confound rather than an isolated
actor-label effect.

Measure speaker/recipient attribution first; report plan-to-fact errors, answer
language and abstention consistency separately. Do not change rubrics after seeing
answers. Report input tokens and payload bytes, not just correctness. Preserve
failures; key-free replay must reproduce outputs without new calls. DeepSeek Flash
is a local diagnostic, not the official AML Answer model or a competition score.

The already rejected grounded Reader V2 candidate remains rejected; old responses,
scores, caches and controls are not rewritten. No broad Reader state-machine or
abstention classifier is introduced here. After this handoff diagnostic, return to
bounded lazy analyzer/retrieval tests rather than repeated prompt-only tuning.
