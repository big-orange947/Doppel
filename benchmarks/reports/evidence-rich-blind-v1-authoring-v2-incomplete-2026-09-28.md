# Evidence-rich blind V1 — authoring V2 incomplete result

Date: 2026-09-28

Status: preserved cross-owner surface-uniqueness failure; retrieval was never opened

Implementation commit: `eb3c39e01703775d2c29ff4952ec75eab1d5183e`

Host-manifest fingerprint:
`eb76c6d920d489fa0cd3dff7524b00ada82ec05ac8d511db9aae6f99177e9785`

## Execution

- logical batches: 48;
- completed batches: 10 (five complete synthetic owners);
- provider calls: 10;
- calls with usage: 10;
- input tokens: 59,378;
- output tokens: 47,334;
- total tokens: 106,712;
- reasoning tokens: 0;
- invalid cache entries: 0;
- retrieval calls and quality metrics: 0.

The V2 contract fixed the V1 defects it targeted. Every owner used the exact required
shared alias `启明服务中心`; all five owner-local 16-entity batches were internally
unique; every 96-memory batch and 10-query batch passed host projection; and zero
variation-nonce, internal-handle, or credential markers appeared in surface text.

A cross-owner audit after the first ten calls exposed a separate contract gap:

- 75 non-shared entity names produced only 58 distinct exact strings;
- 960 memory contents produced 955 distinct exact strings;
- 50 query texts produced 38 distinct exact strings;
- all 50 non-empty relation edge facts remained unique.

The frozen compiler requires unique memory and query surface text. The extra entity
name collisions also violate the corpus design, which permits only a host-declared
shared-name group. Finishing all 48 V2 batches would therefore spend provider budget on
an artifact that the offline compiler must reject.

The ignored runtime progress, state, manifest, and ten raw cache envelopes remain
preserved. The progress artifact SHA-256 after the final zero-call replay is
`4f540560b83b91ae90477d5d3280f107f5d97cbd8bc288c301b5a0820a9e089a`.

## Decision

No V2 cache entry was rewritten, migrated, or deleted, and no V7/V8 retrieval output was
opened. Authoring V2 stops at 10/48 batches.

Authoring contract V3 retains the preregistered authority topology and gold labels but
adds an online exact-surface registry. Only the declared shared-name group may repeat.
All other entity names, memory contents, non-empty relation edge facts, and queries must
be globally unique. A colliding batch is not accepted: it receives a new sealed
variation attempt containing only the opaque local surface keys that must change. No
prior owner text or private gold is exposed. Attempts are capped and budgeted, and V3
uses a new runner, nonce namespace, cache directory, progress file, and manifest
fingerprint.
