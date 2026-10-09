# Observation-boundary repair: opened-question regressions

Implementation and exact new preflights were committed in `f69c41b` before the
ten paid query requests. This changes a general production clock boundary, not
the question-specific algorithm, prompt, schema, ranker or gold-driven selection.
Previous receipts and scores remain intact. These are two already-opened
development questions, not two new independent successes or a benchmark score.

## Results under the repaired implementation

| Observation | First scope | Second scope |
| --- | ---: | ---: |
| Reference-only task judge | correct | correct |
| Annotated turn/session coverage | 1/1 | 2/2 |
| Supplied-context citations | 2 legal | 4 legal |
| Citation judgment | supported, no contradiction | supported, no contradiction |
| Quotation anchoring check | passed | passed |
| Reader items / bytes | 20 / 18787 | 20 / 22783 |
| CUDA pairs scored / truncated | 180 / 0 | 136 / 0 |
| Source-resolution failures | 0 | 0 |
| Returned future-observation records | 0 | 0 |
| Reader future-observation items | 0 | 0 |
| Consumed graph paths | 0 | 1 |
| Execution contract v2 | completed within bounded contract | review required |

The second query still returns Ford F-150 with both the prior Mustang record and
the explicit transition source. Its single WORKS_ON path supports an already
base-rank-1 memory: corroboration, not demonstrated discovery uplift or multi-hop
reasoning accuracy. First-query evidence comes from raw assistant messages and
is not upgraded to an owner fact. Both answers still drift into Chinese despite
English questions; retain this defect rather than marking the runs flawless.

The second run has no execution failures but retains
`unresolved current/as-of conflict in topic <unkeyed>`. It is **review_required**,
not silently green. All sources for returned candidates resolve, but bounded
top-k retrieval is not an exhaustive history scan or a recall guarantee.

## Actual repaired boundary

The original second run admitted these future-created derived candidates:

- `mem-8a3882ef87fd4708b9fe6ae68b85532e`, created June 1 at 17:50 UTC;
- `mem-be59e5e6d53843e086b4dcbdd114af90`, created June 1 at 06:06 UTC.

Its query clock was June 1 at 05:09 UTC. Packing happened not to send either to
Reader, but source backing reported two failures. The repaired run excludes both
before assembly/source resolution. Every base, hybrid, raw and backing record
and every packed `observed_at` was checked against the caller clock. Second-run
channel sizes are 57 base / 20 hybrid / 20 raw / 29 backing, all within the cutoff.
No source record, metadata, vector or graph edge was changed to make this pass.

Observation cutoff uses `now`, not historical `as_of` or administrative
`updated_at`. Synthetic tests also preserve later-learned earlier-valid facts and
known future plans. This does not reconstruct earlier versions of merged records;
an earlier-created record can contain later-added evidence, a remaining provenance/
versioning concern. Do not claim a complete bitemporal snapshot system.

## Usage, repeatability and integrity

| Paid stage | First scope tokens | Second scope tokens |
| --- | ---: | ---: |
| Two planner requests | 21671 | 23710 |
| Reader | 5073 | 6130 |
| Reference-only task judge | 487 | 624 |
| Citation judge | 6857 | 8524 |
| Total | **34088** | **38988** |

Exactly ten successful requests, **73076 reported tokens**, zero failed/interrupted
requests or missing usage. Schemas, extraction and graph projections were reused;
there was no paid reauthoring for these regressions. Exact monetary billing is not
inferred from tokens. Both empty-key, separate-process checkpoint/cache replays
match plan, retrieval, packing, context, answer, grades and checks, with three
downstream cache hits each and no added provider reservations. They are not fresh
retrieval/GPU latency samples.

| Ignored receipt in `data/doppel/` | SHA-256 |
| --- | --- |
| `public-memory-observation-regression-01-live-v1.json` | `6ef752764c68943fd2a0c986d7ca24673f73e5ae12740f053961610f3c11f670` |
| `public-memory-observation-regression-02-live-v1.json` | `a5fbe169c389abcdb910b57b47c77bbf3ea004a0ecb9753805bd24606ee5593d` |

Every query/replay preserves Store, vectors and its selected graph snapshot.
Corpus remains `11aab45f1bdfaebeea23bee822e53e5cdd94aef24f68bb020d90e9eda35e9cc3`,
with 34760 current active vectors. Complete regression: **1440 passed / 33 skipped /
3 subtests passed**, including 11 added observation-boundary cases. Repository-wide
Ruff passes. User-owned `uv.lock` remains unstaged and unchanged by this work.

The source-only third history is running under the original fixed batch contract,
not declared complete here. Its graph authoring cost is accounted separately;
its schema and natural question still require separate frozen plans. No reserved
history, all-500 expansion, AML-compliant model claim or publication gate is opened.
