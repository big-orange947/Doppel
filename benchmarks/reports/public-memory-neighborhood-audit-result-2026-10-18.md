# Neighborhood audit: adjacent sources recovered, QA not rerun

Date:2026-10-18. Frozen implementation/plan:`529a346`. All5 already-opened
ordinals41-45 complete with zero paid-provider calls. This is a development
candidate-availability audit motivated by the known adjacent misses, **not** an
independent benchmark, new answer score or evidence that a100% recall claim
generalizes. The previous paired QA stays3/5 vs3/5.

## Candidate availability and capacity control

The original80 pools preserve9/11 annotated turns across four positive cases.
Scoped ±1 source-neighborhood expansion recovers the other two; a production
native BM25/vector pool enlarged to the **same actual per-case count** recovers
one of the two. No labels, question keywords or actor quotas choose neighbors.

| Case | Original count | Expanded / matched-native count | Original hits | Expanded hits | Native hits |
| --- | ---: | ---: | ---: | ---: | ---: |
|d6233ab6|80|169 /169|2/2|2/2|2/2|
|a96c20ee_abs|80|157 /157|N/A|N/A|N/A|
|f4f1d8a4|80|175 /175|1/1|1/1|1/1|
|gpt4_7abb270c|80|135 /135|4/6|6/6|5/6|
|6a27ffc2|80|170 /170|2/2|2/2|2/2|
|Four positive cases|—|—|**9/11**|**11/11**|**10/11**|

These are whole-message annotation hits in an **unselected candidate pool**,
not final selected/packed semantic evidence or correct answers. The negative row
has no positive denominator and is not converted to an automatic coverage hit.
Equal count does not ensure equal text length, compute or model-input budget.
The native baseline recomputes its wider production RRF pool rather than merely
taking a longer prefix of the original pool. Larger native limits, different
embeddings or other windows were not tested/tuned after observing this result.

## Costs and boundaries

| Case | Expanded content bytes | Same-count native content bytes |
| --- | ---: | ---: |
|d6233ab6|263,108|165,546|
|a96c20ee_abs|196,893|156,700|
|f4f1d8a4|155,588|162,626|
|gpt4_7abb270c|147,414|168,257|
|6a27ffc2|225,812|165,007|
|Total|**988,815**|**818,136**|

Across5 cases both comparison arms contain806 candidates; neighborhood expansion
adds406 original messages to the400 anchors. It uses about**20.9% more formatted
source bytes overall** than same-count native retrieval, although less on the
temporal case. Byte figures include source-content attribution formatting, not a
complete LLM request or tokenizer measure. Do not advertise the extra evidence as
free or a net provider-cost saving. Additional read-only source lookups also cost
I/O, and no stable latency result was measured.

All cases fit frozen240-candidate/300,000-source-content-byte caps without
truncation, skipped neighbors or unvisited anchors. Rejection maps are empty. Every
original80-anchor payload/order is preserved. Every returned neighbor has current
source/provenance, exact scope/session and explicit source offset checks. Inventory
hashes match before/after each case. No Store/index/schema/graph/old-cache writes
or key reads/provider clients, and no authoring/extraction/Reader/judge calls.
The capacity-matched baseline uses at most5 local query embeddings against the
existing bge-small-zh512 index, not full reindexing or a new model download. No
external HTTP-count claim or security/latency certification is made.

## Implemented reusable boundaries

- Packaged `doppel_memory.source_order`: strict explicit `SourcePosition`, a
  read-only host `SourceOrderResolver` protocol and an immutable-returning in-memory
  reference index. IDs and scoped session ordinals are unique; gaps remain gaps.
- Repo reference `integrations/aml/neighborhood.py`: optional attributed expansion
  **before** final selection. Default ±1,80 anchors/240 candidates/300KB/30 seconds.
  No timestamp/ID/role-based chronology inference, summaries or facts added.
- Source callbacks return IDs/positions, never trusted replacement text. Source
  records are reloaded using the existing attribution validator. Changed sources,
  order and revoked anchors are rejected; unsupported newly added neighbors are
  removed. Scope/session escape, invalid radius, duplicate/excess positions,
  conflicting order or mutable callback parameters fail closed.
- No speaker quota: user and assistant neighbors remain independently attributed.
  Added neighbors' similarity0 is an unscored placeholder, not a measured relevance
  probability. Same-session adjacency is not logical support or event identity.
- The index is a host-owned ordering input, not a persistent Store migration or
  new authorization layer. Chunk-local transport indices are deliberately not
  treated as global order. Missing explicit positions preserve valid anchors and
  report the limitation. A consistently wrong host index cannot be proven correct
  by source existence alone.

Integration caveats remain: generic selection defaults to80, so an expanded pool
must be wired with explicit candidate/request budgets rather than silently cropped
back to80. Additional time/tag/fine-grained authorization rules are not inherited
from anchor retrieval automatically; use request-specific source resolvers and
eligibility gates for **every** neighbor. A denial (`resolve_event=None`) is not
returned as authorized evidence. Store/source checks are per-source, not an atomic
snapshot of all messages. No default retrieval/export or top-level API changed.

## Verification and artifacts

Full regression:**2056 passed/33 skipped/three subtests** in227.48s. Targeted25
tests pass, including an added request-specific resolver-denial assertion. Ruff
repository/new-file formatting and Pyright new implementations pass. One existing
Graphiti/Pydantic deprecation warning remains. The final documentation/policy
assertion changes do not modify the frozen runtime or diagnostic results.

- Preflight:`data/doppel/neighborhood-audit-41-45-preflight-v1.json`, SHA-256
  `552c760ca4e72d105b871da83e2731adbbdfc5d31feb3faf7f7e463600e0e994`.
- Plan fingerprint:
  `b275a998c36153b07a631e3d46c56fc9e2e5fd6f8cef69b276599ce89f23cdce`.
- Live:`data/doppel/neighborhood-audit-41-45-live-v1.json`, SHA-256
  `1dda9b67e8b64c380d7485a9e1fad30012452108c2da8f2c478ae1a30b179c79`.
- Run directory:`data/doppel/neighborhood-audit-41-45-v1`, exclusive attempt
  receipt and five per-history snapshots with original sources/discovery links.

All artifacts remain ignored local data; no private source payload added to Git.
The user's unrelated`uv.lock` remains untouched/unstaged. No paid replay, answer
regrading, new/reserved-case access or quality gate relaxation occurred.

## Next decision

Keep this optional: the one additional annotated hit versus matched-size native
retrieval is confined to one already-opened temporal case and costs more text
overall. The known adjacent misses motivated the design, so this is particularly
optimistic development evidence. It does not justify claiming a better final
answer, global recall or default policy. Native widening remains a serious simpler
baseline, not a straw man.

Next freeze untouched cases and compare native widening versus neighborhood
expansion with the **same selection model and explicit pool/request budgets**.
Measure selected/packed evidence and QA, not just source availability. Do not
keep retuning this window on these5 cases, force a temporal answer or replace the
pending preference/recommendation Reader issue with more graph authoring. The
old scores remain unchanged until a separately reported experiment exists.
