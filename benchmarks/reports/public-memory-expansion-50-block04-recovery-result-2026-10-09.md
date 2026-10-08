# Block04 transport recovery succeeded; ingestion reaches chunk354

The frozen [recovery plan](public-memory-expansion-50-block04-recovery-plan-2026-10-09.md)
replayed and validated all353 completed chunks in a fresh child checkpoint, then
retried the same pending extraction request once. The unchanged request succeeded
with no prompt/model changes. Parent artifacts remain preserved.

The resulting child checkpoint has **354/2,420 completed chunks**. Seven of the
fifty selected histories are fully ingested; an eighth is partially processed.
There are2,066 chunks left before the next block. No retrieval or QA was run.

Store audit after recovery: **3,632 raw records,1,461 derived records,16
governance records,5,467 provenance checks and zero failures**. These checks
validate references and scope/actor consistency, not semantic truth.

The recovery call reports **4,403 tokens** (3,735 input including896 cached,
668 output), with complete usage. Across the four bounded stages and two
recoveries there are **356 attempts**, including two failed transport attempts;
354 chunks are complete. Known ingestion usage sums to **1,793,134 reported
tokens**. Both failed calls have unknown usage, so this is a lower bound on
provider-reported usage, not an invoice.

Ignored result `data/doppel/longmemeval-expansion-50-block04-recovery-live-v1.json`,
SHA-256:
`c05c27293782003a925f202a1fa06067d9be174b2e16b6cef6948c9dbfc39a86`.
Recovery plan fingerprint:
`430076adcf62fbd4f033f285a922f755813db77e6c192ac8d71c8a8bb2fc667a`.
The zero-call checks, read-only parent cache and fresh SQLite journal were all
part of the frozen recovery path. This remains ingestion diagnostics, not a QA,
full-benchmark, production Planner/Graphiti or AML result.
