"""One locked reserved10 run: local raw ingestion/contexts, then bounded QA.

No ranking/model/prompt selection on reserved results, and no old schema reset.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import subprocess
from pathlib import Path

from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_context_baseline import RawHistoryHost
from benchmarks.public_context_rerank import (
    LocalContextCrossEncoder,
    StrictContextReranker,
)
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_answer_comparison import (
    AnswerRow,
    _default_provider_factory,
    _request_sha256,
    _StageExecutor,
)
from benchmarks.public_memory_comparison import encoded, inventory, pack_ranked_fit
from benchmarks.public_memory_context_budget import sha
from benchmarks.public_memory_context_budget_qa import STAGES, write_new
from benchmarks.public_memory_expansion import config, local_diagnostic_dsn
from benchmarks.public_memory_fresh_cohort import validate_fingerprint
from benchmarks.public_memory_high_config_first import ReadOnlyStore
from benchmarks.public_memory_listwise_diagnostic import request_bytes
from benchmarks.public_memory_passage_diagnostic import reader_request
from benchmarks.public_memory_pilot import _hash, history_group
from benchmarks.public_memory_prospective_selection import bind_host, model_identity
from benchmarks.public_memory_rank_fusion_qa import summarize as selection_summary
from benchmarks.public_memory_raw_continuation import bound_items
from benchmarks.public_memory_reader_v2 import structural_check
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_task_accuracy import request as task_request
from benchmarks.public_memory_uniform_qa import digest
from benchmarks.public_memory_window_ablation import vector_receipt
from doppel_memory.lexical import BM25RetrievalStrategy
from doppel_memory.postgres_store import PostgreSQLStore
from doppel_memory.rank_fusion import RankFusionReranker, rank_fusion_order
from doppel_memory.vector import (
    HybridRetrievalStrategy,
    PostgreSQLVectorIndex,
    VectorIndexConfig,
)
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.contract import memory_scope

ROOT = Path("data/doppel")
FILES = {
    "selection": ROOT / "rank-fusion-qa-recovery-v1.json",
    "manifest": ROOT / "longmemeval-fresh-high-config-50-manifest-v1.json",
    "dataset": Path("data/public-benchmarks/longmemeval_s_cleaned.json"),
    "window": ROOT / "window-ablation-live-v1.json",
    "fusion": ROOT / "rank-fusion-local-v1.json",
}
PINS = {
    "selection": "24a8bf0c56d421d969c91c0d5eaaa85278e7e48a874d45fbc2ba8cbadd420991",
    "manifest": "661f72949426cde42855bdfa69ea23dcc3062bd6e636f80fea44731e9b651ab5",
    "dataset": "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442",
    "window": "d43c29bde9ce4a4d392db97e0e464aea1ce6177f7bfbdf64c03bfbbe4f61c906",
    "fusion": "6e6b8c911ace18b75fe8a0d64efa9c9af8f304d8af0a8a625cb3600bf7c85208",
}
NAMESPACE = "longmemeval-reserved10-final-fusion-v1"
CODE = (
    __file__,
    "benchmarks/personal_retrieval_ablation.py",
    "benchmarks/public_context_baseline.py",
    "benchmarks/public_context_rerank.py",
    "benchmarks/public_memory_raw_continuation.py",
    "benchmarks/public_memory_comparison.py",
    "benchmarks/public_longmemeval.py",
    "benchmarks/public_memory_reader_v2.py",
    "benchmarks/public_memory_passage_diagnostic.py",
    "benchmarks/public_memory_task_accuracy.py",
    "benchmarks/public_memory_runtime.py",
    "benchmarks/public_memory_answer_comparison.py",
    "doppel_memory/rank_fusion.py",
    "doppel_memory/postgres_store.py",
    "doppel_memory/vector.py",
    "doppel_memory/lexical.py",
    "integrations/aml/context.py",
    "integrations/aml/contract.py",
)


def reserved_metadata(parent):
    rows = [c for c in parent["cases"] if c["partition"] == "reserved-not-run"]
    opened = {
        c["history_group"] for c in parent["cases"] if c["partition"] == "diagnostic"
    }
    if (
        len(rows) != 10
        or len({r["case_id"] for r in rows}) != 10
        or len({r["history_group"] for r in rows}) != 10
        or any(r["history_group"] in opened for r in rows)
    ):
        raise ValueError("exact ten disjoint original reserved histories required")
    if (
        sum(r["raw_turn_count"] for r in rows) != 5048
        or sum(r["chunk_count"] for r in rows) != 506
    ):
        raise ValueError("reserved source size differs from preregistration")
    return rows


def requests_for(cases, prepared):
    if prepared["status"] != "complete" or len(prepared["rows"]) != 10:
        raise ValueError("complete local10 preparation required before paid QA")
    result = []
    for ordinal, (case, meta) in enumerate(
        zip(cases, prepared["rows"], strict=True), start=1
    ):
        context = meta["context"]
        if (
            meta["ordinal"] != ordinal
            or meta["case_id"] != case.scoring.case_id
            or len(context) > 20
            or len(encoded(context)) > 24000
            or sha(encoded(context)) != meta["context_sha256"]
        ):
            raise ValueError("prepared source/context identity or cap mismatch")
        row = AnswerRow(
            ordinal - 1,
            case.scoring.case_id,
            "reserved-fixed-fusion",
            case.runtime,
            case.scoring,
            tuple(context),
        )
        request = reader_request(row)
        if (
            _request_sha256(request) != meta["reader_request_sha256"]
            or request_bytes(request) > 100000
        ):
            raise ValueError("frozen Reader request differs")
        result.append((row, request, meta))
    return result


def load(phase, preparation):
    raw = {name: path.read_bytes() for name, path in FILES.items()}
    if {name: sha(value) for name, value in raw.items()} != PINS:
        raise ValueError("preregistered input changed")
    data = {name: json.loads(value) for name, value in raw.items()}
    chosen = data["selection"]
    if chosen["status"] != "complete" or selection_summary(chosen["rows"])[
        "selection"
    ] != {
        "complete": True,
        "profile": "fusion",
        "engineering_threshold_not_significance_test": True,
    }:
        raise ValueError("opened-data configuration selection not complete/locked")
    parent = data["manifest"]
    validate_fingerprint(parent, "manifest_fingerprint")
    selected = reserved_metadata(parent)
    by_id = {r["question_id"]: r for r in data["dataset"]}
    cases = []
    for meta in selected:
        case = prepare_case(
            by_id[meta["case_id"]], dataset_namespace=parent["dataset_namespace"]
        )
        chunks = case.runtime.ingestion_chunks(max_messages=parent["max_messages"])
        if (
            history_group(case) != meta["history_group"]
            or len(chunks) != meta["chunk_count"]
            or sum(len(s.turns) for s in case.runtime.sessions)
            != meta["raw_turn_count"]
            or _hash([c.request.model_dump(mode="json") for c in chunks])
            != meta["history_payload_sha256"]
        ):
            raise ValueError("original reserved history payload changed")
        cases.append(case)
    original_model = data["window"]["plan"]["reranker"]
    provider = LocalContextCrossEncoder(
        Path(original_model["model_path"]), device="cuda", max_length=8192, batch_size=1
    )
    if model_identity(provider) != original_model:
        raise ValueError("selected BGE model artifact/runtime changed")
    if (
        sha(Path("doppel_memory/rank_fusion.py").read_bytes())
        != data["fusion"]["plan"]["code_sha256"]["doppel_memory/rank_fusion.py"]
    ):
        raise ValueError("selected rank-fusion implementation changed")
    for name, (_, tokens) in STAGES.items():
        if (
            config(tokens).model_dump(mode="json")
            != chosen["plan"]["stages"][name]["config"]
        ):
            raise ValueError("Reader/judge configuration changed")
    plan = {
        "runner": "doppel.reserved10-final.v1",
        "phase": "prepare",
        "input_sha256": PINS,
        "namespace": NAMESPACE,
        "schema": "reserved_final_" + _hash([NAMESPACE, PINS])[:12],
        "max_messages": parent["max_messages"],
        "cases": selected,
        "code_sha256": {str(Path(p)): sha(Path(p).read_bytes()) for p in CODE},
        "implementation_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "profile": "fixed80-BM25-vector-RRF60+BGE-equal-RRF60-top20-whole-ranked-fit24000",
        "model": original_model,
        "embedding": "fastembed:BAAI/bge-small-zh-v1.5/0.8.0/512/symmetric",
        "embedding_cache": data["window"]["plan"]["embedding_cache"],
        "max_local_rerank_calls": 10,
        "max_local_pairs": 800,
        "stages": {
            name: {
                "config": config(tokens).model_dump(mode="json"),
                "max_calls": 10,
                "max_request_bytes": 100000,
                "max_total_request_bytes": 1000000,
            }
            for name, (_, tokens) in STAGES.items()
        },
        "automatic_retries": 0,
        "graph_calls": 0,
        "llm_extraction_calls": 0,
        "no_tuning_on_reserved": True,
        "public_data_not_model_unseen": True,
        "publication_ready": False,
        "official_longmemeval_score": False,
        "aml_score": False,
    }
    base = {**plan, "plan_fingerprint": _hash(plan)}
    if phase == "answers":
        if preparation is None or preparation["plan"] != base:
            raise ValueError("matching frozen preparation/config required")
        queue = requests_for(cases, preparation)
        plan.update(
            phase="answers",
            preparation_sha256=_hash(preparation),
            reader_requests=[_request_sha256(request) for _, request, _ in queue],
        )
        base = {**plan, "plan_fingerprint": _hash(plan)}
    return base, cases, provider, raw


async def require_fresh_schema(connection, schema):
    if await connection.fetchval(
        "SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=$1)", schema
    ):
        raise ValueError("target schema already exists; no reset/reuse is authorized")


async def prepare_contexts(args, plan, cases, provider):
    asyncpg = importlib.import_module("asyncpg")

    for key in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "DOPPEL_API_KEY"):
        os.environ.pop(key, None)
    os.environ["HF_HUB_OFFLINE"] = "1"
    dsn = local_diagnostic_dsn("doppel-ablation-pgvector")
    connection = await asyncpg.connect(
        dsn, server_settings={"default_transaction_read_only": "on"}
    )
    try:
        await require_fresh_schema(connection, plan["schema"])
    finally:
        await connection.close()
    store = PostgreSQLStore(dsn, schema=plan["schema"], create_schema=True)
    embedding = _LocalEmbeddingProvider(cache_dir=Path(plan["embedding_cache"]))
    if (embedding.name, embedding.version, embedding.dimensions) != (
        "fastembed:BAAI/bge-small-zh-v1.5",
        "0.8.0",
        512,
    ):
        raise ValueError("same local embedding profile required")
    index = PostgreSQLVectorIndex(
        store, embedding, VectorIndexConfig(create_extension=False)
    )
    host = RawHistoryHost(store)
    delegate = StrictContextReranker(provider)
    ranker = RankFusionReranker(delegate, rrf_k=60)
    strategy = HybridRetrievalStrategy(
        index,
        lexical_strategy=BM25RetrievalStrategy(),
        candidate_multiplier=1,
        fallback_to_lexical=False,
    )
    rows, failure = [], None
    current, stage = None, "initialize"
    try:
        for ordinal, case in enumerate(cases, start=1):
            current, stage = ordinal, "raw-ingest"
            scope = memory_scope(plan["namespace"], case.runtime.user_id)
            records_list = await host.ingest(
                case.runtime, scope, max_messages=plan["max_messages"]
            )
            stage = "local-index"
            indexed = await index.index_records(records_list)
            if not indexed.ok or indexed.indexed + indexed.skipped != len(records_list):
                raise ValueError("index preparation incomplete")
            records = await inventory(store, [scope])
            if len(records) != plan["cases"][ordinal - 1]["raw_turn_count"]:
                raise ValueError("raw history incomplete")
            corpus = digest(records)
            before = await vector_receipt(store, index, scope, records)
            raw_positioned = bound_items(
                case.runtime,
                {"max_messages": plan["max_messages"]},
                scope,
                host,
                records,
            )
            if any(item is None for item in raw_positioned.values()):
                raise ValueError("source is not eligible raw evidence")
            positioned = {
                p: item for p, item in raw_positioned.items() if item is not None
            }
            items = {item["memory_id"]: item for item in positioned.values()}
            if len(items) != len(records):
                raise ValueError("source payload/provenance mismatch")
            stage = "locked-retrieval"
            result = await AttributedContextRetriever(
                store,
                strategy=strategy,
                resolve_event=host.resolve_event,
                reranker=ranker,
                candidate_limit=80,
            ).search(scope, case.runtime.query.query, limit=20)
            if (
                result.rejected
                or result.revalidated != 80
                or result.final_store_checks != 20
            ):
                raise ValueError("candidate/final source validation failed")
            top = [items[s.memory_id] for s in result.snippets]
            candidate_ids = [
                host.sources[(scope.scope_key, event)]
                for event in result.candidate_evidence_ids
            ]
            full_fusion = [
                candidate_ids[i]
                for i in rank_fusion_order(
                    [candidate_ids.index(key) for key in delegate.last_order], rrf_k=60
                )
            ]
            if full_fusion[:20] != [item["memory_id"] for item in top]:
                raise ValueError("full rank receipt differs from actual selected order")
            context, trace = pack_ranked_fit(top)
            row = AnswerRow(
                ordinal - 1,
                case.scoring.case_id,
                "reserved-fixed-fusion",
                case.runtime,
                case.scoring,
                tuple(context),
            )
            request = reader_request(row)
            if request_bytes(request) > 100000:
                raise ValueError("frozen Reader request cap exceeded")
            # Scoring labels are used only after final ordering and packing.
            required = (
                set()
                if case.scoring.abstention
                else {positioned[p]["memory_id"] for p in case.scoring.evidence_turns}
            )
            stage = "post-source-index-check"
            if corpus != digest(
                await inventory(store, [scope])
            ) or before != await vector_receipt(store, index, scope, records):
                raise ValueError("corpus/index changed during query")
            entry = {
                "ordinal": ordinal,
                "case_id": case.scoring.case_id,
                "raw_records": len(records),
                "corpus_sha256": corpus,
                "vector_receipt": before,
                "context": context,
                "context_sha256": sha(encoded(context)),
                "context_bytes": len(encoded(context)),
                "top20": top,
                "bge_full_order": delegate.last_order,
                "fusion_full_order": full_fusion,
                "candidate_items": [items[key] for key in candidate_ids],
                "source_execution": result.model_dump(
                    mode="json", exclude={"snippets"}
                ),
                "packing_trace": trace,
                "reader_request_sha256": _request_sha256(request),
                "abstention_label": case.scoring.abstention,
                "annotated": len(required),
                "top20_annotations": len(required & {i["memory_id"] for i in top}),
                "packed_annotations": len(required & {i["memory_id"] for i in context}),
            }
            rows.append(entry)
            write_new(args.run_dir / f"context-{ordinal:02d}.json", entry)
            print(
                f"prepared reserved history {ordinal}/10 ({len(records)} raw messages)",
                flush=True,
            )
    except Exception as exc:  # noqa: BLE001 - redact arbitrary provider/DB errors
        failure = {"ordinal": current, "stage": stage, "class": type(exc).__name__}
    finally:
        await store.close()
    return {
        "status": "complete" if failure is None else "failed",
        "rows": rows,
        "failure": failure,
        "paid_calls": 0,
        "raw_records": sum(r["raw_records"] for r in rows),
        "model_usage": provider.report(),
    }


def summary(rows):
    def score(values):
        complete = [r for r in values if r.get("grade") is not None]
        return {
            "completed": len(complete),
            "correct": sum(r["grade"]["answer_correct"] for r in complete),
            "accuracy": sum(r["grade"]["answer_correct"] for r in complete)
            / len(complete)
            if complete
            else None,
        }

    return {
        "expected": 10,
        **score(rows),
        "answerable": score([r for r in rows if not r["abstention_label"]]),
        "unanswerable": score([r for r in rows if r["abstention_label"]]),
        "by_type": {
            kind: score(
                [
                    r
                    for r in rows
                    if not r["abstention_label"] and r["question_type"] == kind
                ]
            )
            for kind in sorted({r["question_type"] for r in rows})
        },
        "structurally_valid": sum(
            r.get("checks", {}).get("structurally_valid", False) for r in rows
        ),
    }


async def answer(args, plan, cases, preparation):
    key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not args.cache_only and not key:
        raise ValueError("provider key absent")
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"), schema=plan["schema"]
    )
    ledgers, models, executors, rows = {}, {}, {}, []
    failure, current, stage = None, None, "initialize"
    try:
        for name, (schema, tokens) in STAGES.items():
            limits = {
                k: plan["stages"][name][k]
                for k in ("max_calls", "max_request_bytes", "max_total_request_bytes")
            }
            ledger = DurableCallLedger(
                args.run_dir / "usage.sqlite3",
                budget_id=plan["plan_fingerprint"] + ":" + name,
                **limits,
            )
            ledgers[name] = ledger
            model = PilotStructuredModel(
                _default_provider_factory(
                    config(tokens),
                    key or "cache-only-no-credential",
                    ledger.observe_usage,
                ),
                ledger=ledger,
                cache_dir=args.run_dir / name,
                cache_only=args.cache_only,
                read_only_cache_dirs=[p / name for p in args.cache_parent],
            )
            models[name] = model
            executors[name] = _StageExecutor(
                model, ledger, schema, cache_only=args.cache_only
            )
        for row, request, meta in requests_for(cases, preparation):
            current, stage = meta["ordinal"], "current-source-check"
            scope = memory_scope(plan["namespace"], row.runtime.user_id)
            records = await inventory(store, [scope])
            if digest(records) != meta["corpus_sha256"]:
                raise ValueError("prepared source corpus changed")
            _, positioned = bind_host(
                row.runtime,
                {"max_messages": plan["max_messages"]},
                scope,
                records,
                store,
            )
            items = {item["memory_id"]: item for item in positioned.values()}
            if any(items.get(item["memory_id"]) != item for item in row.context):
                raise ValueError("prepared context differs from current originals")
            stage = "reader"
            output, called = await executors["reader"].execute(request, row.index)
            entry = {
                "ordinal": current,
                "case_id": row.case_id,
                "question_type": row.scoring.category,
                "abstention_label": row.scoring.abstention,
                "context_sha256": meta["context_sha256"],
                "reader": called,
                "reader_output": output.model_dump(mode="json") if output else None,
            }
            if output:
                stage = "judge"
                grade, judged = await executors["judge"].execute(
                    task_request(
                        row.runtime.query.query, row.scoring.answer, output.answer
                    ),
                    row.index,
                )
                entry.update(
                    checks=structural_check(row, output),
                    task_judge=judged,
                    grade=grade.model_dump(mode="json") if grade else None,
                )
            rows.append(entry)
            write_new(args.run_dir / f"answer-{current:02d}.json", entry)
            if not output or not entry.get("grade"):
                raise RuntimeError("failed request retained; no retry")
            stage = "post-source-check"
            if digest(await inventory(store, [scope])) != meta["corpus_sha256"]:
                raise ValueError("corpus changed during QA")
            print(
                f"answered reserved {current}/10; correct {summary(rows)['correct']}/{current}",
                flush=True,
            )
    except Exception as exc:  # noqa: BLE001 - redact arbitrary error text
        failure = {"ordinal": current, "stage": stage, "class": type(exc).__name__}
    finally:
        await store.close()
    report = {
        "status": "complete" if failure is None else "failed",
        "rows": rows,
        "summary": summary(rows),
        "failure": failure,
        "usage": {name: model.report() for name, model in models.items()},
    }
    for ledger in ledgers.values():
        ledger.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("prepare", "answers"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preparation", type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--cache-parent", type=Path, action="append", default=[])
    args = parser.parse_args()
    if args.output.exists() or (args.run_dir and args.run_dir.exists()):
        parser.error("new output/run paths required; no overwrite or automatic resume")
    preparation = (
        json.loads(args.preparation.read_bytes()) if args.preparation else None
    )
    plan, cases, provider, raw = load(args.phase, preparation)
    result = {"plan": plan, "status": "ready"}
    if args.execute:
        if (
            not args.run_dir
            or not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            parser.error("matching frozen preflight and new run directory required")
        write_new(
            args.run_dir / "attempt.json", {"plan": plan, "cache_only": args.cache_only}
        )
        result.update(
            asyncio.run(
                prepare_contexts(args, plan, cases, provider)
                if args.phase == "prepare"
                else answer(args, plan, cases, preparation)
            )
        )
    if any(FILES[name].read_bytes() != value for name, value in raw.items()):
        raise ValueError("pinned input changed; checkpoints retained")
    write_new(args.output, result)
    print(
        f"output: {args.output.resolve()}\nsha256: {sha(args.output.read_bytes())}",
        flush=True,
    )
    if "summary" in result:
        print(json.dumps(result["summary"], ensure_ascii=False), flush=True)
    raise SystemExit(0 if result["status"] in {"ready", "complete"} else 1)


if __name__ == "__main__":
    main()
