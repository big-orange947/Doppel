# One user-approved recovery, no experiment policy change

Original run stopped on ordinal3/fusion Reader: HTTP200/finish=stop with invalid
content JSON. Reader3 attempts (2 succeeded/1 failed), judge2 succeeded; complete
usage includes the failed response. Original report SHA-256:
bf7abffe0e9b79c2522568c5d31c5d1b584059c07fda078046d4061c7d380aeb.
Preserve its checkpoints, caches, ledger and failed result; do not rewrite/relabel.

The user explicitly approved ONE recovery: unchanged model/prompts/config/requests
and decision, cumulative Reader cap51 instead of50, judge remains50. Subtract
prior reservations: recovery caps48 Reader/48 judge. Read-only parent success
caches reuse the two completed answers/grades; retry only the uncached failed
request once, then execute remaining first attempts. Any further failure stops;
no automatic retry or recursive recovery. Exact original failure-report hash
binds the supplement. Code change is orchestration only, with unchanged shared
Reader/judge dependency hashes verified. Commit before new preflight/calls.

```powershell
.\.venv\Scripts\python.exe -m benchmarks.public_memory_rank_fusion_qa --recover-from data/doppel/rank-fusion-qa-live-v1.json --output data/doppel/rank-fusion-qa-recovery-frozen-v1.json
.\.venv\Scripts\python.exe -u -m benchmarks.public_memory_rank_fusion_qa --execute --recover-from data/doppel/rank-fusion-qa-live-v1.json --cache-parent data/doppel/rank-fusion-qa-live-v1 --frozen-preflight data/doppel/rank-fusion-qa-recovery-frozen-v1.json --run-dir data/doppel/rank-fusion-qa-recovery-v1 --output data/doppel/rank-fusion-qa-recovery-v1.json
```

Accounting must aggregate both identities, including the failed paid response.
This is not a fresh budget or cost refund. No reserved history preparation until
the complete100-row comparison chooses a configuration under the original rule.
