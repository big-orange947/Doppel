# Opened four-scope source-window diagnostic

Frozen c126345, scopes 5–8, same parent retrieval results and Reader V2. No new
planner/embeddings/reranking, no graph or Store mutation. Opened development only.

Task correctness stays true for 5/6, changes false→true for 7, stays false for 8:
2/4→3/4 on this fixed tiny development cohort, not a generalized uplift claim.
Seventh source turn coverage 0/1→1/1 after original same-session neighboring
assistant reply enters context; actor remains agent_output, never owner fact.
Fifth has no new raw IDs but raw ordering changes; sixth/eighth get three new raw
IDs each without changing task outcome. Seventh adds three raw IDs including the
critical reply. Preserve all old receipts and the eighth acquisition-order refusal.

All four rows complete, citations legal, quoted fragments anchored, zero reported
citation contradictions and resolver failures/rejections. These structural checks
do not certify entailment or link semantics. Fifth/eighth language drift persists.
Twelve new successful calls/50567 reported tokens: 15251/12311/9986/13019 per scope.
Empty-key replay each: zero new calls, three hits, plan/retrieval/reader/task/
citation/context/packing/evidence fields canonically equal. Source/graph unchanged.
Full regression 1559 passed/33 skipped/three subtests; Ruff passing, new modules
Pyright clean. No blind, AML, graph-uplift, full-query latency or default-winner claim.
