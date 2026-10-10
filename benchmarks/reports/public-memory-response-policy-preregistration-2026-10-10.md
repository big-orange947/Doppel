# Frozen paired response-policy diagnostic

Freeze before any paid invocation. Seven already-opened cases, in prior category
order: d52b4f67, 21d02d0d, 38146c39, gpt4_d9af6064, 3ba21379, ceb54acb,
29f2956b_abs. The newer oracle-only refusal 0862e8bf_abs has no old S context and
is excluded by availability, not outcome. Reserved cases are not evaluated.

For each case: unchanged S raw_vector_reranked packed context from the frozen
50-question experiment, and S-derived full evidence sessions from the previous
oracle diagnostic. Each receives two fresh Reader calls: unchanged Reader V2,
and grounded_advice_v1. Data, schema, clocks, provider settings are identical
within a context. Alternate policy order across contexts. No old answers/scores,
reference answers, case IDs, profiles or public categories in Reader input.

Candidate changes only the response-policy instructions: distinguish historical
recall from generating new advice, grounded in supplied personal premises but
using general knowledge for the proposal. Do not demand that a new recommendation
already appear in history; do not present a proposal as a remembered event or
preference. No domain-specific rules, graph or retrieval algorithm modifications.
Reader V2, all old caches, scores and core defaults remain unchanged.

Both arms use the unchanged reference-only DeepSeek meaning judge, blind to policy
and context profile. Citation-ID and derivation structure are checked separately;
these are NOT entailment or recommendation-quality proof. Report the original
answers/rationales, disagreements, regressions and refusal behavior, not just a
sum. Six ordinary cases (one/type) and one refusal cannot establish general
effectiveness, preference generalization or a validated judge.

S parent is a raw-vector+rereanker diagnostic, NOT the latest highest-config
Graphiti pipeline. No new extraction, graph, planner, retrieval, embedding, GPU or
Store calls. Cross-context oracle/S differences have unequal context budgets and
label-aware oracle selection; they are NOT a controlled retrieval/graph uplift.
This is development, not blind/full LongMemEval, official GPT-4o scoring or AML.

Preflight: `data/doppel/public-memory-response-policy-preflight-v1.json`
SHA-256 `c8312e2714cfc4b20346a22977e575e9e5eaf9c9febf8a39a82d7baa8f25d542`.
Plan: `49ff962acc9c137e66cdf8256371fb76e432cc529eaebc8cdbb059ae6c3776c7`.
Run directory: `data/doppel/public-memory-response-policy-paired-v1`.

At most 28 Reader + 28 judge new attempts, each canonical request <=100000 bytes,
Reader max_tokens=2048, judge=1024. Temperature=0, thinking disabled, json_object,
deepseek-v4-flash alias (not a pinned historical model version). Stop before the
next stage if observed account debit >=1 CNY, balance <=0, or balance read fails.
This is a post-spend safety stop, NOT a hard billing cap. Settlement lag or other
account activity can affect balance observations. Never print/persist API keys.

No retries, repairs, resampling, budget extensions or output overwrites. Durable
ledgers, content-addressed caches and per-stage receipts preserve failures and
interruption. Empty-key cache-only replay must match answers/grades/checks exactly.
Source files and source/manifest/comparison/quality hashes bind the frozen plan.
Old S request hashes are reconstructed before the new run to prove exact context,
question and reference-time reuse. Code/source changes require a new explicit plan.

Pre-live validation: 12 new offline synthetic protocol tests; 46 directed tests;
whole-repo Ruff passing; Pyright new module clean. Fake-provider controls verify
transport/isolation/replay, not that a real LLM follows the advice policy. No claim
of live recommendation generalization; broader controls/new heldout cases needed.
