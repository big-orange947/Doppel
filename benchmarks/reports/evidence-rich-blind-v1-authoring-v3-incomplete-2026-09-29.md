# Evidence-rich blind V1 — authoring V3 incomplete result

Date: 2026-09-29

Status: preserved over-constrained cross-owner uniqueness result; retrieval was never opened

Implementation commit: `1478813e7b6df134972490c25c3c51ece8f48582`

Host-manifest fingerprint:
`7c4df04d6bc1ee3db5ac2f7f920c08225697a075b0e68595e444c5492b5ce4d4`

## Execution

- logical batches: 48;
- completed batches: 2 (one complete synthetic owner);
- provider calls: 5;
- calls with usage: 5;
- input tokens: 32,659;
- output tokens: 25,503;
- total tokens: 58,162;
- reasoning tokens: 0;
- invalid cache entries: 0;
- retrieval calls and quality metrics: 0.

The first owner's two batches passed on their first attempts. A zero-call replay hit both
cache entries and confirmed 16 unique owner-local entity names, 192 unique memory
contents, 10 unique relation edge facts, 10 unique owner-local queries, the exact
required shared alias, no opened-V4 text copies, and no nonce, internal-handle, or
credential leakage.

The second owner's first batch then exhausted all three sealed attempts:

1. attempt 0 passed local projection but repeated five exact surfaces from owner 1:
   three ordinary entity names and two common residence questions;
2. attempt 1 rewrote the requested keys but assigned one display name to two distinct
   owner-local entities, so local projection rejected it;
3. attempt 2 passed local projection but repeated three ordinary entity names, one
   memory content, and three common questions. No relation edge fact repeated.

The runner stopped with `SurfaceGenerationExhausted`; none of the three drafts was
accepted. The progress artifact SHA-256 is
`dfee3bd523ca6b2ec9e8b3c82df43a3e10b586bb4a754ecafc707d9eac8a9814`.

## Root cause and decision

An offline manifest audit found that owner 1 and owner 2 intentionally share 186 of 192
memory semantic briefs and eight of ten query semantic briefs. They exercise the same
personal-memory capabilities under disjoint scopes. Forcing different users never to
share a city, employer name, or natural question such as a current-residence lookup is
not a realistic multi-tenant contract. Opaque variation seeds cannot reliably alter
those facts, and owner-specific textual salts would make retrieval artificially easy.

No V3 cache entry was rewritten, migrated, or deleted, and no retrieval output was
opened. Authoring V3 stops here.

Authoring contract V4 keeps owner-local entity and query uniqueness, global memory
content and relation-edge uniqueness, and the exact host-required shared alias. It
allows entity names and query wording to repeat across owners as deliberate scope
isolation pressure. The offline compile report records raw counts, unique text counts,
repeated groups, and maximum repetition so duplicates cannot inflate an undocumented
effective sample size. V4 uses a new runner, nonce namespace, cache, progress file, and
manifest fingerprint.
