# Reference analyzer workflow: first live result, 2026-11-10

The user ran the bounded reference entry in their configured PowerShell. The local
receipt confirms one completed provider request, followed by deterministic
consolidation, real PostgreSQL/pgvector maintenance and retrieval. No further LLM
calls were made during this inspection. This is a two-message diagnostic, not a
quality benchmark or release gate.

## Runtime and accounting

- Receipt: `data/doppel/reference-workflow-v1-initial.json`.
- Dedicated schema: `doppel_workflow_reference_v1`.
- Runtime `passed=true`, `complete=true`; four Store records, four manifest checks,
  zero foreign-owner hits, six local embedding calls.
- One provider attempt; input 1371, output 139, total 1510 reported tokens.
  No missing usage and no reported reasoning tokens. Actual currency billing was
  not checked; tokens are not converted to an estimated charge.
- Call ledger and all input/output records remain retained. Candidates were not
  automatically confirmed. No prompts, defaults or Store data were changed here.

## Actual stored claims

| Evidence | Content | Topic | Revision | Time status | State |
|---|---|---|---|---|---|
| `theme-1` | 喜欢浅色主题。 | `preference.theme` | assertion | historical | candidate |
| `theme-2` | 现在喜欢深色主题。 | `preference.theme` | correction | current | candidate |

Both records have actor=owner, authority=human_self and the correct owner subject.
Both `valid_from` and `valid_to` are null. The model marked the earlier claim
historical, so deterministic consolidation correctly did not treat the two records
as conflicting current values. This differs from the fixture analyzer's route:
the fixture emits two current values and relies on consolidation to replace them.
Unbounded retrieval returning two claims is not evidence of failed correction.

## Additional read-only diagnosis

Structured planner fields were supplied directly to the existing query engine,
with observation clock 2026-11-03, lexical retrieval and no further model/index
generation. This checks temporal execution, not natural-language planning.

| View | Actual result | Assessment |
|---|---|---|
| current | 深色 only | Matches current/historical labels |
| prior | 浅色 only | Matches historical label |
| as_of 2026-11-01 12:00 UTC | 深色 only, no warnings | Missing validity uncertainty feedback |

The as-of result must not be reported as validated temporal reasoning. Observation
dates alone do not prove effective dates. The later explicit correction could be
retroactive, and the stored claims have no bounds. This diagnostic does not assert
that light is necessarily the unique correct answer on November 1; it establishes
that the current result provides no warning that the requested effective date is
unsupported by known intervals.

Next work should distinguish dated matches from temporally uncertain candidates,
preserve useful evidence for the host, and avoid silently turning observation
timestamps into validity intervals. Do not repair this by domain dictionaries,
fixture-specific rules or forced model-generated dates. Saved records can reproduce
the issue with zero paid calls before any further dataset expansion.

Local diagnosis receipt: `data/doppel/reference-workflow-v1-query-diagnostic.json`.
Original receipts, journal and call ledger are unchanged.
