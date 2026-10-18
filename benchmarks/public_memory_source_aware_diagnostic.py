"""Fixed three-case source-aware ablation; no automatic retries or tuning."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_context_baseline import RawHistoryHost
from benchmarks.public_context_rerank import LocalContextCrossEncoder
from benchmarks.public_memory_answer_comparison import (
    AnswerRow,
    _default_provider_factory,
    _request_sha256,
    _StageExecutor,
)
from benchmarks.public_memory_comparison import encoded, inventory, pack_ranked_fit
from benchmarks.public_memory_expansion import config, local_diagnostic_dsn, save
from benchmarks.public_memory_fresh_cohort import validate_fingerprint
from benchmarks.public_memory_high_config_first import (
    ReadOnlyStore,
    ReadOnlyVectorIndex,
)
from benchmarks.public_memory_passage_diagnostic import (
    CASES,
    SavedOrder,
    passage_item,
    reader_request,
)
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_raw_continuation import bound_items, prepare
from benchmarks.public_memory_reader_v2 import ReaderV2Output, structural_check
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_task_accuracy import Grade
from benchmarks.public_memory_task_accuracy import request as task_request
from doppel_memory.lexical import BM25RetrievalStrategy
from doppel_memory.models import MemoryFilter, MemoryState
from doppel_memory.source_aware_rerank import (
    SourceAwareRerankConfig,
    SourceAwareReranker,
)
from doppel_memory.vector import HybridRetrievalStrategy
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.contract import memory_scope
from integrations.aml.passages import AttributedPassageRetriever

RUNNER = "doppel.source-aware-opened-three.v1"
ARMS = {
    "content_only": SourceAwareRerankConfig(
        include_metadata=False, diversity_weight=0.0
    ),
    "source_metadata": SourceAwareRerankConfig(
        include_metadata=True, diversity_weight=0.0
    ),
    "source_metadata_mmr": SourceAwareRerankConfig(
        include_metadata=True, diversity_weight=0.15
    ),
}


class SavedCandidates:
    def __init__(self, candidates):
        self.candidates = candidates

    async def search(self, store, query, scopes, *, filters=None, limit=10):
        if len(scopes) != 1 or any(
            c.scope is None or c.scope.scope_key != scopes[0].scope_key
            for c in self.candidates
        ):
            raise ValueError("candidate pool escaped exact scope")
        return [c.model_copy(deep=True) for c in self.candidates[:limit]]


def make_plan(args, binding, parent, provider=None):
    value = {
        "runner": RUNNER,
        "phase": args.phase,
        "binding": binding,
        "cases": list(CASES),
        "arms": {k: v.model_dump(mode="json") for k, v in ARMS.items()},
        "schema": parent["plan"]["schema"],
        "candidate_limit": 80,
        "source_limit": 20,
        "passage_limit": 80,
        "output_limit": 20,
        "context_byte_limit": 24000,
        "source_sha256": {
            name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for name, path in {
                "wrapper": __file__,
                "source_reranker": "doppel_memory/source_aware_rerank.py",
                "passages": "integrations/aml/passages.py",
                "reader_adapter": "benchmarks/public_memory_passage_diagnostic.py",
            }.items()
        },
        "opened_not_independent": True,
        "publication_ready": False,
        "graph_calls": 0,
    }
    if provider:
        value["model"] = {
            k: v
            for k, v in provider.report().items()
            if k
            not in {
                "calls",
                "pairs_scored",
                "truncated_pairs",
                "longest_pair_tokens",
                "device_actual",
            }
        }
        if value["model"] != parent["plan"]["reranker"]:
            raise ValueError("frozen local model changed")
        value["max_local_pairs"] = 1440
    if args.phase == "answers":
        value["tested_arm"] = "source_metadata_mmr"
        value["reused_arm"] = "content_only"
        value["stages"] = {
            name: {"max_calls": 3, "config": config(tokens).model_dump(mode="json")}
            for name, tokens in (("reader", 2048), ("task_judge", 1024))
        }
    else:
        value["llm_calls"] = 0
    return {**value, "plan_fingerprint": _hash(value)}


def reused_baseline(row, prepared, old_contexts, old_qa):
    previous = next(
        r
        for r in old_contexts["rows"]
        if r["case_id"] == row["case_id"]
        and r["profile"] == "saved_source_passages_fit"
    )
    if previous["context"] != row["context"]:
        raise ValueError("content-only passage baseline changed")
    old = next(
        r
        for r in old_qa["rows"]
        if r["case_id"] == row["case_id"]
        and r["profile"] == "saved_source_passages_fit"
    )
    runtime, scoring = prepared
    answer_row = AnswerRow(
        0, row["case_id"], "content_only", runtime, scoring, tuple(row["context"])
    )
    if old["reader"]["request_sha256"] != _request_sha256(
        reader_request(answer_row)
    ) or not old.get("grade"):
        raise ValueError("baseline Reader request/grade binding changed")
    return {
        **old,
        "profile": "content_only",
        "reused_immutable_result": True,
        "new_calls": 0,
    }


async def contexts(
    args, selected, manifest, parent, old_contexts, old_qa, provider, plan
):
    save(
        args.run_dir / "contexts-attempt.json",
        {"plan_fingerprint": plan["plan_fingerprint"]},
    )
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"), schema=plan["schema"]
    )
    index = ReadOnlyVectorIndex(store, _LocalEmbeddingProvider(cache_dir=None))
    rows, baselines, certificates = [], [], []
    try:
        for runtime, scoring in selected:
            scope = memory_scope(manifest["run_namespace"], runtime.user_id)
            records = await inventory(store, [scope])
            digest = _hash({k: r.model_dump(mode="json") for k, r in records.items()})
            receipt = next(
                r for r in parent["receipts"] if r["case_id"] == scoring.case_id
            )
            if digest != receipt["corpus_sha256"]:
                raise ValueError("original Store changed")
            host = RawHistoryHost(store)
            host.sources = {
                (scope.scope_key, r.source_event_id): r.memory_id
                for r in records.values()
            }
            raw_items = bound_items(runtime, manifest, scope, host, records)
            if any(i is None for i in raw_items.values()):
                raise ValueError("unclassified raw source")
            items = {k: i for k, i in raw_items.items() if i is not None}
            hybrid = HybridRetrievalStrategy(
                index,
                lexical_strategy=BM25RetrievalStrategy(),
                candidate_multiplier=1,
                fallback_to_lexical=False,
            )
            pool = list(
                await hybrid.search(
                    store,
                    runtime.query.query,
                    [scope],
                    filters=MemoryFilter(states={MemoryState.CONFIRMED}),
                    limit=80,
                )
            )
            candidate_hash = _hash([c.model_dump(mode="json") for c in pool])
            case_rows = []
            for arm, settings in ARMS.items():
                scorer = SourceAwareReranker(provider, settings)
                source_result = await AttributedContextRetriever(
                    store,
                    strategy=SavedCandidates(pool),
                    resolve_event=host.resolve_event,
                    reranker=scorer,
                ).search(scope, runtime.query.query, limit=20)
                if arm == "content_only":
                    old = next(
                        r
                        for r in parent["rows"]
                        if r["case_id"] == scoring.case_id
                        and r["profile"] == "raw_bm25_vector_reranked"
                    )
                    expected = [
                        items[tuple(p)]["memory_id"]
                        for p in old["retrieved_source_positions"]
                    ]
                    if [s.memory_id for s in source_result.snippets] != expected:
                        raise ValueError("content-only source order did not reproduce")
                source_parent = AttributedContextRetriever(
                    store,
                    strategy=SavedOrder(
                        scope, [s.memory_id for s in source_result.snippets]
                    ),
                    resolve_event=host.resolve_event,
                )
                result = await AttributedPassageRetriever(
                    source_parent, reranker=scorer
                ).search(scope, runtime.query.query, limit=20)
                resolver = AttributedPassageRetriever(source_parent)
                for p in result.passages:
                    await resolver.resolve_original(scope, p)
                packed, trace = pack_ranked_fit(
                    [passage_item(p) for p in result.passages]
                )
                row = {
                    "case_id": scoring.case_id,
                    "profile": arm,
                    "candidate_pool_sha256": candidate_hash,
                    "context": packed,
                    "context_bytes": len(encoded(packed)),
                    "context_sha256": hashlib.sha256(encoded(packed)).hexdigest(),
                    "source_events": [s.evidence_id for s in source_result.snippets],
                    "source_actor_counts": {
                        actor: sum(s.actor == actor for s in source_result.snippets)
                        for actor in {s.actor for s in source_result.snippets}
                    },
                    "passage_execution": result.model_dump(
                        mode="json", exclude={"passages"}
                    ),
                    "packing_trace": trace,
                    "annotated_span_answer_recall": None,
                }
                if arm == "content_only":
                    baselines.append(
                        reused_baseline(row, (runtime, scoring), old_contexts, old_qa)
                    )
                case_rows.append(row)
            after = await inventory(store, [scope])
            if digest != _hash(
                {k: r.model_dump(mode="json") for k, r in after.items()}
            ):
                raise ValueError("read-only Store changed during comparison")
            save(
                args.run_dir / f"context-{scoring.case_id}.json",
                {"rows": case_rows, "plan_fingerprint": plan["plan_fingerprint"]},
            )
            rows.extend(case_rows)
            certificates.append({"case_id": scoring.case_id, "corpus_sha256": digest})
            print(f"completed three arms {scoring.case_id}", flush=True)
    finally:
        await store.close()
    return {
        "status": "complete",
        "rows": rows,
        "reused_baselines": baselines,
        "source_certificates": certificates,
        "model_usage": provider.report(),
        "llm_calls": 0,
    }


async def answers(args, selected, report, plan):
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        raise ValueError("provider key absent")
    save(
        args.run_dir / "answers-attempt.json",
        {"plan_fingerprint": plan["plan_fingerprint"]},
    )
    prepared = {s.case_id: (r, s) for r, s in selected}
    selected_rows = [r for r in report["rows"] if r["profile"] == "source_metadata_mmr"]
    if len(selected_rows) != 3:
        raise ValueError("exactly three preregistered candidate QA rows required")
    ledgers, stages, rows = {}, {}, []
    try:
        for name, tokens, schema in (
            ("reader", 2048, ReaderV2Output),
            ("task_judge", 1024, Grade),
        ):
            ledger = DurableCallLedger(
                args.run_dir / "usage.sqlite3",
                budget_id=plan["plan_fingerprint"] + ":" + name,
                max_calls=3,
                max_request_bytes=100000,
                max_total_request_bytes=300000,
            )
            ledgers[name] = ledger
            if ledger.report()["attempts_reserved"]:
                raise ValueError("preserve prior attempts")
            model = PilotStructuredModel(
                _default_provider_factory(
                    config(tokens), os.environ["DEEPSEEK_API_KEY"], ledger.observe_usage
                ),
                ledger=ledger,
                cache_dir=args.run_dir / name,
            )
            stages[name] = _StageExecutor(model, ledger, schema, cache_only=False)
        for i, item in enumerate(selected_rows):
            row = AnswerRow(
                i,
                item["case_id"],
                item["profile"],
                *prepared[item["case_id"]],
                tuple(item["context"]),
            )
            output, reader_record = await stages["reader"].execute(
                reader_request(row), i
            )
            entry = {
                "case_id": row.case_id,
                "profile": row.profile,
                "reader": reader_record,
                "reader_output": output.model_dump(mode="json") if output else None,
            }
            if output:
                grade, judge_record = await stages["task_judge"].execute(
                    task_request(
                        row.runtime.query.query, row.scoring.answer, output.answer
                    ),
                    i,
                )
                entry.update(
                    checks=structural_check(row, output),
                    task_judge=judge_record,
                    grade=grade.model_dump(mode="json") if grade else None,
                )
            rows.append(entry)
            save(args.run_dir / f"answer-{i}.json", entry)
            if output is None or not entry.get("grade"):
                break
        return {
            "status": "complete"
            if len(rows) == 3 and all(r.get("grade") for r in rows)
            else "failed",
            "rows": rows,
            "reused_baselines": report["reused_baselines"],
            "usage": {k: v.report() for k, v in ledgers.items()},
        }
    finally:
        for ledger in ledgers.values():
            ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("contexts", "answers"), required=True)
    for name in (
        "dataset",
        "manifest",
        "parent-report",
        "old-contexts",
        "old-qa",
        "run-dir",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--reranker-model", type=Path)
    parser.add_argument("--context-report", type=Path)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("fresh output required")
    content = {
        k: getattr(args, k).read_bytes()
        for k in ("dataset", "manifest", "parent_report", "old_contexts", "old_qa")
    }
    binding = {k: hashlib.sha256(v).hexdigest() for k, v in content.items()}
    all_cases, manifest = prepare(
        json.loads(content["dataset"]),
        json.loads(content["manifest"]),
        binding["dataset"],
    )
    selected = [next(c for c in all_cases if c[1].case_id == key) for key in CASES]
    parent, old_contexts, old_qa = (
        json.loads(content[k]) for k in ("parent_report", "old_contexts", "old_qa")
    )
    for report in (parent, old_contexts, old_qa):
        validate_fingerprint(report["plan"], "plan_fingerprint")
        if report["status"] != "complete":
            parser.error("complete frozen parents required")
    if (
        parent["plan"]["manifest"] != manifest
        or old_qa["plan"]["binding"]["contexts"] != binding["old_contexts"]
    ):
        parser.error("parent binding changed")
    provider, context_report = None, None
    if args.phase == "contexts":
        provider = LocalContextCrossEncoder(
            args.reranker_model, device="cuda", max_length=8192, batch_size=1
        )
    else:
        data = args.context_report.read_bytes()
        binding["contexts"] = hashlib.sha256(data).hexdigest()
        context_report = json.loads(data)
        validate_fingerprint(context_report["plan"], "plan_fingerprint")
        if context_report["status"] != "complete" or context_report["plan"][
            "binding"
        ] != {k: binding[k] for k in content}:
            parser.error("context binding changed")
        for row in context_report["rows"]:
            if (
                len(encoded(row["context"])) > 24000
                or hashlib.sha256(encoded(row["context"])).hexdigest()
                != row["context_sha256"]
            ):
                parser.error("context bytes changed")
    plan = make_plan(args, binding, parent, provider)
    result = {"runner": RUNNER, "status": "ready", "plan": plan, "graph_calls": 0}
    if args.execute:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            parser.error("matching frozen preflight required")
        result.update(
            asyncio.run(
                contexts(
                    args,
                    selected,
                    manifest,
                    parent,
                    old_contexts,
                    old_qa,
                    provider,
                    plan,
                )
                if args.phase == "contexts"
                else answers(args, selected, context_report, plan)
            )
        )
    save(args.output, result)
    print(json.dumps({"status": result["status"], "phase": args.phase}))


if __name__ == "__main__":
    main()
