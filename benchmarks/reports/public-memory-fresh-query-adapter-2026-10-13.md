# Frozen fresh-cohort query execution supplement

The adapter `public_memory_fresh_query` reuses the existing production
`HighConfigRetrieval` composition, natural V7 two-pass planner, evidence-rich V8
context assembly, Reader v2, reference-only task judge and citation judge.
It adds no algorithm, answering policy, domain rule, prompt revision or new sample.
Nine synthetic offline tests validate the operational adapter; they are not a new
live judge/reader qualification campaign. They make zero external model calls.

Each selected question is gated on an immutable complete **scope-local** source
and graph receipt. The partial whole-cohort report is never relabelled complete.
Every graph target must still resolve to the authoritative Store, every source
turn must bind to its original journal record, and every active vector must be
current. Schema definitions come from distinct source relation names only.

After those gates, open only the selected actual question/reference pair in the
frozen case order. Rebuild and compare all provider/retrieval configurations with
the cohort plan. Bind actual local reranker weights, source-only schema, source
snapshot, query hash, stage budgets and adapter source hash in the query preflight
before paid QA. No questions/gold enter the graph construction or schema authoring.

Two profiles only:

- `full_high_config`: natural planner, lexical/vector/typed graph/path retrieval,
  local CUDA BGE reranker, separate raw dialogue and source backing, unchanged
  whole-item memory/raw/backing cyclic assembly, twenty items / 24,000 UTF-8 bytes.
- `raw_vector_reranked`: existing strong original-attributed-message vector
  ordering, eighty candidates, same local reranker, twenty whole ranked-prefix
  items / 24,000 UTF-8 bytes. It does not invoke a query planner or a graph writer.

Alternate execution order by fixed one-based source ordinal. Full permits two
planner calls plus one Reader, one task judge and one citation judge; raw permits
one call to each of those three answer/scoring stages. Exactly eight attempts at
most per complete question pair, no automatic retry. Persist retrieval and model
stage checkpoints, including failures; cache-only replay cannot silently rerun a
retrieval. Bind each provider's exact frozen configuration rather than rebuilding
it from an unverified model/token alias. Store and vector access is read-only;
verify source journal, corpus, vectors and graph after execution.

Do not treat a degraded/missing graph as a successful highest-config run. Report
execution completeness separately from provisional answer quality and evidence
coverage. Do not revise core/config/prompts after seeing this cohort's answers.
The prior opened vector-only sample, oracle diagnostics and failed analyzer
promotion controls remain separate. Final cohort denominator remains fifty;
completed/scored denominators must also be disclosed as blocks become available.

This code commit precedes the first new-cohort question opening and paid QA.
The actual per-question plan and source-only schema budgets are frozen separately
after the first graph completes. No official GPT-4o judge or AML claim is made.
