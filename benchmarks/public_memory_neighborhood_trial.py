"""Fresh fixed ordinals46-50: matched-count native vs source-neighborhood QA.

Preparation writes only raw events/local vectors. Paid evaluation reopens the
frozen pools read-only; both arms use identical source/passage selection and QA.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_context_baseline import RawHistoryHost, score_evidence
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
    NoGenerate,
    request_bytes,
)
from benchmarks.public_memory_neighborhood_audit import source_index
from benchmarks.public_memory_passage_diagnostic import (
    SavedOrder,
    passage_item,
    reader_request,
)
from benchmarks.public_memory_pilot import _hash, history_group
from benchmarks.public_memory_prospective_selection import (
    bind_host,
    fragment_annotations,
)
from benchmarks.public_memory_reader_v2 import ReaderV2Output, structural_check
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_source_aware_diagnostic import SavedCandidates
from benchmarks.public_memory_task_accuracy import Grade
from benchmarks.public_memory_task_accuracy import request as task_request
from doppel_memory.bounded_selection import BoundedTopKSelector
from doppel_memory.lexical import BM25RetrievalStrategy
from doppel_memory.models import RecallResult
from doppel_memory.postgres_store import PostgreSQLStore, _load_asyncpg
from doppel_memory.reference_selection import TopKSelectionConfig
from doppel_memory.vector import (
    HybridRetrievalStrategy,
    PostgreSQLVectorIndex,
    VectorIndexConfig,
)
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.contract import memory_scope
from integrations.aml.neighborhood import (
    AttributedNeighborhoodExpander,
    NeighborhoodConfig,
    as_candidate,
)
from integrations.aml.passages import AttributedPassageRetriever

RUNNER = "doppel.fresh-neighborhood-46-50.v1"
NAMESPACE = "longmemeval-neighborhood-46-50-v1"
PROFILES = ("native_matched", "neighborhood")
SELECTION = TopKSelectionConfig(
    max_candidates=240, max_input_chars=350000, timeout_seconds=300.0
)
STAGES = {
    "selector": (20, 1024, 600000, 12000000),
    "reader": (10, 2048, 100000, 1000000),
    "judge": (10, 1024, 100000, 1000000),
}
MODEL_FILES = (
    __file__,
    "benchmarks/public_memory_prospective_selection.py",
    "benchmarks/public_memory_neighborhood_audit.py",
    "benchmarks/public_memory_listwise_diagnostic.py",
    "benchmarks/public_memory_passage_diagnostic.py",
    "benchmarks/public_memory_reader_v2.py",
    "benchmarks/public_memory_task_accuracy.py",
    "benchmarks/public_memory_comparison.py",
    "benchmarks/public_context_baseline.py",
    "benchmarks/public_longmemeval.py",
    "benchmarks/public_memory_runtime.py",
    "benchmarks/public_memory_answer_comparison.py",
    "benchmarks/public_memory_expansion.py",
    "benchmarks/public_memory_source_aware_diagnostic.py",
    "benchmarks/public_memory_raw_continuation.py",
    "benchmarks/public_memory_high_config_first.py",
    "benchmarks/personal_retrieval_ablation.py",
    "doppel_memory/bounded_selection.py",
    "doppel_memory/reference_selection.py",
    "doppel_memory/source_aware_rerank.py",
    "doppel_memory/source_order.py",
    "doppel_memory/lexical.py",
    "doppel_memory/vector.py",
    "integrations/aml/context.py",
    "integrations/aml/neighborhood.py",
    "integrations/aml/passages.py",
)


def prepare(raw, parent, source_sha):
    validate_fingerprint(parent, "manifest_fingerprint")
    selected = [r for r in parent["cases"] if r["partition"] == "diagnostic"]
    by_id = {r["question_id"]: r for r in raw}
    if (
        len(selected) != 50
        or len(by_id) != len(raw)
        or source_sha != parent["source_sha256"]
    ):
        raise ValueError("unchanged source and frozen fifty-case parent required")
    forbidden = (
        {r["history_group"] for r in selected[:45]}
        | {
            r["history_group"]
            for r in parent["cases"]
            if r["partition"] != "diagnostic"
        }
        | set(parent.get("excluded_history_groups", []))
    )
    cases, rows = [], []
    for ordinal, row in enumerate(selected[45:50], 46):
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
                "fresh source binding changed or overlaps opened/reserved histories"
            )
        forbidden.add(row["history_group"])
        cases.append((case.runtime, case.scoring))
        rows.append(
            {
                "ordinal": ordinal,
                **{
                    k: row[k]
                    for k in (
                        "case_id",
                        "history_group",
                        "raw_turn_count",
                        "chunk_count",
                        "history_payload_sha256",
                    )
                },
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


def make_plan(phase, manifest, preparation=None):
    value = {
        "runner": RUNNER,
        "phase": phase,
        "manifest": manifest,
        "schema": "raw_neighbor_" + manifest["manifest_fingerprint"][:12],
        "profiles": list(PROFILES),
        "neighborhood": NeighborhoodConfig().model_dump(mode="json"),
        "selector": SELECTION.model_dump(mode="json"),
        "candidate_policy": "top80 then explicit +/-1 neighbors; native recomputed at expanded count; no byte matching",
        "source_limit": 20,
        "passage_limit": 80,
        "output_limit": 20,
        "context_byte_limit": 24000,
        "arm_order": "native then neighborhood; same model/instructions/metadata/limits",
        "source_sha256": {
            p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in MODEL_FILES
        },
        "embedding": "fastembed:BAAI/bge-small-zh-v1.5/0.8.0/512",
        "fusion": "production-BM25-vector-RRF60-equal-no-fallback",
        "stages": {
            n: {
                "max_calls": cap,
                "config": config(tokens).model_dump(mode="json"),
                "max_request_bytes": size,
                "max_total_request_bytes": total,
            }
            for n, (cap, tokens, size, total) in STAGES.items()
        },
        "publication_ready": False,
        "independent_model_unseen_claim": False,
        "judge": "unchanged-DeepSeek-provisional-not-official-LongMemEval-or-AML",
        "selection_policy": "fixed-parent-ordinals46-50-no-replacements",
        "automatic_retries": 0,
        "graph_calls": 0,
    }
    if preparation is not None:
        previous = preparation["plan"]
        if preparation["status"] != "complete" or any(
            previous[k] != v for k, v in value.items() if k != "phase"
        ):
            raise ValueError("preparation/runtime binding changed")
        requests = []
        for receipt in preparation["receipts"]:
            for profile in PROFILES:
                pool = receipt["pools"][profile]
                requests.append(
                    {
                        "case_id": receipt["case_id"],
                        "profile": profile,
                        "corpus_sha256": receipt["corpus_sha256"],
                        **{
                            k: pool[k]
                            for k in (
                                "pool_sha256",
                                "selector_request_sha256",
                                "selector_request_bytes",
                                "count",
                            )
                        },
                    }
                )
        if len(requests) != 10 or any(
            r["selector_request_bytes"] > STAGES["selector"][2]
            or not 1 <= r["count"] <= 240
            for r in requests
        ):
            raise ValueError("ten bounded source requests required")
        value.update(preparation_sha256=_hash(preparation), source_requests=requests)
    return {**value, "plan_fingerprint": _hash(value)}


async def validated(store, scope, host, pool, query):
    result = await AttributedContextRetriever(
        store,
        strategy=SavedCandidates(pool),
        resolve_event=host.resolve_event,
        candidate_multiplier=1,
    ).search(scope, query, limit=len(pool))
    if result.rejected or len(result.snippets) != len(pool):
        raise ValueError("complete unchanged authorized candidate pool required")
    return result.snippets


def preview(query, scope, snippets):
    return BoundedTopKSelector(NoGenerate(), SELECTION).build_request(
        query, [as_candidate(scope, s) for s in snippets], limit=20
    )


async def context_row(
    store, scope, host, pool, runtime, scoring, profile, selector, items
):
    # Explicit 12x20 window: do NOT silently crop expanded pools to the old80.
    sources = await AttributedContextRetriever(
        store,
        strategy=SavedCandidates(pool),
        resolve_event=host.resolve_event,
        reranker=selector,
        candidate_multiplier=12,
    ).search(scope, runtime.query.query, limit=20)
    summary = selector.last_selection
    if summary is None or summary.offered_candidates != len(pool) or sources.rejected:
        raise ValueError("selector did not consume the entire authorized pool")
    retriever = AttributedPassageRetriever(
        AttributedContextRetriever(
            store,
            strategy=SavedOrder(scope, [s.memory_id for s in sources.snippets]),
            resolve_event=host.resolve_event,
        ),
        reranker=selector,
    )
    result = await retriever.search(scope, runtime.query.query, limit=20)
    for p in result.passages:
        await retriever.resolve_original(scope, p)
    if result.rejected:
        raise ValueError("passage provenance validation failed")
    packed, trace = pack_ranked_fit([passage_item(p) for p in result.passages])
    return {
        "case_id": scoring.case_id,
        "profile": profile,
        "context": packed,
        "context_sha256": hashlib.sha256(encoded(packed)).hexdigest(),
        "context_bytes": len(encoded(packed)),
        "source_selection": summary.model_dump(mode="json"),
        "passage_selection": selector.last_selection.model_dump(mode="json")
        if selector.last_selection
        else None,
        "source_turn_coverage": score_evidence(
            scoring, host.retrieved_positions(sources.snippets)
        ),
        "packed_annotations": fragment_annotations(scoring, packed, items),
        "source_execution": sources.model_dump(mode="json", exclude={"snippets"}),
        "passage_execution": result.model_dump(mode="json", exclude={"passages"}),
        "packing_trace": trace,
    }


def digest(records):
    return _hash({k: r.model_dump(mode="json") for k, r in records.items()})


async def prepare_run(args, cases, manifest, plan):
    save(args.run_dir / "prepare-attempt.json", {"plan": plan})
    dsn = local_diagnostic_dsn("doppel-ablation-pgvector")
    check = await _load_asyncpg().connect(dsn)
    try:
        if await check.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name=$1)",
            plan["schema"],
        ):
            raise ValueError("dedicated schema exists; never reset or implicitly rerun")
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
    hybrid = HybridRetrievalStrategy(
        index,
        lexical_strategy=BM25RetrievalStrategy(),
        candidate_multiplier=1,
        fallback_to_lexical=False,
    )
    receipts, current = [], None
    try:
        for meta, (runtime, scoring) in zip(manifest["cases"], cases, strict=True):
            current = scoring.case_id
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
            corpus = digest(records)
            anchors = await AttributedContextRetriever(
                store,
                strategy=hybrid,
                resolve_event=host.resolve_event,
                candidate_multiplier=1,
            ).search(scope, runtime.query.query, limit=80)
            if anchors.rejected:
                raise ValueError("anchor validation failed")
            expanded = await AttributedNeighborhoodExpander(
                store,
                resolve_event=host.resolve_event,
                source_order=source_index(scope, records, items),
                config=NeighborhoodConfig.model_validate(plan["neighborhood"]),
            ).expand(scope, anchors.snippets)
            if (
                expanded.rejected
                or expanded.snippets[: len(anchors.snippets)] != anchors.snippets
            ):
                raise ValueError("expansion rejected or changed original anchors")
            native = await AttributedContextRetriever(
                store,
                strategy=hybrid,
                resolve_event=host.resolve_event,
                candidate_multiplier=1,
            ).search(scope, runtime.query.query, limit=len(expanded.snippets))
            if native.rejected or len(native.snippets) != len(expanded.snippets):
                raise ValueError("matched-size native pool unavailable")
            pools = {}
            for profile, snippets in zip(
                PROFILES, (native.snippets, expanded.snippets), strict=True
            ):
                pool = [as_candidate(scope, s) for s in snippets]
                snippets = await validated(
                    store, scope, host, pool, runtime.query.query
                )
                request = preview(runtime.query.query, scope, snippets)
                if request_bytes(request) > STAGES["selector"][2]:
                    raise ValueError("source request exceeds frozen byte cap")
                pools[profile] = {
                    "pool": [c.model_dump(mode="json") for c in pool],
                    "count": len(pool),
                    "pool_sha256": _hash([c.model_dump(mode="json") for c in pool]),
                    "selector_request_sha256": _request_sha256(request),
                    "selector_request_bytes": request_bytes(request),
                }
            if corpus != digest(await inventory(store, [scope])):
                raise ValueError("source changed during preparation")
            receipt = {
                "ordinal": meta["ordinal"],
                "case_id": current,
                "raw_records": len(records),
                "corpus_sha256": corpus,
                "pools": pools,
                "expansion": expanded.model_dump(mode="json", exclude={"snippets"}),
            }
            save(args.run_dir / f"prepared-{meta['ordinal']}.json", receipt)
            receipts.append(receipt)
            print(
                f"prepared {len(receipts)}/5: {len(records)} raw messages, {len(expanded.snippets)} candidates per arm; zero LLM",
                flush=True,
            )
        status, failure = "complete", None
    except Exception as exc:  # noqa: BLE001 - do not expose credentials/provider text
        status, failure = "failed", type(exc).__name__
    finally:
        await store.close()
    return {
        "status": status,
        "failure_class": failure,
        "stopped_case": current if failure else None,
        "receipts": receipts,
        "raw_records": sum(r["raw_records"] for r in receipts),
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
        selector = BoundedTopKSelector(audit, SELECTION)
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
            if digest(records) != receipt["corpus_sha256"]:
                raise ValueError("prepared source changed")
            host, items = bind_host(runtime, manifest, scope, records, store)
            positions = {i["memory_id"]: p for p, i in items.items()}
            for profile in PROFILES:
                frozen = receipt["pools"][profile]
                pool = [RecallResult.model_validate(c) for c in frozen["pool"]]
                if (
                    len(pool) != frozen["count"]
                    or _hash([c.model_dump(mode="json") for c in pool])
                    != frozen["pool_sha256"]
                ):
                    raise ValueError("frozen pool changed")
                audit.expected_source_sha = frozen["selector_request_sha256"]
                stage = "llm-selection"
                context = await context_row(
                    store, scope, host, pool, runtime, scoring, profile, selector, items
                )
                context["candidate_turn_coverage"] = score_evidence(
                    scoring, [positions[c.memory_id] for c in pool]
                )
                if len(encoded(context["context"])) > 24000:
                    raise ValueError("packed context exceeds frozen limit")
                idx = len(rows)
                save(args.run_dir / f"context-{idx}.json", context)
                row = AnswerRow(
                    idx, case, profile, runtime, scoring, tuple(context["context"])
                )
                stage = "reader"
                output, record = await reader.execute(reader_request(row), idx)
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
                        idx,
                    )
                    entry.update(
                        checks=structural_check(row, output),
                        task_judge=judged,
                        grade=grade.model_dump(mode="json") if grade else None,
                    )
                rows.append(entry)
                save(args.run_dir / f"answer-{idx}.json", entry)
                if not output or not entry.get("grade"):
                    raise RuntimeError("QA failed; no retry")
                print(f"completed QA {len(rows)}/10 ({profile})", flush=True)
            stage = "final-store-validation"
            if digest(await inventory(store, [scope])) != receipt["corpus_sha256"]:
                raise ValueError("Store changed during read-only evaluation")
        status, failure = "complete", None
    except Exception as exc:  # noqa: BLE001 - redact arbitrary errors
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
    preparation = (
        json.loads(args.preparation.read_bytes()) if args.preparation else None
    )
    if args.phase == "evaluate":
        if preparation is None:
            parser.error("completed preparation required")
        validate_fingerprint(preparation["plan"], "plan_fingerprint")
    elif preparation is not None:
        parser.error("prepare phase cannot accept previous preparation")
    plan = make_plan(args.phase, manifest, preparation)
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
                prepare_run(args, cases, manifest, plan)
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
