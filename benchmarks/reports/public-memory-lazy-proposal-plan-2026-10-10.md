# Frozen query-time proposal diagnosis: two opened raw contexts

Starting HEAD: `beeb792`. This is a small pipeline/cost diagnosis, not a new
retrieval algorithm, official LongMemEval evaluation, independent blind test or
AML score. Leave persistent analysis and the public SDK defaults unchanged.

## Cases and exact contrast

Select the existing first-opened temporal-reasoning (`gpt4_d9af6064`) and
knowledge-update (`3ba21379`) cases from the previous response-policy preparation.
Use the saved S `raw_vector_reranked` contexts, not gold-selected oracle sessions.
Validate saved contexts against their original full S sources. The oracle file is
bound only to reproduce the existing selection; oracle text is not sent to models.
Prior reserved partitions remain excluded; selection does not inspect outcomes.

Two arms share the question, question clock, raw sources, source order, Reader
schema/config and common instructions:

- `recall_only`: original raw evidence, empty optional proposal field.
- `lazy_proposals`: all the same raw evidence plus unverified temporary proposals
  from `ReferencePersonalMemoryAnalyzer` through `PersonalMemoryMiner` gates.

Analyzer input is the retrieved evidence window, oldest first; it receives no
question, reference answer, scoring labels, old answer, category or profile.
Question-time demand limits which sources are analyzed, but this existing analyzer
is not a question-conditioned extractor. This distinction is part of the result.
Both historical owner and agent messages remain. Explicit dataset transport
bindings are checked against actor/authority; no general role-only identity policy
is added to the public framework.

Use conversation-target candidate proposals, subject/source matching, confidence
0.75, quarantine with rejected-draft accounting and complete bounded-window checks.
Do not consolidate, write Store records, add graph edges or promote proposals into
confirmed facts. Reader cites original raw IDs only. Proposal IDs are not a new
evidence source. Unknown, mixed-actor or wrong-subject evidence is quarantined,
not repaired; original raw context is never discarded with rejected proposals.

This is **proposal augmentation**, not a complete temporary timeline/consolidation
engine. It cannot discover evidence missing from the fixed candidate set. Extra
context length and one additional model call are part of the contrast, not isolated
causal effects. No arithmetic/domain/topic-specific correction is allowed.

## Clock policy

The temporal case has 10/10 retrieved observations later on the same day than its
original question timestamp. Preserve them in both arms under explicit
`provided-history-v1` semantics, retaining the original question clock and adding
the available observation horizon. This is **not strict causal/as-of replay**.
The update case has zero retrieved observations after its question clock.
Do not silently change dates, filter one arm differently or describe future
observations as a prediction. Observation time remains distinct from effective time.

## Bounds and receipts

Maximum **2 analyzer + 4 Reader = 6 attempted provider calls**, zero Judge. Separate
durable immutable stage budgets, fresh caches/receipts, no automatic retries or
repair. Interrupted/failed stages are retained and cannot be silently rebilled.
Analyzer output cap 4,096 tokens; Reader cap 1,024; json_object, temperature zero,
thinking disabled; requested DeepSeek alias `deepseek-v4-flash`, actual response
model recorded separately. No pinned-snapshot claim.

Analyzer request sizes: 24,305 and 25,949 serialized bytes. Both model stages cap
each canonical request at 100KB. Dynamic lazy Reader requests fail rather than
truncate when over bound. Their generation rule is preregistered; their actual
hashes become available only after analysis and are receipted before the calls.
These byte limits are not token counts or an exact monetary cap.

Observe CNY balance before each stage; stop when empty, observation fails or the
observed decline reaches CNY 1. This is post-spend observation, not an invoice
guarantee. Do not purchase hosting or restart expensive S-wide eager analysis.

Execution order: temporal baseline → analysis → candidate; update analysis →
candidate → baseline. A separate key-removed process must replay all outputs,
proposal diagnostics and request identities with zero new calls. Record per-stage
usage and missing usage; provider caching is distinct from local cache replay.

Semantic review is manual/non-independent: compare actual answers to the original
source passages and reference without changing rubrics or exposing labels to
Reader/analyzer. Report any loss, null result, contradictory proposal or unsupported
time interpretation. Do not turn two cases into an accuracy/recall claim.

## Bound preflight and validation

Runner: `doppel.public-memory-query-time-proposal-diagnostic.v1`.
Preflight: `data/doppel/lazy-proposal-preflight-frozen-v1.json`.
SHA-256: `7c5046afd51749dea8a9429870f7554dc58230bed3f7fe4b87cfdd6c6eb2b4da`.
Plan fingerprint: `bbcfac715887602617b60543456ddb00d6a8021908604cac396caeb80f45d7fe`.
Fresh run directory: `data/doppel/lazy-proposal-diagnostic-v1`.
Exact source/config/runtime/request bindings are in the immutable preflight.

Offline: **15 new tests**, including real miner quarantine gates, source/actor/time
binding rejection, request gold/question separation, raw-evidence preservation,
stage budgets, fail-stop without retry and key-removed fake replay. Together with
the preceding representation tests, **34 passed**. Repository Ruff passes; new
runner Pyright reports zero errors. Freeze and commit before paid execution.
