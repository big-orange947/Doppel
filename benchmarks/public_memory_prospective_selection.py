"""Fixed fresh ordinals41-45: raw preparation, then BGE/LLM paired evaluation."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_context_baseline import RawHistoryHost, score_evidence
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
from benchmarks.public_memory_expansion import config, local_diagnostic_dsn, save
from benchmarks.public_memory_fresh_cohort import validate_fingerprint
from benchmarks.public_memory_high_config_first import ReadOnlyStore
from benchmarks.public_memory_listwise_diagnostic import (
    AuditedRankModel,
    request_bytes,
)
from benchmarks.public_memory_passage_diagnostic import (
    SavedOrder,
    passage_item,
    reader_request,
)
from benchmarks.public_memory_pilot import _hash, history_group
from benchmarks.public_memory_raw_continuation import bound_items
from benchmarks.public_memory_reader_v2 import ReaderV2Output, structural_check
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_source_aware_diagnostic import SavedCandidates
from benchmarks.public_memory_task_accuracy import Grade
from benchmarks.public_memory_task_accuracy import request as task_request
from benchmarks.public_memory_topk_diagnostic import preview_request
from doppel_memory.bounded_selection import BoundedTopKSelector
from doppel_memory.lexical import BM25RetrievalStrategy
from doppel_memory.models import MemoryFilter, MemoryState, RecallResult
from doppel_memory.postgres_store import PostgreSQLStore, _load_asyncpg
from doppel_memory.reference_selection import TopKSelectionConfig
from doppel_memory.vector import (
    HybridRetrievalStrategy,
    PostgreSQLVectorIndex,
    VectorIndexConfig,
)
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.contract import memory_scope
from integrations.aml.passages import AttributedPassageRetriever

RUNNER = "doppel.prospective-selection-41-45.v1"
NAMESPACE = "longmemeval-prospective-selection-41-45-v1"
PROFILES = ("bge_content_only", "llm_metadata_up_to20")
STAGES = {
    "selector": (10, 1024, 500000, 5000000),
    "reader": (10, 2048, 100000, 1000000),
    "judge": (10, 1024, 100000, 1000000),
}
MODEL_FILES = (
    __file__,
    "doppel_memory/bounded_selection.py",
    "doppel_memory/reference_selection.py",
    "doppel_memory/source_aware_rerank.py",
    "integrations/aml/context.py",
    "integrations/aml/passages.py",
    "benchmarks/public_memory_passage_diagnostic.py",
    "benchmarks/public_memory_reader_v2.py",
    "benchmarks/public_memory_task_accuracy.py",
    "benchmarks/public_context_rerank.py",
    "benchmarks/public_memory_topk_diagnostic.py",
    "benchmarks/public_memory_comparison.py",
)


def prepare(raw, parent, source_sha):
    validate_fingerprint(parent, "manifest_fingerprint")
    selected = [c for c in parent["cases"] if c["partition"] == "diagnostic"]
    by_id = {r["question_id"]: r for r in raw}
    if (
        len(selected) < 45
        or len(by_id) != len(raw)
        or source_sha != parent["source_sha256"]
    ):
        raise ValueError(
            "unchanged source and at least45 frozen diagnostic cases required"
        )
    forbidden = (
        {c["history_group"] for c in parent["cases"] if c["partition"] != "diagnostic"}
        | {c["history_group"] for c in selected[:40]}
        | set(parent.get("excluded_history_groups", []))
    )
    cases, rows = [], []
    for ordinal, row in enumerate(selected[40:45], 41):
        case = prepare_case(
            by_id[row["case_id"]], dataset_namespace=parent["dataset_namespace"]
        )
        chunks = case.runtime.ingestion_chunks(max_messages=parent["max_messages"])
        if (
            history_group(case) != row["history_group"]
            or row["history_group"] in forbidden
            or sum(len(s.turns) for s in case.runtime.sessions) != row["raw_turn_count"]
            or len(chunks) != row["chunk_count"]
            or _hash([c.request.model_dump(mode="json") for c in chunks])
            != row["history_payload_sha256"]
        ):
            raise ValueError(
                "fresh history/source binding differs or overlaps opened/reserved history"
            )
        forbidden.add(row["history_group"])
        cases.append((case.runtime, case.scoring))
        rows.append(
            {
                "ordinal": ordinal,
                "case_id": row["case_id"],
                "history_group": row["history_group"],
                "raw_turn_count": row["raw_turn_count"],
                "chunk_count": row["chunk_count"],
                "history_payload_sha256": row["history_payload_sha256"],
                "sampling_stratum": row.get("sampling_stratum", "public"),
            }
        )
    manifest = {
        "runner": RUNNER,
        "parent_manifest_fingerprint": parent["manifest_fingerprint"],
        "source_sha256": source_sha,
        "run_namespace": NAMESPACE,
        "dataset_namespace": parent["dataset_namespace"],
        "max_messages": parent["max_messages"],
        "temporal_policy": parent["temporal_policy"],
        "cases": rows,
    }
    return cases, {**manifest, "manifest_fingerprint": _hash(manifest)}


def model_identity(provider):
    return {
        k: v
        for k, v in provider.report().items()
        if k
        not in {
            "device_actual",
            "calls",
            "pairs_scored",
            "truncated_pairs",
            "longest_pair_tokens",
        }
    }


def make_plan(phase, manifest, model, preparation=None):
    value = {
        "runner": RUNNER,
        "phase": phase,
        "manifest": manifest,
        "schema": "raw_select_" + manifest["manifest_fingerprint"][:12],
        "profiles": list(PROFILES),
        "bge": model,
        "candidate_window": 80,
        "source_limit": 20,
        "passage_limit": 80,
        "output_limit": 20,
        "context_byte_limit": 24000,
        "span_chars": 1200,
        "overlap_chars": 160,
        "source_sha256": {
            p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in MODEL_FILES
        },
        "embedding": "fastembed:BAAI/bge-small-zh-v1.5/0.8.0/512",
        "fusion": "production-BM25-vector-RRF60-equal-no-fallback",
        "stages": {
            name: {
                "max_calls": cap,
                "config": config(tokens).model_dump(mode="json"),
                "max_request_bytes": size,
                "max_total_request_bytes": total,
            }
            for name, (cap, tokens, size, total) in STAGES.items()
        },
        "fragment_annotation_policy": "source-presence-is-not-semantic-support; report full-turn-text-retention separately",
        "comparison": "deployment-profiles-not-model-only-ablation; metadata differs",
        "publication_ready": False,
        "independent_model_unseen_claim": False,
        "graph_calls": 0,
        "automatic_retries": 0,
        "selection_policy": "fixed-parent-ordinals-41-through-45-no-replacements",
    }
    if preparation is not None:
        previous = preparation["plan"]
        if (
            preparation["status"] != "complete"
            or previous["manifest"] != manifest
            or previous["source_sha256"] != value["source_sha256"]
            or previous["bge"] != model
        ):
            raise ValueError(
                "preparation/runtime code or source changed before evaluation"
            )
        value["preparation_sha256"] = _hash(preparation)
        value["source_requests"] = [
            {
                k: r[k]
                for k in (
                    "case_id",
                    "corpus_sha256",
                    "pool_sha256",
                    "selector_request_sha256",
                    "selector_request_bytes",
                )
            }
            for r in preparation["receipts"]
        ]
        if len(value["source_requests"]) != 5 or any(
            r["selector_request_bytes"] > STAGES["selector"][2]
            for r in value["source_requests"]
        ):
            raise ValueError("five bounded source requests required")
    return {**value, "plan_fingerprint": _hash(value)}


def fragment_annotations(scoring, context, items):
    """Do not call a fragment's source ID an answer-support hit."""
    positions = {item["memory_id"]: pos for pos, item in items.items()}
    spans = {}
    for item in context:
        span = item["source_span"]
        key = positions[item["source_memory_id"]]
        spans.setdefault(key, []).append(
            (span["start"], span["end"], span["source_char_count"])
        )
    full = set()
    for key, intervals in spans.items():
        end = 0
        for start, stop, size in sorted(intervals):
            if start > end:
                break
            end = max(end, stop)
        if end == intervals[0][2]:
            full.add(key)
    required = set(scoring.evidence_turns)
    return {
        "eligible_answerable": not scoring.abstention and bool(required),
        "annotated_turn_count": len(required),
        "annotated_source_turns_present": len(required & set(spans)),
        "full_annotated_turn_texts_retained": len(required & full),
        "fragment_answer_support_recall": None,
    }


def bind_host(runtime, manifest, scope, records, store):
    host = RawHistoryHost(store)
    host.sources = {
        (scope.scope_key, r.source_event_id): r.memory_id for r in records.values()
    }
    raw_items = bound_items(runtime, manifest, scope, host, records)
    if len(raw_items) != len(records) or any(i is None for i in raw_items.values()):
        raise ValueError("raw inventory differs from immutable history")
    items = {k: v for k, v in raw_items.items() if v is not None}
    host.positions = {
        (scope.scope_key, records[i["memory_id"]].source_event_id): p
        for p, i in items.items()
    }
    return host, items


async def source_preview(store, scope, host, pool, query):
    result = await AttributedContextRetriever(
        store, strategy=SavedCandidates(pool), resolve_event=host.resolve_event
    ).search(scope, query, limit=80)
    if result.rejected or len(result.snippets) != len(pool):
        raise ValueError("complete authorized pool required before selection")
    return preview_request(query, scope, result.snippets, BoundedTopKSelector)


async def context_row(
    store, scope, host, pool, runtime, scoring, profile, ordering, items
):
    sources = await AttributedContextRetriever(
        store,
        strategy=SavedCandidates(pool),
        resolve_event=host.resolve_event,
        reranker=ordering,
    ).search(scope, runtime.query.query, limit=20)
    selection = getattr(ordering, "last_selection", None)
    source_summary = selection.model_dump(mode="json") if selection else None
    parent = AttributedContextRetriever(
        store,
        strategy=SavedOrder(scope, [s.memory_id for s in sources.snippets]),
        resolve_event=host.resolve_event,
    )
    retriever = AttributedPassageRetriever(parent, reranker=ordering)
    result = await retriever.search(scope, runtime.query.query, limit=20)
    for p in result.passages:
        await retriever.resolve_original(scope, p)
    packed, trace = pack_ranked_fit([passage_item(p) for p in result.passages])
    return {
        "case_id": scoring.case_id,
        "profile": profile,
        "context": packed,
        "context_sha256": hashlib.sha256(encoded(packed)).hexdigest(),
        "context_bytes": len(encoded(packed)),
        "source_selection": source_summary,
        "source_turn_coverage": score_evidence(
            scoring, host.retrieved_positions(sources.snippets)
        ),
        "packed_annotations": fragment_annotations(scoring, packed, items),
        "source_execution": sources.model_dump(mode="json", exclude={"snippets"}),
        "passage_execution": result.model_dump(mode="json", exclude={"passages"}),
        "packing_trace": trace,
    }


async def prepare_run(args, cases, manifest, plan, provider):
    save(args.run_dir / "prepare-attempt.json", {"plan": plan})
    dsn = local_diagnostic_dsn("doppel-ablation-pgvector")
    check = await _load_asyncpg().connect(dsn)
    try:
        if await check.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name=$1)",
            plan["schema"],
        ):
            raise ValueError(
                "dedicated schema already exists; never reset or implicitly rerun"
            )
    finally:
        await check.close()
    store = PostgreSQLStore(dsn, schema=plan["schema"], create_schema=True)
    embedder = _LocalEmbeddingProvider(cache_dir=None)
    if (embedder.name, embedder.version, embedder.dimensions) != (
        "fastembed:BAAI/bge-small-zh-v1.5",
        "0.8.0",
        512,
    ):
        raise ValueError("unchanged local embedding required")
    index = PostgreSQLVectorIndex(
        store, embedder, VectorIndexConfig(create_extension=True)
    )
    receipts = []
    try:
        for ordinal, (runtime, scoring) in enumerate(cases, 41):
            scope = memory_scope(manifest["run_namespace"], runtime.user_id)
            host = RawHistoryHost(store)
            created = await host.ingest(
                runtime, scope, max_messages=manifest["max_messages"]
            )
            indexed = await index.index_records(created)
            if not indexed.ok or indexed.indexed + indexed.skipped != len(created):
                raise ValueError("local vector indexing incomplete")
            records = await inventory(store, [scope])
            host, items = bind_host(runtime, manifest, scope, records, store)
            digest = _hash({k: r.model_dump(mode="json") for k, r in records.items()})
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
            preview = await source_preview(
                store, scope, host, pool, runtime.query.query
            )
            if request_bytes(preview) > STAGES["selector"][2]:
                raise ValueError("source request exceeds preregistered cap")
            baseline = await context_row(
                store,
                scope,
                host,
                pool,
                runtime,
                scoring,
                PROFILES[0],
                StrictContextReranker(provider),
                items,
            )
            after = await inventory(store, [scope])
            if digest != _hash(
                {k: r.model_dump(mode="json") for k, r in after.items()}
            ):
                raise ValueError("source changed during local baseline")
            receipt = {
                "ordinal": ordinal,
                "case_id": scoring.case_id,
                "raw_records": len(records),
                "corpus_sha256": digest,
                "pool_sha256": _hash([c.model_dump(mode="json") for c in pool]),
                "pool": [c.model_dump(mode="json") for c in pool],
                "selector_request_sha256": _request_sha256(preview),
                "selector_request_bytes": request_bytes(preview),
                "baseline": baseline,
            }
            save(args.run_dir / f"prepared-{ordinal}.json", receipt)
            receipts.append(receipt)
            print(
                f"prepared {ordinal - 40}/5 histories ({len(records)} raw messages), zero LLM",
                flush=True,
            )
    finally:
        await store.close()
    return {
        "status": "complete",
        "receipts": receipts,
        "raw_records": sum(r["raw_records"] for r in receipts),
        "reranker": provider.report(),
        "new_calls": 0,
    }


async def evaluate_run(args, cases, manifest, plan, preparation):
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        raise ValueError("provider key absent")
    save(args.run_dir / "evaluate-attempt.json", {"plan": plan})
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"), schema=plan["schema"]
    )
    ledgers, models, rows = {}, {}, []
    stage, case = "initialization", None
    try:
        for name, limits in plan["stages"].items():
            ledger = DurableCallLedger(
                args.run_dir / "usage.sqlite3",
                budget_id=plan["plan_fingerprint"] + ":" + name,
                max_calls=limits["max_calls"],
                max_request_bytes=limits["max_request_bytes"],
                max_total_request_bytes=limits["max_total_request_bytes"],
            )
            ledgers[name] = ledger
            if ledger.report()["attempts_reserved"]:
                raise ValueError("preserve previous paid attempts")
            models[name] = PilotStructuredModel(
                _default_provider_factory(
                    config(STAGES[name][1]),
                    os.environ["DEEPSEEK_API_KEY"],
                    ledger.observe_usage,
                ),
                ledger=ledger,
                cache_dir=args.run_dir / name,
            )
        audit = AuditedRankModel(models["selector"], args.run_dir)
        selector = BoundedTopKSelector(audit, TopKSelectionConfig(timeout_seconds=300))
        reader = _StageExecutor(
            models["reader"], ledgers["reader"], ReaderV2Output, cache_only=False
        )
        judge = _StageExecutor(
            models["judge"], ledgers["judge"], Grade, cache_only=False
        )
        for (runtime, scoring), receipt in zip(
            cases, preparation["receipts"], strict=True
        ):
            case, stage = scoring.case_id, "source-validation"
            if receipt["case_id"] != case:
                raise ValueError("case/preparation order changed")
            scope = memory_scope(manifest["run_namespace"], runtime.user_id)
            records = await inventory(store, [scope])
            if receipt["corpus_sha256"] != _hash(
                {k: r.model_dump(mode="json") for k, r in records.items()}
            ):
                raise ValueError("prepared source changed")
            host, items = bind_host(runtime, manifest, scope, records, store)
            pool = [RecallResult.model_validate(c) for c in receipt["pool"]]
            if receipt["pool_sha256"] != _hash(
                [c.model_dump(mode="json") for c in pool]
            ):
                raise ValueError("frozen pool changed")
            audit.expected_source_sha = receipt["selector_request_sha256"]
            stage = "llm-selection"
            candidate = await context_row(
                store, scope, host, pool, runtime, scoring, PROFILES[1], selector, items
            )
            for context in (receipt["baseline"], candidate):
                if (
                    context["context_sha256"]
                    != hashlib.sha256(encoded(context["context"])).hexdigest()
                    or len(encoded(context["context"])) > 24000
                ):
                    raise ValueError("packed context bytes changed")
                index = len(rows)
                save(args.run_dir / f"context-{index}.json", context)
                row = AnswerRow(
                    index,
                    case,
                    context["profile"],
                    runtime,
                    scoring,
                    tuple(context["context"]),
                )
                stage = "reader"
                output, record = await reader.execute(reader_request(row), index)
                entry = {
                    **context,
                    "reader": record,
                    "reader_output": output.model_dump(mode="json") if output else None,
                }
                if output:
                    stage = "task-judge"
                    grade, judged = await judge.execute(
                        task_request(
                            runtime.query.query, scoring.answer, output.answer
                        ),
                        index,
                    )
                    entry.update(
                        checks=structural_check(row, output),
                        task_judge=judged,
                        grade=grade.model_dump(mode="json") if grade else None,
                    )
                rows.append(entry)
                save(args.run_dir / f"answer-{index}.json", entry)
                if not output or not entry.get("grade"):
                    raise RuntimeError("QA stage failed; no retry")
            stage = "final-store-validation"
            after = await inventory(store, [scope])
            if receipt["corpus_sha256"] != _hash(
                {k: r.model_dump(mode="json") for k, r in after.items()}
            ):
                raise ValueError("Store changed during read-only evaluation")
            print(f"completed paired QA {len(rows) // 2}/5", flush=True)
        status, failure = "complete", None
    except Exception as exc:  # noqa: BLE001 - redact arbitrary provider errors
        status, failure = "failed", type(exc).__name__
    finally:
        await store.close()
    result = {
        "status": status,
        "rows": rows,
        "failure_class": failure,
        "stopped_case": case if failure else None,
        "stopped_stage": stage if failure else None,
        "usage": {k: v.report() for k, v in ledgers.items()},
    }
    for ledger in ledgers.values():
        ledger.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("prepare", "evaluate"), required=True)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/public-benchmarks/longmemeval_s_cleaned.json"),
    )
    parser.add_argument(
        "--parent-manifest",
        type=Path,
        default=Path("data/doppel/longmemeval-fresh-high-config-50-manifest-v1.json"),
    )
    parser.add_argument(
        "--reranker-model",
        type=Path,
        default=Path("D:/project/.doppel-eval-models/bge-reranker-v2-m3"),
    )
    parser.add_argument("--preparation", type=Path)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("fresh output required")
    raw = args.dataset.read_bytes()
    cases, manifest = prepare(
        json.loads(raw),
        json.loads(args.parent_manifest.read_bytes()),
        hashlib.sha256(raw).hexdigest(),
    )
    provider, preparation = None, None
    if args.phase == "prepare":
        provider = LocalContextCrossEncoder(
            args.reranker_model, device="cuda", max_length=8192, batch_size=1
        )
        identity = model_identity(provider)
    else:
        if args.preparation is None:
            parser.error("completed preparation required")
        preparation = json.loads(args.preparation.read_bytes())
        validate_fingerprint(preparation["plan"], "plan_fingerprint")
        identity = preparation["plan"]["bge"]
    plan = make_plan(args.phase, manifest, identity, preparation)
    result = {
        "runner": RUNNER,
        "status": "ready",
        "plan": plan,
        "graph_calls": 0,
        "publication_ready": False,
    }
    if args.execute:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            parser.error("matching frozen preflight required")
        result.update(
            asyncio.run(
                prepare_run(args, cases, manifest, plan, provider)
                if args.phase == "prepare"
                else evaluate_run(args, cases, manifest, plan, preparation)
            )
        )
    save(args.output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "phase": args.phase,
                "new_attempts": sum(
                    v["attempts_reserved"] for v in result.get("usage", {}).values()
                ),
            }
        )
    )
    raise SystemExit(0 if result["status"] in {"ready", "complete"} else 1)


if __name__ == "__main__":
    main()
