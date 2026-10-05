# Blind corpus V3: completed review and diagnostic audit

Date: 2026-10-05

Status: complete first V3 review, rejected; compilation and retrieval remain closed.
This is an assistant's diagnostic examination of the reported findings and nearby
contracts, not an independent second-model review or an acceptance override.

## Bound artifacts and actual usage

Implementation commit: `e9da148326a99d5a6e4fbadbd674cdb4b7f6c3ce`.

Host manifest fingerprint:
`70fcb5c2fcbe3b2da7ec89e889b78066394a46027ab27e354ade7e1e3dcf0000`.

Authored surface artifact SHA-256:
`d000d2a4ec413a45700b848074e3ec91a2f5f7b0dc043a94f6eeb4394823609e`.

Complete rejected review SHA-256:
`e413f3880d639f52a370e67b707c23092deb438de920a7a23ee6c03ac7c58d3d`.

V3 authoring retained 33 seed batches, completed the remaining 15 with 21 new
calls, and finished all 48 batches. Five responses repeated same-owner memory
text; one response failed surface validation. No attempt ceiling was raised.
Reported usage was 212,683 input + 108,142 output = 320,825 tokens.

The complete independent review used 48 calls and reported 477,812 input +
33,436 output = 511,248 tokens. V3 alone therefore used 69 calls and 832,073
tokens, with zero reported reasoning tokens. Prior authoring/review usage is
separate; it is not silently included in these V3 figures. This diagnostic audit
made zero provider calls and performed no automatic surface rewrite.

## Coverage and hard boundary

The authored hash, manifest fingerprint, exact batch identities, owner references,
reviewed-key fingerprints, issue-key validity and counts were checked locally.
All 48 batches and 5,304 owner-local surface slots are covered: 4,608 memories,
456 entity names and 240 query slots. Each draft still passes structural projection.

The review reports 23 findings on 23 distinct owner-local slots, in 11 core batches.
All 24 tail batches have zero findings. Categories are 10 `answer_leak`,
10 `relation_mismatch` and three `temporal_mismatch` findings. Thirty-seven batches
have no reported findings; that is not proof of semantic correctness.

The compile validator was explicitly checked against this rejected review and
raises `compile requires an accepted first semantic review`. No corpus was
compiled, no retrieval profile was run, and `accepted=false` remains untouched.
The existing review/compiler tests also pass (22 tests). An offline table check
verifies that the 23 diagnostic rows exactly cover the original reported
owner/slot/code triples, without omissions or duplicate rows.

Surface diversity is also distinct from slot count: 4,567 unique memory strings,
231 unique non-empty edge facts, 254 unique entity names and 144 unique query texts.
Cross-owner repetition is permitted and adds isolation pressure, but 240 query
slots must not be advertised as 240 independently worded questions or proof of
broad natural-language generalization.

## Finding-by-finding diagnostic assessment

The categories below assess the reported reason, not every possible defect in each
slot. They must not be consumed as a machine acceptance policy. Opaque owner/slot
references are used instead of publishing the blind surface text or private answers.

| Owner | Surface key | Reported code | Diagnostic assessment | Reason |
| --- | --- | --- | --- | --- |
| 05 | memory-temporary-residence | temporal_mismatch | Contract ambiguity | Ending "before April 1" does not independently fix the final day; the fixed host interval requires unambiguous half-open boundary wording. |
| 06 | query-no-answer | answer_leak | Reviewer false positive | Asking for a buyer does not supply a buyer or imply the Store has that fact. An unanswered relation question is a legitimate test. |
| 08 | memory-competing-first | relation_mismatch | Data-coherence defect | Same animal is described as bought from one party and adopted from another without actors or a transfer chain that makes both claims coherent. |
| 08 | memory-stale-route | relation_mismatch | Contract/lifecycle ambiguity | A previous adoption and subsequent adoption can coexist, but "the adoption relation ended" does not describe return/re-adoption or who acted. |
| 09 | memory-temporary-residence | temporal_mismatch | Contract ambiguity | The review's present-versus-past reasoning is weak, but the underlying end-boundary wording is still imprecise. |
| 11 | query-subject-correction | answer_leak | Reviewer false positive | Asking about a corrected claim names its topic without asserting the positive or negative answer. |
| 11 | query-no-answer | answer_leak | Reviewer false positive | Missing purchase evidence is not an answer embedded in the question. |
| 12 | query-subject-correction | answer_leak | Reviewer false positive | A whether-question identifies a topic, not its truth value. Naming the topic is not the reported answer leak. |
| 12 | query-no-answer | answer_leak | Reviewer false positive | The question asks for a missing relation; it neither invents a buyer nor announces answerability. |
| 14 | query-no-answer | answer_leak | Reviewer false positive | The same distinction between asking and asserting applies. |
| 16 | memory-temporary-residence | temporal_mismatch | Contract ambiguity | An event that is over now can be queried historically; nevertheless the exact end boundary must be stated clearly. |
| 18 | memory-competing-first | relation_mismatch | Data-coherence defect | An ordinary authored book is presented as formally signed/issued; broad `document` typing did not constrain the subtype or issuer role. |
| 18 | memory-stale-route | relation_mismatch | Data-coherence defect | A passport is said to have been issued by the same publishing organization; its competent-issuer role is not supplied. |
| 18 | query-no-answer | answer_leak | Reviewer false positive | The cited query does not disclose a buyer or claim its answer is unknown; the report supplies no actual leaked answer. |
| 22 | query-subject-correction | answer_leak | Reviewer false positive | Mentioning the allergen in a whether-question does not give the allergy status. |
| 22 | query-no-answer | answer_leak | Reviewer false positive | A query about an unrecorded relation is permitted. |
| 24 | memory-one-hop | relation_mismatch | Data-coherence defect | Sale and adoption claims about the same animal need explicit actors/transfer context; present text does not establish that chain. |
| 24 | memory-competing-first | relation_mismatch | Data-coherence defect | The paired adoption claim has the same unexplained acquisition-source conflict. |
| 24 | memory-two-hop-first | relation_mismatch | Contract/lifecycle ambiguity | Distinct old and current adoption sources require a coherent return/re-adoption history, not a blanket ban on temporal changes. |
| 24 | memory-stale-route | relation_mismatch | Contract/lifecycle ambiguity | Historical termination alone under-specifies the acquisition sequence. |
| 24 | memory-no-answer-related | relation_mismatch | Reviewer false positive | Current custody by B and explicitly ended custody by A are compatible. The current surface explicitly says "now". |
| 24 | memory-no-answer-stale | relation_mismatch | Reviewer false positive | This surface explicitly states past custody and that it ended; a different current holder is not a contradiction. |
| 24 | query-no-answer | answer_leak | Reviewer false positive | Demanding that the query announce its unknown answer directly conflicts with the frozen query contract. |

The diagnostic breakdown is 12 reviewer false positives, five data-coherence
findings and six contract/lifecycle ambiguities. That is an explanatory breakdown
of the 23 flags, NOT "12 failures waived" or "11 real failures remaining" in a
revised gate. Some findings refer to the same underlying defect.

## False negatives found outside the reported findings

Whole-family inspection also found ordinary-book/issuance wording in owners 02
and 10, whose corresponding slots were not flagged. Owner 16 explicitly has
coexisting animal sale/adoption source records without a clear actor/transfer chain,
although its review did not report those relation slots. The same host relation
families occur in owners 02/10/18 (`ISSUED_BY`) and 08/16/24 (`ADOPTED_FROM`).

Consequently a repair restricted to the 23 flagged slots would leave known issues
behind. Passing LLM review is not a reliable substitute for coherent host contracts.
These are corpus and review-system findings, not measured Doppel retrieval defects.

## Next bounded work, before another paid run

1. Calibrate the reviewer on small, separate generic controls: an unknown relation
   question versus an invented answer; a whether-question versus a stated answer;
   non-overlapping old/current custody versus overlapping contradictory custody;
   and half-open intervals with an exact historical query date. Record both false
   positives and missed defects. Do not infer query answerability from Store coverage.
2. Audit contracts by relation family, including unflagged owners. Broad entity
   types alone do not ensure an issuable document, a competent issuer, or a coherent
   acquisition chain. Describe issuer roles and adoption/transfer/reissue lifecycles
   in natural briefs without changing scope, gold evidence, route shape or labels.
3. Express the existing residency interval precisely: entry on February 1, occupancy
   through March 31, no temporary residency from April 1 onward; align the question
   to its existing March 15 as-of date. Apply the temporal-precision rule consistently,
   not just to the three flagged owners. Preserve the existing host timestamps.
4. Freeze a repair inventory and new contract version before authoring. Prefer
   bounded surface-slot edits over regenerating 96-memory core batches. Retain
   untouched strings, parent hashes and original rejected reports; validate complete
   coverage, endpoint consistency and owner-local uniqueness after edits. No automatic
   generation/review loop until acceptance and no selection by retrieval scores.
5. Review the revised artifact under an explicitly versioned protocol. Any reused
   review must be valid for byte-identical inputs and that protocol; a changed prompt
   must not reuse old acceptance by assumption. Keep unresolved findings blocking
   compilation, then freeze the completed corpus before opening retrieval profiles.

The reduction from the original 126 findings to V3's 23 is not an apples-to-apples
quality improvement: host briefs, surfaces and reviewer protocol changed, and the
reviewer still has false positives and negatives. Retrieval recall, relation accuracy,
temporal safety, latency and publication readiness remain unmeasured on this corpus.
