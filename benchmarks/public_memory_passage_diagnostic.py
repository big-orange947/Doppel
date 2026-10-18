"""Three opened failures: immutable source windows, optional bounded Reader QA."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from benchmarks.public_context_baseline import RawHistoryHost
from benchmarks.public_context_rerank import (
    LocalContextCrossEncoder,
    StrictContextReranker,
)
from benchmarks.public_memory_answer_comparison import (
    AnswerRow,
    _default_provider_factory,
    _StageExecutor,
)
from benchmarks.public_memory_comparison import encoded, inventory, pack_ranked_fit
from benchmarks.public_memory_expansion import config, local_diagnostic_dsn, save
from benchmarks.public_memory_fresh_cohort import validate_fingerprint
from benchmarks.public_memory_high_config_first import ReadOnlyStore
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_raw_continuation import bound_items, prepare
from benchmarks.public_memory_reader_v2 import (
    ReaderV2Output,
    build_request,
    structural_check,
)
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_task_accuracy import Grade
from benchmarks.public_memory_task_accuracy import request as task_request
from doppel_memory.models import RecallResult
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.contract import memory_scope
from integrations.aml.passages import AttributedPassageRetriever, PassageRetrievalConfig

RUNNER = "doppel.opened-three-passage-diagnostic.v1"
CASES = ("e9327a54", "gpt4_ec93e27f", "gpt4_2f8be40d")


class SavedOrder:
    def __init__(self, scope, ids):
        self.scope, self.ids = scope, ids

    async def search(self, store, query, scopes, *, filters=None, limit=10):
        if len(scopes) != 1 or scopes[0] != self.scope:
            raise ValueError("saved order escaped source scope")
        return [
            RecallResult(
                scope=self.scope,
                memory_id=key,
                fact="not-trusted",
                similarity=1 / (rank + 1),
            )
            for rank, key in enumerate(self.ids[:limit])
        ]


def passage_item(p):
    return {
        "channel": "raw",
        "memory_id": p.passage_id,
        "scope_key": p.scope_key,
        "role": p.role,
        "actor": p.actor,
        "authority": p.authority.value,
        "text": p.text,
        "observed_at": p.at.isoformat(),
        "temporal_status": None,
        "valid_from": None,
        "valid_to": None,
        "source_events": [p.evidence_id],
        "source_memory_id": p.memory_id,
        "excerpt": True,
        "source_span": {
            "start": p.start,
            "end": p.end,
            "offset_unit": p.offset_unit,
            "source_char_count": p.source_char_count,
            "source_text_sha256": p.source_text_sha256,
        },
    }


def reader_request(row):
    request = build_request(row)
    # Explicit original/excerpt metadata is supplied symmetrically; existing
    # Reader instructions/output schema are unchanged and gold is never included.
    return request.model_copy(
        update={
            "input": {
                **request.input,
                "context_items": [dict(item) for item in row.context],
            }
        }
    )


def plan_for(args, binding, parent, reranker=None):
    value = {
        "runner": RUNNER,
        "phase": args.phase,
        "binding": binding,
        "parent_plan_fingerprint": parent["plan"]["plan_fingerprint"],
        "cases": list(CASES),
        "opened_diagnostic_not_blind": True,
        "profiles": ["saved_whole_message_fit", "saved_source_passages_fit"],
        "context_byte_limit": 24000,
        "item_limit": 20,
        "passages": PassageRetrievalConfig().model_dump(),
        "source_sha256": {
            name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for name, path in {
                "wrapper": __file__,
                "splitter": "doppel_memory/passages.py",
                "adapter": "integrations/aml/passages.py",
                "reader": "benchmarks/public_memory_reader_v2.py",
                "judge": "benchmarks/public_memory_task_accuracy.py",
            }.items()
        },
        "graph_calls": 0,
        "publication_ready": False,
    }
    if reranker:
        value["reranker"] = {
            k: v
            for k, v in reranker.report().items()
            if k
            not in {
                "device_actual",
                "calls",
                "pairs_scored",
                "truncated_pairs",
                "longest_pair_tokens",
            }
        }
        if value["reranker"] != parent["plan"]["reranker"]:
            raise ValueError("unchanged local reranker required")
    if args.phase == "answers":
        value["stages"] = {
            "reader": {"max_calls": 6, "config": config(2048).model_dump(mode="json")},
            "task_judge": {
                "max_calls": 6,
                "config": config(1024).model_dump(mode="json"),
            },
        }
    else:
        value["llm_calls"] = 0
    return {**value, "plan_fingerprint": _hash(value)}


async def contexts(args, selected, manifest, parent, reranker, plan):
    marker = args.run_dir / "contexts-attempt.json"
    save(marker, {"plan_fingerprint": plan["plan_fingerprint"]})
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"),
        schema=parent["plan"]["schema"],
    )
    rows, certificates = [], []
    try:
        for runtime, scoring in selected:
            scope = memory_scope(manifest["run_namespace"], runtime.user_id)
            records = await inventory(store, [scope])
            before = _hash({k: r.model_dump(mode="json") for k, r in records.items()})
            receipt = next(
                r for r in parent["receipts"] if r["case_id"] == scoring.case_id
            )
            if before != receipt["corpus_sha256"]:
                raise ValueError("original source inventory changed")
            host = RawHistoryHost(store)
            host.sources = {
                (scope.scope_key, r.source_event_id): r.memory_id
                for r in records.values()
            }
            items = bound_items(runtime, manifest, scope, host, records)
            old = next(
                r
                for r in parent["rows"]
                if r["case_id"] == scoring.case_id
                and r["profile"] == "raw_bm25_vector_reranked"
            )
            ranked = [items[tuple(p)] for p in old["retrieved_source_positions"]]
            whole, _ = pack_ranked_fit(ranked)
            if (
                hashlib.sha256(encoded(whole)).hexdigest()
                != old["packing"]["ranked_fit"]["packed_context_sha256"]
            ):
                raise ValueError("whole-message context not exactly reproduced")
            source = AttributedContextRetriever(
                store,
                strategy=SavedOrder(scope, [i["memory_id"] for i in ranked]),
                resolve_event=host.resolve_event,
            )
            retriever = AttributedPassageRetriever(
                source, reranker=StrictContextReranker(reranker)
            )
            result = await retriever.search(scope, runtime.query.query, limit=20)
            for passage in result.passages:
                await retriever.resolve_original(scope, passage)
            fragments, trace = pack_ranked_fit(
                [passage_item(p) for p in result.passages]
            )
            for profile, context in (
                ("saved_whole_message_fit", whole),
                ("saved_source_passages_fit", fragments),
            ):
                row = {
                    "index": len(rows),
                    "case_id": scoring.case_id,
                    "profile": profile,
                    "context": context,
                    "context_bytes": len(encoded(context)),
                    "context_sha256": hashlib.sha256(encoded(context)).hexdigest(),
                    "span_answer_support_recall": None,
                }
                if profile == "saved_source_passages_fit":
                    row.update(
                        passage_execution=result.model_dump(
                            mode="json", exclude={"passages"}
                        ),
                        packing_trace=trace,
                    )
                rows.append(row)
            after = await inventory(store, [scope])
            if before != _hash(
                {k: r.model_dump(mode="json") for k, r in after.items()}
            ):
                raise ValueError("read-only source inventory changed")
            certificates.append({"case_id": scoring.case_id, "corpus_sha256": before})
            print(f"prepared contexts {scoring.case_id}", flush=True)
    finally:
        await store.close()
    return {
        "status": "complete",
        "rows": rows,
        "source_certificates": certificates,
        "reranker": reranker.report(),
        "llm_calls": 0,
        "provider_tokens": 0,
    }


async def answers(args, selected, context_report, plan):
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        raise ValueError("configure key in environment; never in report")
    save(
        args.run_dir / "answers-attempt.json",
        {"plan_fingerprint": plan["plan_fingerprint"]},
    )
    by_id = {s.case_id: (r, s) for r, s in selected}
    rows = [
        AnswerRow(
            r["index"],
            r["case_id"],
            r["profile"],
            *by_id[r["case_id"]],
            tuple(r["context"]),
        )
        for r in context_report["rows"]
    ]
    ledgers, stages, results = {}, {}, []
    try:
        for name, output in (("reader", ReaderV2Output), ("task_judge", Grade)):
            ledger = DurableCallLedger(
                args.run_dir / "usage.sqlite3",
                budget_id=plan["plan_fingerprint"] + ":" + name,
                max_calls=6,
                max_request_bytes=100000,
                max_total_request_bytes=600000,
            )
            ledgers[name] = ledger
            if ledger.report()["attempts_reserved"]:
                raise ValueError("preserve previous attempts; no silent rerun")
            model = PilotStructuredModel(
                _default_provider_factory(
                    config(2048 if name == "reader" else 1024),
                    os.environ["DEEPSEEK_API_KEY"].strip(),
                    ledger.observe_usage,
                ),
                ledger=ledger,
                cache_dir=args.run_dir / name,
            )
            stages[name] = _StageExecutor(model, ledger, output, cache_only=False)
        for row in rows:
            output, reader_record = await stages["reader"].execute(
                reader_request(row), row.index
            )
            entry = {
                "index": row.index,
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
                    row.index,
                )
                entry.update(
                    checks=structural_check(row, output),
                    task_judge=judge_record,
                    grade=grade.model_dump(mode="json") if grade else None,
                )
            results.append(entry)
            save(args.run_dir / f"answer-row-{row.index}.json", entry)
            print(f"answer {row.index + 1}/6", flush=True)
            if output is None or not entry.get("grade"):
                break
        return {
            "status": "complete"
            if len(results) == 6 and all(r.get("grade") for r in results)
            else "failed",
            "rows": results,
            "usage": {k: v.report() for k, v in ledgers.items()},
        }
    finally:
        for ledger in ledgers.values():
            ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("contexts", "answers"), required=True)
    for name in ("dataset", "manifest", "parent-report", "run-dir", "output"):
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
        for k in ("dataset", "manifest", "parent_report")
    }
    binding = {k: hashlib.sha256(v).hexdigest() for k, v in content.items()}
    cases, manifest = prepare(
        json.loads(content["dataset"]),
        json.loads(content["manifest"]),
        binding["dataset"],
    )
    parent = json.loads(content["parent_report"])
    validate_fingerprint(parent["plan"], "plan_fingerprint")
    if parent["status"] != "complete" or parent["plan"]["manifest"] != manifest:
        parser.error("unchanged completed next-ten report required")
    selected = [next(c for c in cases if c[1].case_id == key) for key in CASES]
    reranker, context_report = None, None
    if args.phase == "contexts":
        reranker = LocalContextCrossEncoder(
            args.reranker_model, device="cuda", max_length=8192, batch_size=1
        )
    else:
        data = args.context_report.read_bytes()
        binding["contexts"] = hashlib.sha256(data).hexdigest()
        context_report = json.loads(data)
        if context_report["status"] != "complete" or len(context_report["rows"]) != 6:
            parser.error("complete six-row context report required")
        if context_report["plan"]["binding"] != {
            k: binding[k] for k in ("dataset", "manifest", "parent_report")
        }:
            parser.error("context source binding changed")
        for row in context_report["rows"]:
            if (
                len(encoded(row["context"])) > 24000
                or hashlib.sha256(encoded(row["context"])).hexdigest()
                != row["context_sha256"]
            ):
                parser.error("context bytes/hash changed")
    plan = plan_for(args, binding, parent, reranker)
    report = {
        "runner": RUNNER,
        "status": "ready",
        "plan": plan,
        "graph_calls": 0,
        "qa_metrics_available": args.phase == "answers",
    }
    if args.execute:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            parser.error("matching frozen preflight required")
        report.update(
            asyncio.run(
                contexts(args, selected, manifest, parent, reranker, plan)
                if args.phase == "contexts"
                else answers(args, selected, context_report, plan)
            )
        )
    save(args.output, report)
    print(json.dumps({"status": report["status"], "phase": args.phase}))


if __name__ == "__main__":
    main()
