"""Frozen opened-three top-k smoke, preserving the failed full-permutation run."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_memory_answer_comparison import (
    AnswerRow,
    _default_provider_factory,
    _request_sha256,
    _StageExecutor,
)
from benchmarks.public_memory_comparison import encoded, inventory, pack_ranked_fit
from benchmarks.public_memory_expansion import config, local_diagnostic_dsn, save
from benchmarks.public_memory_high_config_first import (
    ReadOnlyStore,
    ReadOnlyVectorIndex,
)
from benchmarks.public_memory_listwise_diagnostic import (
    AuditedRankModel,
    NoGenerate,
    get_pool,
    load_inputs,
    request_bytes,
)
from benchmarks.public_memory_passage_diagnostic import (
    CASES,
    SavedOrder,
    passage_item,
    reader_request,
)
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_reader_v2 import ReaderV2Output, structural_check
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_source_aware_diagnostic import SavedCandidates
from benchmarks.public_memory_task_accuracy import Grade
from benchmarks.public_memory_task_accuracy import request as task_request
from doppel_memory.models import RecallResult
from doppel_memory.reference_selection import ReferenceTopKSelector, TopKSelectionConfig
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.passages import AttributedPassageRetriever

RUNNER = "doppel.topk-opened-three.v1"
PROFILE = "metadata_top20_selected_unranked"
STAGES = {
    "selector": (6, 1024, 500000, 1500000),
    "reader": (3, 2048, 100000, 300000),
    "judge": (3, 1024, 100000, 300000),
}
SETTINGS = TopKSelectionConfig(timeout_seconds=300)
PRIOR_FAILURE = Path("data/doppel/listwise-diagnostic-live-v1.json")


def preview_request(query, scope, snippets):
    return ReferenceTopKSelector(NoGenerate(), SETTINGS).build_request(
        query,
        [
            RecallResult(
                scope=scope,
                memory_id=s.memory_id,
                fact=s.text,
                raw_text=s.text,
                actor=s.actor,
                authority=s.authority,
                valid_at=s.at,
                source_event_id=s.evidence_id,
                similarity=s.similarity,
            )
            for s in snippets
        ],
        limit=20,
    )


async def prepared_pool(store, index, runtime, scoring, manifest, data):
    scope, host, pool, certificate = await get_pool(
        store, index, runtime, scoring, manifest, data["parent"], data["pool_parent"]
    )
    source = AttributedContextRetriever(
        store, strategy=SavedCandidates(pool), resolve_event=host.resolve_event
    )
    validated = await source.search(scope, runtime.query.query, limit=80)
    if validated.rejected or len(validated.snippets) != len(pool):
        raise ValueError(
            "selection preflight requires the entire authorized source pool"
        )
    request = preview_request(runtime.query.query, scope, validated.snippets)
    certificate = {
        **certificate,
        "source_request_sha256": _request_sha256(request),
        "source_request_bytes": request_bytes(request),
        "source_content_chars": sum(len(i["content"]) for i in request.input["items"]),
        "select_count": request.input["select_count"],
    }
    return scope, host, pool, certificate


def make_plan(hashes, certificates, schema):
    prior = json.loads(PRIOR_FAILURE.read_bytes())
    if (
        prior["status"] != "failed"
        or prior["usage"]["ranker"]["attempts_reserved"] != 1
    ):
        raise ValueError("preserve the existing failed permutation run")
    value = {
        "runner": RUNNER,
        "binding": hashes,
        "cases": list(CASES),
        "profile": PROFILE,
        "schema": schema,
        "certificates": certificates,
        "source_limit": 20,
        "passage_limit": 80,
        "output_limit": 20,
        "context_byte_limit": 24000,
        "selection_config": SETTINGS.model_dump(),
        "unselected_status": "unranked-no-scores",
        "stages": {
            name: {
                "max_calls": cap,
                "config": config(tokens).model_dump(mode="json"),
                "max_request_bytes": size,
                "max_total_request_bytes": total,
            }
            for name, (cap, tokens, size, total) in STAGES.items()
        },
        "prior_failed_report_sha256": hashlib.sha256(
            PRIOR_FAILURE.read_bytes()
        ).hexdigest(),
        "prior_spend_not_reallocated": {
            "attempts": 1,
            "total_tokens": prior["usage"]["ranker"]["reported_tokens"]["total_tokens"],
        },
        "source_sha256": {
            path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in (
                __file__,
                "doppel_memory/reference_selection.py",
                "doppel_memory/source_aware_rerank.py",
                "integrations/aml/context.py",
                "integrations/aml/passages.py",
                "benchmarks/public_memory_listwise_diagnostic.py",
                "benchmarks/public_memory_passage_diagnostic.py",
                "benchmarks/public_memory_reader_v2.py",
                "benchmarks/public_memory_task_accuracy.py",
            )
        },
        "opened_not_independent": True,
        "publication_ready": False,
        "graph_calls": 0,
        "automatic_retries": 0,
        "baseline_new_calls": 0,
        "repair_prior_output": False,
    }
    if any(c["source_request_bytes"] > STAGES["selector"][2] for c in certificates):
        raise ValueError("source request exceeds frozen byte cap")
    return {**value, "plan_fingerprint": _hash(value)}


async def execute(args, data, manifest, selected, baselines, plan, store, index):
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        raise ValueError("provider key absent")
    save(args.run_dir / "attempt.json", {"plan": plan})
    ledgers, models, rows = {}, {}, []
    audited = None
    case, stage = None, "initialization"
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
                raise ValueError("preserve prior attempts; no implicit recovery")
            models[name] = PilotStructuredModel(
                _default_provider_factory(
                    config(STAGES[name][1]),
                    os.environ["DEEPSEEK_API_KEY"],
                    ledger.observe_usage,
                ),
                ledger=ledger,
                cache_dir=args.run_dir / name,
            )
        audited = AuditedRankModel(models["selector"], args.run_dir)
        selector = ReferenceTopKSelector(audited, SETTINGS)
        reader = _StageExecutor(
            models["reader"], ledgers["reader"], ReaderV2Output, cache_only=False
        )
        judge = _StageExecutor(
            models["judge"], ledgers["judge"], Grade, cache_only=False
        )
        for i, (runtime, scoring) in enumerate(selected):
            case, stage = scoring.case_id, "source-preflight"
            scope, host, pool, certificate = await prepared_pool(
                store, index, runtime, scoring, manifest, data
            )
            if certificate != plan["certificates"][i]:
                raise ValueError("preflight certificate changed")
            audited.expected_source_sha = certificate["source_request_sha256"]
            stage = "source-selection"
            sources = await AttributedContextRetriever(
                store,
                strategy=SavedCandidates(pool),
                resolve_event=host.resolve_event,
                reranker=selector,
            ).search(scope, runtime.query.query, limit=20)
            source_selection = (
                selector.last_selection.model_dump(mode="json")
                if selector.last_selection
                else None
            )
            source_parent = AttributedContextRetriever(
                store,
                strategy=SavedOrder(scope, [s.memory_id for s in sources.snippets]),
                resolve_event=host.resolve_event,
            )
            resolver = AttributedPassageRetriever(source_parent, reranker=selector)
            stage = "passage-selection"
            result = await resolver.search(scope, runtime.query.query, limit=20)
            passage_selection = (
                selector.last_selection.model_dump(mode="json")
                if selector.last_selection
                else None
            )
            for passage in result.passages:
                await resolver.resolve_original(scope, passage)
            packed, trace = pack_ranked_fit([passage_item(p) for p in result.passages])
            entry = {
                "case_id": case,
                "profile": PROFILE,
                "context": packed,
                "context_bytes": len(encoded(packed)),
                "context_sha256": hashlib.sha256(encoded(packed)).hexdigest(),
                "source_events": [s.evidence_id for s in sources.snippets],
                "source_positions": [
                    [s.session_id, s.transport_turn_index] for s in sources.snippets
                ],
                "source_selection": source_selection,
                "passage_selection": passage_selection,
                "source_execution": sources.model_dump(
                    mode="json", exclude={"snippets"}
                ),
                "passage_execution": result.model_dump(
                    mode="json", exclude={"passages"}
                ),
                "packing_trace": trace,
                "certificate": certificate,
            }
            save(args.run_dir / f"context-{i}.json", entry)
            stage = "reader"
            row = AnswerRow(i, case, PROFILE, runtime, scoring, tuple(packed))
            output, record = await reader.execute(reader_request(row), i)
            entry.update(
                reader=record,
                reader_output=output.model_dump(mode="json") if output else None,
            )
            if output:
                stage = "task-judge"
                grade, judged = await judge.execute(
                    task_request(runtime.query.query, scoring.answer, output.answer), i
                )
                entry.update(
                    checks=structural_check(row, output),
                    task_judge=judged,
                    grade=grade.model_dump(mode="json") if grade else None,
                )
            stage = "final-store-check"
            after = await inventory(store, [scope])
            if certificate["corpus_sha256"] != _hash(
                {k: r.model_dump(mode="json") for k, r in after.items()}
            ):
                raise ValueError("Store changed during read-only comparison")
            rows.append(entry)
            save(args.run_dir / f"answer-{i}.json", entry)
            print(f"completed {case}: grade={entry.get('grade')}", flush=True)
            if not output or not entry.get("grade"):
                raise RuntimeError("answer stage failed; no retry")
        status, failure = "complete", None
    except Exception as exc:  # noqa: BLE001 - do not persist arbitrary provider errors
        status, failure = "failed", type(exc).__name__
    result = {
        "runner": RUNNER,
        "status": status,
        "plan": plan,
        "rows": rows,
        "reused_baselines": baselines,
        "usage": {k: v.report() for k, v in ledgers.items()},
        "model_cache": {k: v.report() for k, v in models.items()},
        "selection_requests": audited.requests if audited else [],
        "failure_class": failure,
        "stopped_case": case if failure else None,
        "stopped_stage": stage if failure else None,
    }
    for ledger in ledgers.values():
        ledger.close()
    return result


async def run(args):
    data, hashes, manifest, selected, baselines = load_inputs()
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"),
        schema=data["parent"]["plan"]["schema"],
    )
    index = ReadOnlyVectorIndex(store, _LocalEmbeddingProvider(cache_dir=None))
    try:
        certificates = []
        for runtime, scoring in selected:
            *_, certificate = await prepared_pool(
                store, index, runtime, scoring, manifest, data
            )
            certificates.append(certificate)
        plan = make_plan(hashes, certificates, data["parent"]["plan"]["schema"])
        if not args.execute:
            return {"runner": RUNNER, "status": "ready", "plan": plan, "new_calls": 0}
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            raise ValueError("matching frozen preflight required before paid execution")
        return await execute(
            args, data, manifest, selected, baselines, plan, store, index
        )
    finally:
        await store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("fresh output required")
    result = asyncio.run(run(args))
    save(args.output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "new_attempts": sum(
                    v["attempts_reserved"] for v in result.get("usage", {}).values()
                ),
            }
        )
    )
    raise SystemExit(0 if result["status"] in {"ready", "complete"} else 1)


if __name__ == "__main__":
    main()
