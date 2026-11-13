# Source-preserving extraction: partial pilot, not ready for promotion

Implementation `828056e`; independent continuation `d9b0fa9`.
[Original plan](source-clause-probe-plan-2026-11-13.md),
[continuation plan](source-clause-followup-plan-2026-11-13.md).

The new module-only candidate requests exact source clauses and annotations,
then uses the entire cited original message as content. Actor comes from that
source; contact identity still passes ordinary sender binding. Model-generated
content and subject fields are forbidden in its schema. No default changes.
Exact quotes and whole-source rendering constrain text provenance, not semantic
correctness, annotation quality, count accuracy or ownership of mentioned entities.

## What actually ran

The original paired runner stopped after the second default window. Its frozen
stop policy meant the candidate was not executed. Preserve that stopped receipt;
it is not a completed six-call comparison. The candidate was then frozen as an
independent arm, using the same unchanged messages, instructions and rubrics, a
separate three-attempt ledger, and new state. No original request was retried.

| Arm | First source | Second source | Third source | Calls / reported tokens |
|---|---|---|---|---|
| Default V8 | Complete | Evidence-gate failure | Not run | 2 / 2,961 |
| Source-clause candidate | Complete | Schema failure | Not run | 2 / 1,980 |

All four provider requests succeeded at HTTP/JSON level. Both workflows stopped;
do not report overall quality success or a three-case pass rate. No Reader/Judge,
embedding, Graphiti, real chat or old-state reset. Unused attempts are not refunded
or automatically reallocated. Combined actual usage: **4 calls / 4,941 tokens**.

### Whole-context retention and redundancy

First source: “A colleague bought a new laptop. I have not ordered one and still
use my old desktop.” Default V8 emits one reasonable current owner-state summary.
The candidate emits three annotations, each attached to the same whole original
text: colleague purchase, owner non-order, owner desktop use. Source text and
negation remain available without generated name/pronoun substitution.

The three duplicate bodies are an observed cost, not three independent facts.
They have different topic/status annotations and survive as three candidates.
One describes a colleague's acquisition while its subject role is owner, because
this adapter binds source perspective, not the subject of every predicate. The
full text makes the distinction visible, but metadata alone does not certify it.
This tradeoff is not a demonstrated improvement in semantic quality.

### Failures on embedded speech and occurrence metadata

Second source: “Rina told me, 'I moved to a new apartment last week.' I am still
in my original apartment and have no moving plans.”

Default V8 emits a third-person episode with `subject=rina` and an event-time
expression “last week (relative to 2026-11-04)”, which is not a verbatim source
span. It also emits a valid-looking owner-state draft. The default batch gate
rejects the batch; no derived records are committed for that source.

The source-clause candidate retains valid clause strings but emits a coordinate
with `precision=week` (unsupported; schema uses range), and puts event_key/time on
a `memory_type=fact` draft. Validation stops before committing any derived record.
The raw response remains cached. Whole-source rendering has not solved typed
annotation correctness. No output repair, coercion or schema relaxation was used.

## Cache reconstruction

Candidate cache-only execution in a fresh state directory made zero new attempts,
hit both raw outputs and reproduced the same stopped window. Analysis observations
and sorted record projections are equal. Ordered query output is **not identical**:
two identical-body records with different metadata swap positions on an equal-score
tie in the newly built Store. The unordered hit set is equal; no missing record
was observed on this sample. This is not byte-identical replay or a demonstrated
recall regression. It remains an ordering/duplicate-material issue for follow-up.

Artifacts remain in `data/doppel/source-clause-probe-v1-*` and
`data/doppel/source-clause-followup-v1-*`; summary binds the live/replay hashes and
explicitly records `replay_projection_equal=false`. State lives in dedicated
`data/examples/source-clause-*` directories. No existing record or failed receipt
was replaced to improve the result.

## Verification and next step

Ten new offline tests; 49 related checks pass. Full suite: **2,599 passed /
33 skipped / 3 subtests passed**, one existing Graphiti/Pydantic deprecation
warning. Ruff, formatting and changed runtime/runner Pyright pass.

Keep the candidate experimental. Next separate retained source context from
independently typed assertions, so one raw message need not create multiple
identical bodies interpreted as separate facts. Invalid time/subject annotations
must stay visible without being silently repaired; test any partial-acceptance
policy independently. Preserve this failed pilot and use fresh controls for
future changes; no claim that previous lifecycle attribution failures are fixed.
