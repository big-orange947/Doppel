# Blind corpus: bounded text revision, semantic acceptance still pending

Date: 2026-10-06

Actual surface repairs are now generated as separate artifacts. No production
planner, retrieval strategy, scoring criterion or private evaluation label changed.
No retrieval profile was opened and no provider/API-key path was used.

## Actual changes within the frozen inventory

The inventory allowed inspection of 106 slots. Exactly 84 surface slots changed;
22 candidates were retained. All 5,220 unlisted/unchanged slots remain identical
to their original text. This is 84 / 5,304, approximately 1.58% of surface slots.
Individual content, brief and edge edits are recorded separately in the local diff.

| Change family | Actual changed surface slots |
| --- | ---: |
| Precise original temporary-residency interval | 24 memory contents |
| Precise original March 15 query date | 24 questions |
| Issuance/coherence memory repairs and necessary name references | 15 memories |
| Sale/adoption actors and return/re-adoption lifecycle | 12 memories |
| Issuing entity names | 6 entity names |
| Questions referencing the renamed creative documents | 3 questions |

Total: 51 memory contents, 27 questions and six entity names. There are also
27 changed edge-fact strings and 78 changed semantic briefs attached to these
same slots. They are not additional memory/query samples.

The existing credential and current competent-issuer names were retained. Only
the creative document and competing issuer names changed in the issuance family.
The creative object is now an activity commemorative certificate, which can have
a separate creator and issuing institution. Both the `CREATED_BY` route and the
competing `ISSUED_BY` route still exist. The competing issuer is an immigration
authority, not a publisher or training school said to issue passports. Its role
in issuing the activity certificate is explicit in the fictional corpus.

Old and current passport records distinguish expired and reissued versions; an
expired credential does not erase the historical act of issuance. Old animal
adoption records explicitly describe return to the institution on the original
end date. Current records describe re-adoption from the original current source
on the original start date. Bird records distinguish a previous keeper's adoption
from the later sale to the owner. No competing/stale branch was deleted.

The natural-language strings are assistant-curated repairs, not a new independent
model-authoring run. They add actor/version/lifecycle context to synthetic records;
they are not new observations from a real user's history. This limitation must be
preserved when interpreting the eventual benchmark.

## Invariants and limits of automated checks

The revised manifest is version `1.4.2`. Its wording fingerprint changed, but its
private-authority fingerprint remains exactly:
`127c3a74137e12e70e89873aff6d745f18dbb7136ddb5b325d402a9842e006b6`.

Owner partition, identity/type, scope, subject, authority, state, valid intervals,
relation direction/type, routes, evidence IDs, answerability and all required /
related / forbidden labels are unchanged. The applier rejects unlisted text,
brief or edge edits and changed private authority. It also verifies full projected
coverage, same-owner uniqueness, shared-name constraints, original graph shape,
and explicit source/target names in every relation content and edge fact.

Exact endpoint-name presence is a structural check, not proof of correct sentence
meaning or relation direction. Semantic acceptance remains a separate step. No
automatic acceptance follows from passing these invariants.

Unknown-buyer questions and subject-correction questions remain byte-identical.
No answerability hints were added to those queries. Original flagged custody
records were retained rather than treating compatible old/current holders as a
contradiction. All 23 original review findings remain pending adjudication, with
their original details retained in the diff. The original rejected report and
all source/cache artifacts remain immutable.

The original reviewer-calibration branch remains stopped. Next work is bounded
semantic adjudication of the revised source and retained disputed findings, then
an explicitly frozen corpus and unchanged V7/V8 retrieval comparison. Do not
claim an independently accepted blind corpus or new recall scores at this stage.

## Local artifacts and hashes

The recipe and full-text outputs remain ignored to avoid publishing the still
unopened blind surfaces. The final generated files use the `final` prefix and
bind the committed applier `947c0287c5a5874b76355c455e9443693b853d21`:

- `data/doppel/evidence-rich-blind-v1-bounded-revised-final-manifest.json`:
  `893eab19077b76412796aa829359c566812bfb1c472abb2cfb2f85ed7d69b32a`.
  `591275a89778efe6ca5dabfe0ff43b090632a656e25a905f6a4b5d5ce3c4ebc9`.
- `data/doppel/evidence-rich-blind-v1-bounded-revised-final-diff.json`:
  `90c5a48a41b5584f60816b3f11a57e48fe2e58f4d77fe1d65d51a1fb53f048bf`.

The diff binds source hashes, recipe hash, applier source hash, revised hashes and
every changed field's old/new text and hash. The initial and `verified` generations
are retained as intermediate snapshots, not overwritten. They have the same surface
repair content; the final generation additionally separates original authoring
usage/timestamp/commit provenance from the current zero-call curation invocation.
Their differing metadata does not represent another corpus/algorithm experiment.

Original authored/review/inventory hashes were rechecked and are unchanged.

Observed diversity: 4,567 distinct memory strings, 143 question texts, 232 nonempty
edge facts and 255 entity names. Originally there were 144 distinct question texts;
date normalization collapsed one wording variant. There are still 240 query slots,
not 240 independently worded natural-language questions. Corpus scale and text
diversity must not be conflated.

Usage: zero provider calls and zero tokens. Corpus acceptance, compilation and
retrieval metrics remain false. No lockfile or dependency installation changed.

## Verification

There are 14 new offline tests for precise dates, preserved inputs/gold, scoped
renames, single-pass substitution, unlisted text/edge rejection, malformed recipes,
changed source hashes and output overwrite protection. They do not require local
blind artifact files or live backends.

Full suite: 939 passed, 33 skipped and three subtests passed; one existing Graphiti
Pydantic deprecation warning. After the final provenance-only metadata separation,
all 25 inventory/applier tests were rerun and passed. Ruff passes all three affected
Python files. Full Pyright passed; the final applier recheck also has zero errors.

The final generated applier hash matches the committed source bytes; all original
authored/review/inventory hashes were rechecked again after final generation.
