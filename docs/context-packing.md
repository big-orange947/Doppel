# Optional lossless context metadata factoring

`doppel_memory.context_packing` is a module-only, opt-in codec/packer for an
already-authorized ordered list. It is **not** installed into recall, personal
query, AML search, the existing Reader or an agent's context manager. It does
not trigger memory selection, retrieve anything, confirm facts or grant access.

The first opened30 paired replay does **not** establish an evidence/QA gain.
Retain mode includes41 extra complete sources without gaining annotated turns;
repacking from scratch loses3 annotated turns across2 cases. Keep the current
production/default packing and Reader protocol unchanged. See the
[diagnostic result](../benchmarks/reports/public-memory-packing-replay-result-2026-10-23.md).

## Format and invariants

Only fields identical across every supplied candidate can move into `shared`:
scope_key, channel, temporal_status, valid_from and valid_to. Explicit null stays
explicit null; absent fields are not guessed. Role, actor, authority, observed_at,
memory_id, text and source references remain per-item. Original text is not
stripped, summarized, truncated, normalized or synthesized.

The envelope is human-readable JSON:

```json
{"format":"doppel.shared-context.v1","shared":{"scope_key":"..."},"items":[{"memory_id":"...","text":"...","role":"user","actor":"owner","authority":"human_self"}]}
```

An envelope is used only if it is smaller than the unchanged plain list. Decoder
rejects unknown format, unexpected shared fields, key overlap and invalid/mixed
scopes or duplicate IDs. A decoder is not a source-authority validator; hosts
still need their original Store/provenance/isolation checks. No model should
infer new authority from field placement.

## Policies and bounds

```python
from doppel_memory.context_packing import pack_context_items, unpack_context

result = pack_context_items(authorized_ranked_items, mode="retain")
selected_original_items = unpack_context(result.payload)
```

Default bounds:80 input candidates,20 returned items,24000 UTF-8 JSON bytes.
Inputs must be JSON-roundtrippable objects with explicit scope_key, memory_id
and original text. Inputs are snapshotted and never mutated.

- `retain`: compute original whole-item ranked-fit selection, keep every old
  selected item, then use saved bytes to include more items in original order.
- `repack`: scan the same source order from scratch using factored byte costs.
  Previously skipped long items can displace several smaller items, including
  necessary evidence. It is experimental, not an automatic upgrade.

Neither policy sees a question, answer, task type, gold label or reference. Item
count and byte bounds are not relaxed. Empty/oversized items never cause invented
text. `unpack_context(result.payload)` reproduces the complete original selected
JSON objects, not their original JSON dictionary-key order/serialization.

The consumer must explicitly support the envelope. Do not silently feed it to an
old list-only Reader, reuse an old answer cache under this wire format or assume
that reversible JSON compression improves an LLM's comprehension. No such
answer-generation comparison has run. This module remains unpromoted.
