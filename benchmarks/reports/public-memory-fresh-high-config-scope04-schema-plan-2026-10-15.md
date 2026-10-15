# Fourth scope: graph recovery complete, source-only schema freeze

The authorized recovery completed all 162 projections. It added only the remaining
36 records, 139 successful attempts / 620,581 tokens, with zero incomplete-slot
repairs. Original 529 call rows remain byte-identical at the logical-row hash.
Graph cumulative 668 attempts (667 successes + one preserved transport failure),
2,824,469 known tokens and one missing usage; original 1,500-attempt ceiling is
unchanged. No extra retry, source/core/prompt/model changes or QA on partial graph.
Source, Store, vectors and other cohort graph scopes remain unchanged.

- Complete graph receipt SHA-256:
  `b6f245388f5f1e1b1b92ed03043e6dee8aa2cec1b042abec12880e347bd86c28`.
- Preserve original failed graph receipt:
  `db3c5a7083247521f7c1bfd5a3bc9a077eca98b9b07b8a00045ae0b21b5f4b04`.
- No observed allowlisted endpoint warnings in either invocation; this does not
  certify semantic completeness or coverage of unobserved warning classes.

Actual source snapshot has **172 distinct rich edges / 128 distinct names**.
The graph writer sums 174 per-episode rich-edge associations; these are not 174
unique edges. Freeze the actual distinct-name inventory before schema calls:

- Plan fingerprint:
  `bba4aca03429750365643ecb2f6a2eb92271d9ddc3a419ff683a1f14c48a66a9`.
- Preflight SHA-256:
  `61d67e5af3c5e1ca46179897eb67c8bb40176e7c4c343d77a9f29a8ff4047141`.
- Edge snapshot SHA-256:
  `0c38ac7cf71526af94c92a6624ad4afddafed87339d81b7b5e36a901eda36910`.
- Six calls maximum; at most 24 source names/batch, 4,096 output cap,
  100,000 canonical request bytes/call and 600,000 total. No automatic retries.
- Unchanged schema source/instructions/provider. Distinct names ONLY, no entities,
  graph facts, source texts, question/gold/labels. Keep all names; generated
  descriptions remain fallible, not independently verified edge semantics.
- Zero graph/Store/vector writes and verify unchanged selected graph.

Next: freeze paired question plans, ordinal 4 / `7e00a6cb`, raw first then full,
same existing fifty-case settings and eight QA attempts maximum. No retuning,
resampling, new calibration campaign or official/independent/AML score claim.
