# Evidence-rich blind V1 authoring V6: preserved incomplete result

Date: 2026-10-05

Runner: `doppel.evidence-rich-blind-authoring.v6`

Implementation commit: `515ce323a11c1b65404d387ef25f87df527a2183`

Manifest fingerprint: `852dfde146d8ac2920683ac275eb5a35700bdb47e01cf09cad4dd0433065d253`

## Outcome

V6 stopped at `owner-blind-12:01` with `SurfaceGenerationExhausted`. It made three
new provider calls, bringing the cumulative total to 47 calls and 535,745 tokens, but
accepted no additional batch beyond V5's 22/48. Retrieval remained unopened and no
quality metric was computed. The requested 228-call cap did not force extra spending:
the runner stopped immediately at the sealed nine-attempt boundary.

V6 fixed the repeated city/organization display-name defect. All three V6 drafts
passed entity, query, relation-shape, and within-batch evidence validation. They were
rejected solely by the V4 global evidence registry:

| Total attempt | V6 collision result |
|---:|---|
| 7 | Two prior-owner memory matches and two prior-owner edge matches |
| 8 | Four prior-owner memory matches and one prior-owner edge match |
| 9 | One prior-owner memory match and one prior-owner edge match |

No V6 collision was within the batch or within owner 12. All matched evidence belonged
to other scopes. The first eleven completed owner scopes still contained 2,112 unique
memory strings and 110 unique edge facts under the stronger historical contract.

## Contract finding

Global natural-language evidence uniqueness is not aligned with Doppel's authority
boundary. Different people can state the same fact in the same words, just as they can
share an entity name or ask the same question. Inside one owner, duplicate evidence can
overweight retrieval and must remain forbidden. Across owners, candidates are governed
by exact scope and provenance; equal text is realistic isolation pressure and does not
duplicate evidence inside any query's authorized search space.

Repeatedly paraphrasing valid cross-owner evidence also makes the synthetic corpus less
natural and consumes calls without improving the property under test. The three V6
attempts empirically separate this contract issue from the fixed V4 memory-collapse and
V5 entity-name defects.

## Continuation decision

V4, V5, and V6 remain immutable. V7 hashes and replays all three parent-cache layers,
uses the V6 surface instructions, and replaces the global registry with a scope-local
registry keyed by owner scope. Compilation applies the same `(scope, text)` uniqueness
rule to memories and relation facts, continues to reject any copied memory from the
opened V4 corpus, and reports global memory/edge repetition counts transparently.
Retrieval remains closed until authoring, independent semantic review, and compilation
all succeed.
