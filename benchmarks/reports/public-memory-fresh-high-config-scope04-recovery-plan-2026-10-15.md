# Scope 04: explicitly authorized bounded recovery

User approved one bounded recovery after the new graph transport failure. Keep
the exact original graph plan/preflight/configuration, source receipt, deterministic
record order, provider and existing cache/ledger. No new budget identity/call-cap
increase, question access, owned-slot repairs or automatic second recovery.

- Original graph plan fingerprint:
  `8e174a1087062ddd6c661924bfabc14550f6fc5a5453acadbb1d1a09fad17eda`.
- Original preflight SHA-256:
  `ea5b29e49374f0942102f195e097fe33b1324e81c2f048a8bd408372d69bf28f`.
- Preserve failed receipt SHA-256:
  `db3c5a7083247521f7c1bfd5a3bc9a077eca98b9b07b8a00045ae0b21b5f4b04`.
- Existing durable attempts 529; **971 remaining under the same 1,500 ceiling**.
  Preserve call 529's transport failure and missing usage. Do not refund it.
- Prior ordered call-row SHA-256:
  `d3056f467ac684dc15c8ba079401f9fb3aac59f09291d6ec76ede9ea7d7fc439`.
- Ledger (calls/failure metadata/budget limits) SHA-256:
  `2cb8dd3207240da5de7e8a3ae10848b62e3798064740df9b4aed849ebf64f456`.
- Index journal SHA-256:
  `ecf2255f2ba55cb03c7cac736d526d14449de68e22f598051805c09f0cb650d6`.
- Cache inventory: 528 entries; SHA-256:
  `adb5ba2e943e9f69f3ab1aaecec8885392a5d0a51b834bc024bf564ea514278d`.

Read-only readiness check found 126 complete journal entries, one started entry,
and **zero existing Episodic nodes for all remaining 36 deterministic episode
IDs** (including the failed target). Thus no existing graph projection needs
deletion/replacement to resume. The completed 126 entries must revalidate and be
skipped, not re-authored. Stop if completion/integrity checks fail. Verify prior
ledger-row hash and original receipt hash after completion; retain both receipts.

Use the unchanged `public_memory_fresh_graph` entry point, original shared graph
run directory and original frozen preflight, with a **new** output receipt path
`longmemeval-fresh-high-config-50-graph-scope04-recovery01-live-v1.json`.
The original durable ledger caps cumulative calls and bytes. This is one newly
authorized invocation, not an automatic retry loop. A further provider failure
stops and must remain explicit; no silent index degradation or QA on partial graph.

Network readiness: direct provider TCP and configured local proxy TCP connections
were reachable after the failure. The redacted error chain cannot uniquely prove
which endpoint refused the earlier connection; do not assert a Docker/provider
outage or rate/balance failure without evidence. No proxy/config changes are made.
