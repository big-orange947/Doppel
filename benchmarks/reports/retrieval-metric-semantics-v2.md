# Retrieval metric semantics v2

This is an additive evaluation change, not a new retrieval result. Runtime
retrieval, ranking, existing gold labels and old hard gates are unchanged.

## Boundaries

- `forbidden` and `forbidden_hit_count` remain legacy dataset exclusions. They
  do not automatically imply security violations. Do not erase these labels
  merely because a result is inconvenient.
- Scope, provenance, authority/lifecycle and explicit temporal checks remain
  independent. The existing security and temporal gates are not relaxed.
- `abstention_accuracy` remains empty/nonempty output agreement for compatibility;
  it is not answer correctness. Answer generation is not measured by this suite.
- New per-case `evaluation_semantics` makes these limitations explicit.

## Independent relevance judgments

Optional query field `relevance_grades` maps fixture IDs to 0 (irrelevant),
1 (useful related context), or 2 (directly useful evidence). These are evaluation
labels only and are never supplied to the runtime planner or ranking system.
Review judgments against the question and memory text, independently of the
system's scores. Keep annotation rationale and reviewer decisions with future
datasets. Preserve prior dataset/report versions when reviewing legacy labels.

`graded_relevance.ndcg_at_5` uses gain `2^grade - 1` and logarithmic rank discount.
Its ideal order is relative to the explicit judgment pool, not the entire corpus.
Missing annotations are NOT implicitly irrelevant. An unjudged top-five hit,
absent judgments, or zero ideal gain yields unavailable/null. A judged query
with positive ideal gain and empty retrieval scores zero. Aggregation reports
the evaluated population and unavailable/failed count explicitly; do not compare
means across systems with different judgment coverage without completing labels.
Existing datasets are not automatically relabeled and therefore have no new
nDCG quality result yet. Empty new fields preserve old dataset fingerprints;
actual annotations change the fingerprint and invalidate bound replay inputs.

## Source accounting

Named semantic-source reasons remain preferred. For profiles with exactly one
known semantic index, a positive engine semantic score also establishes an
accepted source contribution. A profile name without a score is insufficient.
Composite sources are never guessed. Counts measure accepted-hit support, not
causal incremental recall; use paired runs to measure incremental benefit.

Relation attribution now exposes `per_mode`, including real-planner replay.
Legacy top-level link counts remain oracle-only, with `legacy_oracle_available`
explicitly indicating coverage. Modes are never silently pooled. The older
graph-direct diagnostic is still oracle-specific and is not a substitute for
real-planner relation attribution.

## Revised next steps

1. Use engine traces to inspect candidate losses and complete reviewed relevance
   labels without changing runtime filters at the same time.
2. Add an opt-in candidate-union retrieval experiment: preserve host hard relation
   constraints, treat inferred relation types as soft signals, retain independent
   vector candidates, and revalidate all sources against the authoritative Store.
3. Compare unchanged vector baseline, union, and uniform reranking; preserve all
   safety checks and report legacy/new relevance metrics side by side.
4. Freeze configuration on development data; evaluate genuinely new queries.

Evidence-support verification stays optional and disabled; it is not a required
gate for candidate union. Agent orchestration and answer generation stay outside
this development phase.
