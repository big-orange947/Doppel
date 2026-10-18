# Frozen source-aware ranking: three opened-case ablation

Add an opt-in existing-Reranker adapter with two independent switches: source
actor/role/authority/candidate-time metadata, and source/token MMR diversity.
No role quota, owner-only filtering, recency rule, entity alias or query keyword
policy. All returned candidates preserve original scope/text/authority/scores.
Metadata can expand remote-provider disclosure, so it is explicit host opt-in.

Three fixed arms: content-only/weight0, metadata/weight0, metadata/weight0.15.
Same local BGE model/artifact, max8192/batch1. MMR utility is0.85×relevance minus
0.15×maximum redundancy; redundancy is1 for the same scoped source, otherwise
generic lexical-token Jaccard. Ties preserve input order. Do not tune weights
after results. Fourteen new core and three driver tests pass; with passage guards,
30 targeted tests pass. Pyright reports zero errors in new core/driver files.

Fixed opened cases remain e9327a54/gpt4_ec93e27f/gpt4_2f8be40d. Reconstruct one
production BM25/vector candidate80 per question from the unchanged read-only
Store/index. Every arm receives the identical copied candidate pool. Apply its
ranking policy both to source80→20 and to at most80 source-bound passages→20.
Both stages revalidate sources; final context uses the unchanged24KB fit budget.
Maximum local scored pairs1440 across18 logical model calls. No tokenizer/model,
embedding, source expansion beyond80, graph, source writes or index migration.

Content-only source order and packed passage context must exactly reproduce
the prior frozen outputs. Prior Reader request hashes/grades must also match
before reusing them at zero new paid cost. Failure to reproduce stops the run;
no silent baseline rewrite/retry. All original corpus hashes must remain equal.

Only the preselected metadata+MMR arm receives new QA, regardless of which arm
looks better after local ranking. Freeze exact resulting contexts before calls:
at most3 Reader +3 task-judge calls, no retries; same DeepSeek flash/settings,
Reader2048/judge1024 output caps, original Reader instructions/schema. Metadata-
only remains an ungraded ablation. No grade/profile/gold enters ranking or Reader.
Keep old2/3 task grades immutable and separate old spend from new spend.

This is development on three opened public failures, not fresh independent or
official LongMemEval/AML/release performance. If promising, move to untouched
continuation rather than tuning these cases. No fragment-ID-as-answer metric.

Frozen context preflight v2 SHA-256:
`2277df5123d9bc162cc68bf923aa6d2abc1482a9070ffa8832bdc4027d4189c9`.
Plan fingerprint:
`e4b2f941e754088341089aa276c6db99c7a8f9066ed4cc6746d8e6b247eb580c`.
Unused preflight v1 remains preserved; it preceded a type-only explicit argument
fix, with no live evaluation or provider calls. Freeze current code before run.

## Context stage complete; QA frozen before paid calls

All three arms/cases complete, content-only source windows and full packed
passage contexts exactly match prior artifacts, and all three baseline Reader
request hashes/immutable grades are verified for zero-call reuse. Same candidate
pool per case, no source/index writes. Local model18 calls /1100 scored pairs /
zero truncations; no passage candidate budget exhausted. Raw provider's static
`input_policy` string describes its default content-only adapter: effective input
format in this experiment is controlled by the declared arms/source-aware wrapper
and includes metadata in the two opt-in arms.

Context output SHA-256:
`4b8cad11b8401402f5d55b6130baee4cb6acc4e916d6d66dfbfd30a27e2aa7df`.
Preselected metadata+MMR QA contexts are23608/22999/23041 bytes. More owner passages
are not scored as answer correctness. Metadata-only is not promoted to a paid arm.

QA preflight SHA-256:
`6f2cd92789c920aa21b896fa84994520e1d230971f36f07789840c7723fc7396`.
QA plan fingerprint:
`be72640beebe86482e60937c584e34c4d1544668d84f71bba5c1e39e79656c86`.
Max3 Reader plus3 task-judge calls, no retry; old baseline spend remains old.
