# Fixed-top20 context budget curve: packing is only part of the loss

Zero-model replay of all50 opened diagnostic histories. Fixed before execution:
both saved candidate80/160 arms, complete ordered top20, whole-item ranked-fit,
item limit20, and byte caps24000/48000/96000. These are **decimal UTF-8 JSON
bytes**, not KiB, tokens or model context-window sizes. No text truncation,
metadata factoring, expansion, source/role preference, query-dependent rule,
retrieval, embedding, reranking, LLM, API-key access or DB operation.

## Results

Positive-only denominators:43 answerable questions/76 annotated original turns.
Seven negative cases remain in footprint totals, not positive recall counts.
All100 arm/case24KB contexts and packing traces reproduce saved results exactly;
the80 arm also binds to all50 frozen historical QA context hashes.

| Candidate window | Byte cap | Packed annotations | Complete positives | Items, all50 | Mean actual JSON bytes/query |
|---|---:|---:|---:|---:|---:|
|80|24000|60/76 (78.9%)|36/43|574|23532.8|
|80|48000|64/76 (84.2%)|38/43|970|40423.7|
|80|96000|66/76 (86.8%)|38/43|1000|41775.8|
|160|24000|56/76 (73.7%)|34/43|490|23625.4|
|160|48000|59/76 (77.6%)|36/43|880|45010.6|
|160|96000|59/76 (77.6%)|36/43|1000|51575.7|

For80,48KB recovers4 annotations across3 questions (20/37/44);96KB recovers6
across4 (20/37/40/44), relative to24KB. Neither displaces any baseline annotation
in this corpus. The two additional annotations at96KB belong to question40,
which still lacks another annotation outside top20; complete-positive count
therefore remains38/43.160 recovers3 annotations at48KB (13/26/37), no further
annotations at96KB. No observed annotation displacements in either160 comparison.

In the frozen QA,20 (preference) and37 (temporal) were already correct;40
(multi-session) and44 (temporal) were incorrect. Four questions with recovered
annotations must not be presented as four recovered correct answers. Extra
non-annotated context can also change answers in either direction, so a later
QA comparison must retain all50 rather than cherry-pick these four cases.

The greedy policy is **not mathematically monotonic**: a previously skipped early
long item can fit at a larger cap and displace later items. Tests explicitly
exercise this behavior; results record gains and losses rather than assuming
that increased capacity always retains previous evidence.

## What the loss decomposition says

At80/24KB,16 of76 annotations are not delivered:

- **4 never enter candidate80.** Changing only context capacity cannot recover them.
- **6 enter candidate80 but miss top20.** Changing only packing cannot recover them.
- **6 reach top20 but are skipped at24KB.** All6 fit by96KB.

At96KB every source in top20 fits in every case for both arms. Maximum actual
context is63766 bytes at80 and78051 at160, not96000. The remaining10 annotations
at80 and17 at160 are outside their respective top20; there is no additional
packing capacity to exploit without changing the source-selection stage.

Increasing the80 cap from24KB to48KB raises actual serialized footprint71.8%;
to96KB raises it77.5%. Going from48KB to96KB adds only3.3% actual average bytes
on this specific corpus because most top20 lists already fit. These are resource
tradeoffs, **not same-budget algorithm improvements**, token/cost estimates or
latency measurements. More irrelevant text can also hurt downstream answering.

Even160/96KB delivers fewer annotations than80/24KB (59 versus60). Its poor
delivery in the previous ablation is not merely a too-small context cap. Do not
promote candidate160, add actor/length quotas, or filter historical assistants.

## Boundaries and next decision

**Historical end-to-end QA remains37/50.** This run changes no answers, grades,
Reader, service defaults or public wire format. Annotation coverage is neither
answer accuracy nor evidence sufficiency; annotations are not exhaustive. These
are already-opened development cases, not an independent/blind sample, an official
LongMemEval500 result, AML score or publication/release gate.

Next useful experiment is downstream QA under a frozen Reader and scoring rule,
not more corpus generation or eager paid graph construction. Keep candidate80
and compare resource caps explicitly; reuse existing24KB answers and deduplicate
identical48/96KB inputs.40 positive/7 negative48KB contexts differ from24KB;
another9 positive/2 negative96KB contexts differ from48KB. Thus58 new unique
contexts at most, not100 new Reader requests, if both enlarged caps are tested
on all50. Judge calls also need their own fixed cap and cache identity. No such
new QA has run or been charged here. Answer effects and additional input spend
must be reported together before any default-budget promotion.

For subsequent retrieval work, the real remaining questions concern candidate
discovery and source ordering, not adding capacity forever. Do not claim that a
particular reranker replacement solves them without a controlled comparison.

## Reproduction and integrity

```powershell
cd D:\project\Doppel
.\.venv\Scripts\python.exe -m benchmarks.public_memory_context_budget
```

No Docker, optional model dependencies or API key needed. Existing output is
never overwritten; use a new `--output` path for an additional replay. The command
pins all three input file hashes, the parent plan fingerprint, parent/QA bindings,
and original24KB contexts/traces, and checks input bytes again after replay.
Source objects retain their original text, actor, role, authority, timestamps,
scope, memory ID and provenance. Output IDs/digests refer to those unchanged
full objects, not reconstructed excerpts. Selection never receives annotations.

Inputs (ignored local artifacts, unchanged):

- `window-ablation-live-v1.json`:
  d43c29bde9ce4a4d392db97e0e464aea1ce6177f7bfbdf64c03bfbbe4f61c906.
- `window-ablation-plan-v1.json`:
  f45b41b7f146bd1bcba90103fe40b026b4d8ac1a036d9191d02031b271f95c0d.
- `uniform-qa-fifty-summary-v1.json`:
  a5ecbc7c038a072eb69e73d5024fd53f3ec92800a5aec8c1bbeedd95c7ad8408.

Output `data/doppel/context-budget-curve-v1.json`, SHA-256:
90dfb893ec72a8a821be2e86d39b4cf100f0bc1140f905949cb4f265d59d536b.
The artifact records parent HEADae9bd2b plus the exact uncommitted runner content
hash at execution; the runner/tests are committed with this report, not falsely
claimed to have existed in the parent commit. Paid/model/retrieval calls and
source writes all0.16 new offline tests cover original policy reproduction,
UTF-8/item/exact-fit caps, invalid budgets, corruption/scope rejection, positive
denominators, annotation-independent selection and greedy-budget displacement.
An independent new-path replay produces the exact same report bytes and SHA-256.
Final integrity check confirms runner content hash and every input hash still
match. Full suite **2279 passed,33 skipped,3 subtests**,265.96s, one existing
optional Graphiti/Pydantic deprecation warning; Ruff repository check and touched
file formatting pass, runner Pyright0 errors/warnings. Existing uv.lock remains
untouched and unstaged (preexisting1025 additions/1025 deletions).
