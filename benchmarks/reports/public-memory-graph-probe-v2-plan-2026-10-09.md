# Source graph probe v2: correct per-memory relation contract

Freeze before the v2 live read-only probe. Preserve v1's failed report unchanged;
there are no paid calls, fact rewrites, algorithm/threshold changes or QA scores.

The post-authoring v1 audit verifies 210/210 projections and visits all 231 rich
edge/Episode links (229 distinct edges). It fails 25 strict edge-selection checks;
every one-hop path, wrong-subject check and cross-scope check passes. A zero-call
read-only follow-up queries **all 25** failures, not a selected subset: all 25 source
memory IDs are present with the expected Episode provenance, but the returned
representative edge is different from the individually probed edge.

This matches existing production behavior: `GraphitiRelationIndex.search_relations`
deduplicates with `results[(group_id, memory_id)]` and retains one representative
edge per memory. Its contract is memory-candidate retrieval, not enumeration of
every edge. Path retrieval has a different path-based contract.

V2 requires the expected source memory, exact scope, source Episode and requested
relation type to appear in the returned relation candidate. It still requires the
individual probed edge to appear in a one-hop path with source-memory provenance;
wrong-subject and cross-scope requirements remain unchanged. Keep the old exact
edge-selection boolean as an explicit **non-gating observation**, and record the
actually returned representative edge IDs. Do not hide its 25 differences.

Do not interpret this as relaxing answer/evidence support. Source IDs, Episode IDs,
types, paths and isolation remain checked, and a synthetic alternate-edge control
now exercises the legitimate per-memory case. No production retrieval code changes.
The source anchor, predicate label and fact text are still taken from stored edges;
passing v2 proves interface/provenance connectivity only, not natural planning,
recall@k, multi-hop reasoning, extracted-fact correctness or answer accuracy.

Other scopes currently have no projections; the negative cross-scope check is not
a populated multi-owner/adversarial security benchmark. Full fifty-history graph
coverage and highest-configuration QA are still not approved by this probe.

Old receipt `data/doppel/public-memory-graph-first-history-probe-v1.json` SHA-256:
`5eed5e8ce1d0411de85f2963cf3ec7c742678645847dd1235e40691e2aa0d4de`.
New output: `data/doppel/public-memory-graph-first-history-probe-v2.json`.
