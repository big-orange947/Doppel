# First-history graph backfill: separate bounded continuation

Freeze before continuation calls. The original run/receipt/caches are immutable;
this is not an automatic change to its budget, a new algorithm or a QA result.

## Parent observation

Original first-history run: 146/210 projections verified, 143 new writes plus the
three reused smoke records. All 601 provider attempts succeeded, zero missing
usage, 2,499,757 reported tokens. Canonical request bytes are 7,999,092 against the
8,000,000 ceiling; one additional uncached request was not reserved. The old report
exposes only the Graphiti wrapper exception, not its nested budget classification;
preserve that observability limitation rather than changing its recorded failure.

Among the 146 checks, 102 have at least one non-fallback edge; 44 have only fallback
coverage. The reported 161 rich edges are **Episode-edge link incidences**, not a
deduplicated graph-edge total. There is no natural-query recall score.

Parent budget identity:
`1410d51c8a740a6cd40f8517222be68972df45bba2fcc59933cbbf1976a348d4`.
Receipt: `data/doppel/public-memory-graph-first-history-live-v1.json`.
Raw receipt SHA-256:
`9df0e5fed4b5ff3aff12c5bfe62a8793140df90c1f7fd9a573e6d4f6d49f37e0`.

## New plan and ceilings

Select the **same** source-ordered 210 records, exact corpus and target fingerprints.
Use `data/doppel/public-memory-graph-first-history-continuation-v1` as a separate run
directory. Generate and bind a new frozen preflight; keep production Graphiti,
provider parameters, prompts, embedding and Store/vector contents unchanged.

Maximum **899 new attempts**, so parent plus continuation remains within the
original **1,500-attempt** ceiling. The eight earlier smoke calls are separate,
already-paid work and must also appear in total first-scope authoring accounting.
The new explicit canonical-byte ceiling is 8,000,000; aggregate admitted bytes across
the two runs can therefore reach 16,000,000, unlike the original single-run ceiling.
No retry, silent budget mutation, overwrite of old scores or hidden token refund.

Read the parent cache through existing content-addressed **read-only** cache
support. A hit must validate the exact model/prompt/input/schema envelope; invalid
cache entries fail rather than being rebilled. Bind the parent receipt, settled
ledger, cache inventory hash and target fingerprints into the child plan, and
recheck them after live execution. The new harness rejects nested continuations to
avoid hiding earlier accounting; another stop requires a separately reviewed plan.

Revalidate and reuse the 146 complete projections without LLM calls. Complete
remaining targets through the production writer, retaining rich and fallback edges
separately. Aggregate both budget identities' attempts/usage/unknown usage; never
report only the cheaper child run as total cost. The reporting change now preserves
exception-chain types and allowlisted budget reasons without provider text or keys.

Only a completed 210-record receipt can advance this first scope to projection
audit and natural-query pilot preparation. Full fifty-history graph coverage,
natural planning quality, answer quality and multi-hop quality remain uncertified.

Before live: 46 focused runtime/backfill/probe tests pass, including immutable
parent binding, remaining-attempt enforcement, changed-ledger/nested-parent refusal
and redacted failure-chain handling. Prior full regression: 1,398 pass/33 skip.
