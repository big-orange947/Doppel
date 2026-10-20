# Annotation-only safety correction: zero-call frozen follow-up

The f7e8e02 nine-call source-review experiment is complete and preserved. Its
synthetic controls matched8/8, but the real windows exposed a false positive:
an owner statement about visiting Munich was rejected because the model used
an unrelated historical assistant denial. Exact source quote matching did not
prevent cross-draft/cross-actor reasoning. Two real decision-to-completion errors
were also flagged. These observations do not justify default hard filtering.

Correct the opt-in wrapper's default to **annotate**, with explicit `withhold`
retained as an experimental choice. No prompt, provider output, confidence,
control expectation, historical grade or source record is changed. Preserve
flagged candidates and expose reviewer/quote/unverified status through transient
claims and ordinary query metadata/warnings. Source-disputed candidates cannot
certify an exact count, but recall stays available. Existing actor/scope gates
remain independent and authoritative.

Reapply exactly the same9 cached raw review responses to the same8 original
source windows and fixed8 synthetic controls, using a fresh version-bound run.
Parent cache JSON hashes, request hashes and source code are frozen in preflight.
Key-free/cache-only mode must permit **0 new provider calls**, with no new
extraction, QA, graph, source writes or access to reserved histories. No retry,
cache repair or correction of the original reviewer judgments.

Check that71 previously eligible real proposals are retained instead of68,
including the owner claim falsely rejected and the2 disputed completion claims;
the latter must remain clearly annotated, not treated as repaired facts. Keep
original source/actor quarantine counts and event precision warnings visible.
An annotation may itself be false; this is recall safety, not a claim that
semantic extraction or answer accuracy is now solved. No default analyzer or
review policy promotion beyond the safe behavior of this optional wrapper.

- Frozen preflight: data/doppel/source-grounding-annotated-preflight-frozen-v2.json
- File SHA: 37ac739f5a4311dbc6cf974d1635bdc22623564878c380d66ee9edbfd9f93d51
- Plan: 5f68088922ddc7f60c0003c8ab7f2be63faf3a10599e59cfc360ccde2cef7bbd
- Parent read-only cache: data/doppel/source-grounding-v1/review
- Fresh run directory: data/doppel/source-grounding-annotated-v2
- New-call cap0 is enforced by cache-only before provider access; ledger retains
  its generic positive bound, but no reservation/network request is allowed.
- Original live/key-free replay SHA:
  805323fdab8dcb03fe2172d0527c6fe68f25b440642ae7e1893bd7a8df8db6bf

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_memory_source_grounding --run-dir data/doppel/source-grounding-annotated-v2 --output data/doppel/source-grounding-annotated-live-v2.json --frozen-preflight data/doppel/source-grounding-annotated-preflight-frozen-v2.json --read-only-review-cache data/doppel/source-grounding-v1/review --execute --cache-only
```
