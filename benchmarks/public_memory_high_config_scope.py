"""Natural-query runner for the preregistered consecutive diagnostic scopes.

Keeps first-query V1 runner/receipts intact. Execution V2 is separate from answer
quality; all source/model/context identities must be frozen before live calls.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Any

from benchmarks.high_config_execution_contract import assess_execution
from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_context_baseline import (
    execution_metadata,
    score_evidence,
    select_diagnostic_cases,
)
from benchmarks.public_context_rerank import LocalContextCrossEncoder
from benchmarks.public_memory_answer_comparison import (
    AnswerRow,
    _default_provider_factory,
)
from benchmarks.public_memory_clock_policy import (
    POLICIES,
    explicit_horizon,
    observation_policy,
)
from benchmarks.public_memory_comparison import inventory, load_bindings
from benchmarks.public_memory_expansion import (
    PrimaryOutput,
    config,
    local_diagnostic_dsn,
    primary_checks,
    primary_request,
    save,
)
from benchmarks.public_memory_graph_backfill import inspect_projection
from benchmarks.public_memory_graph_schema import snapshot, validate_definitions
from benchmarks.public_memory_high_config_context import (
    JournalSourceResolver,
    LocalRelationCrossEncoder,
    prepare_context,
)
from benchmarks.public_memory_high_config_first import (
    STAGES,
    ReadOnlyStore,
    ReadOnlyVectorIndex,
    RecordedPlannerModel,
    build_plan,
    persisted_generation,
    reader_request,
    vector_snapshot,
)
from benchmarks.public_memory_high_config_preflight import bound_scopes
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_reader_v2 import ReaderV2Output, structural_check
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_task_accuracy import Grade
from benchmarks.public_memory_task_accuracy import request as task_request
from doppel_memory.graphiti_store import GraphitiRelationIndex, GraphitiSemanticIndex
from doppel_memory.high_config import HighConfigRetrieval, HighConfigRetrievalResult
from doppel_memory.query_path import ReferencePersonalMemoryRelationPathPlannerV7
from doppel_memory.relation import RelationTypeDefinition

RUNNER = "doppel.public-memory-consecutive-high-config-query.v3"


def source_target(batch, ordinal):
    """Only a source-only frozen graph envelope can authorize a query scope."""
    if type(ordinal) is not int or not 2 <= ordinal <= 50:
        raise ValueError("invalid diagnostic scope ordinal")
    runner = batch.get("runner")
    if runner == "doppel.public-memory-consecutive-graph-batch.v1":
        if ordinal not in {2, 3}:
            raise ValueError("scope not in original fixed graph batch")
    elif runner == "doppel.public-memory-next-source-history-graph.v1":
        if (
            type(batch.get("previous_scope_ordinal")) is not int
            or batch.get("target_scope_ordinal") != batch["previous_scope_ordinal"] + 1
            or ordinal != batch["target_scope_ordinal"]
            or len(batch.get("scope_plans", [])) != 1
        ):
            raise ValueError("scope not bound to consecutive source-only envelope")
    else:
        raise ValueError("unknown source graph envelope")
    targets = [
        p for p in batch.get("scope_plans", []) if p.get("scope_ordinal") == ordinal
    ]
    if len(targets) != 1:
        raise ValueError("one exact source scope plan required")
    return targets[0]


def scope_plan(
    binding,
    runtime,
    scope,
    schema,
    corpus,
    vectors,
    reranker,
    ordinal,
    batch,
    clock_policy="strict-reference-v1",
):
    source_target(batch, ordinal)
    plan = build_plan(binding, runtime, scope, schema, corpus, vectors, reranker)
    plan.update(
        runner=RUNNER,
        scope_ordinal=ordinal,
        selection="preregistered-consecutive-ingestion-order-no-answer-selection",
        batch_plan_fingerprint=batch["plan_fingerprint"],
        execution_contract="doppel.high-config-execution-contract.v2",
        observation_clock=observation_policy(runtime, clock_policy),
    )
    for file in [
        Path(__file__),
        Path("benchmarks/high_config_execution_contract.py"),
        Path("benchmarks/public_memory_clock_policy.py"),
    ]:
        plan["source_sha256"][file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
    plan["plan_fingerprint"] = _hash(
        {k: v for k, v in plan.items() if k != "plan_fingerprint"}
    )
    return plan


async def query_and_answer(
    args, prepared, scope, records, sources, definitions, vector, client, reranker, plan
):
    runtime, scoring = prepared
    clock = observation_policy(runtime, args.clock_policy)
    if plan["observation_clock"] != clock:
        raise ValueError("bound observation policy changed")
    ledgers, models = {}, {}
    report: dict[str, Any] = {"status": "failed"}
    args.run_dir.mkdir(parents=True, exist_ok=True)
    _bind_json(args.run_dir / "plan.json", plan)
    key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not args.cache_only and not key:
        raise ValueError("key environment absent")
    try:
        for stage, (calls, tokens) in STAGES.items():
            ledger = DurableCallLedger(
                args.run_dir / f"{stage}.sqlite3",
                budget_id=plan["plan_fingerprint"] + ":" + stage,
                max_calls=calls,
                max_request_bytes=500_000,
                max_total_request_bytes=calls * 500_000,
            )
            ledgers[stage] = ledger
            models[stage] = PilotStructuredModel(
                _default_provider_factory(config(tokens), key, ledger.observe_usage),
                ledger=ledger,
                cache_dir=args.run_dir / stage,
                cache_only=args.cache_only,
            )
        checkpoint = args.run_dir / "retrieval.json"
        if checkpoint.exists():
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            if saved["plan_fingerprint"] != plan["plan_fingerprint"]:
                raise ValueError("retrieval checkpoint identity mismatch")
            result = HighConfigRetrievalResult.model_validate(saved["result"])
            report["retrieval_execution"] = "immutable-checkpoint-replay"
        else:
            marker = args.run_dir / "retrieval-attempt.json"
            if marker.exists() or args.cache_only:
                raise ValueError(
                    "no silent retry or new retrieval in checkpoint replay"
                )
            save(
                marker,
                {"plan_fingerprint": plan["plan_fingerprint"], "status": "started"},
            )
            relation = GraphitiRelationIndex(vector._store, graphiti_client=client)
            host = HighConfigRetrieval(
                vector._store,
                semantic_index=vector,
                relation_index=relation,
                path_index=relation,
                exploration_index=relation,
                planner=ReferencePersonalMemoryRelationPathPlannerV7(
                    RecordedPlannerModel(
                        models["planner"], args.run_dir / "planner-requests.json"
                    )
                ),
                memory_reranker=reranker,
                path_reranker=LocalRelationCrossEncoder(reranker),
                source_resolver=JournalSourceResolver(vector._store, sources),
                relation_definitions=definitions,
            )
            start = perf_counter()
            result = await host.query(
                runtime.query.query,
                [scope],
                now=runtime.query.reference_time,
                observed_until=explicit_horizon(clock),
                default_subject_id=scope.user_id,
                trace_limit=100,
            )
            save(
                checkpoint,
                {
                    "plan_fingerprint": plan["plan_fingerprint"],
                    "result": result.model_dump(mode="json"),
                    "reranker": reranker.report(),
                    "retrieval_ms": (perf_counter() - start) * 1000,
                },
            )
            report["retrieval_execution"] = "live-production-high-config"
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        context, packing = prepare_context(result, records, sources)
        row = AnswerRow(
            0,
            scoring.case_id,
            "personal-high-config-" + clock["policy"],
            runtime,
            scoring,
            tuple(context),
        )
        report.update(
            case_id=scoring.case_id,
            question=runtime.query.query,
            context=context,
            packing=packing,
            retrieval=result.model_dump(mode="json"),
            reranker=saved["reranker"],
            retrieval_ms=saved["retrieval_ms"],
            execution=assess_execution(result.model_dump(mode="json")),
        )
        reader = await persisted_generation(
            models["reader"],
            reader_request(row, result),
            ReaderV2Output,
            args.run_dir / "reader-output.json",
        )
        report.update(
            reader=reader.model_dump(mode="json"),
            reader_checks=structural_check(row, reader),
        )
        grade = await persisted_generation(
            models["task_judge"],
            task_request(runtime.query.query, scoring.answer, reader.answer),
            Grade,
            args.run_dir / "task-output.json",
        )
        support = await persisted_generation(
            models["citation_judge"],
            primary_request(row, reader),
            PrimaryOutput,
            args.run_dir / "citation-output.json",
        )
        positions = [
            sources[(scope.scope_key, event)].position
            for item in context
            for event in item["source_events"]
        ]
        report.update(
            task_grade=grade.model_dump(mode="json"),
            citation_grade=support.model_dump(mode="json"),
            citation_checks=primary_checks(row, support),
            evidence_score=score_evidence(scoring, positions),
            reference_answer=scoring.answer,
            status="complete",
        )
    except Exception as error:  # noqa: BLE001 - sanitized credential/provider boundary
        report.update(status="failed", failure_type=type(error).__name__)
    finally:
        report["usage"] = {stage: model.report() for stage, model in models.items()}
        for ledger in ledgers.values():
            ledger.close()
    return report


async def run(args):
    paths = {
        k: getattr(args, k)
        for k in ["dataset", "manifest", "ingestion", "backfill", "schema"]
    }
    content = {k: p.read_bytes() for k, p in paths.items()}
    binding = {k: hashlib.sha256(v).hexdigest() for k, v in content.items()}
    manifest, ingestion, backfill, schema = (
        json.loads(content[k]) for k in ["manifest", "ingestion", "backfill", "schema"]
    )
    cases = select_diagnostic_cases(
        json.loads(content["dataset"]), manifest, source_sha256=binding["dataset"]
    )
    scopes = bound_scopes(manifest, ingestion)
    ordinal = args.scope_ordinal
    scope, prepared = scopes[ordinal - 1], cases[ordinal - 1]
    batch = backfill["plan"]
    target = source_target(batch, ordinal)
    for plan in [batch, target, schema["plan"]]:
        if (
            _hash({k: v for k, v in plan.items() if k != "plan_fingerprint"})
            != plan["plan_fingerprint"]
        ):
            raise ValueError("source plan fingerprint mismatch")
    if (
        backfill["status"] != "complete"
        or not backfill["selected_scope_projection_complete"]
        or backfill["scope_ordinal"] != ordinal
        or backfill["graph_plan"] != target
        or not all(
            backfill[k]
            for k in ["corpus_unchanged", "vectors_unchanged", "other_scopes_unchanged"]
        )
        or batch["binding"]["manifest"] != binding["manifest"]
        or batch["binding"]["ingestion"] != binding["ingestion"]
        or {r["scope_key"] for r in target["records"]} != {scope.scope_key}
        or schema["status"] != "complete"
        or schema["plan"]["source"]["scope_key"] != scope.scope_key
    ):
        raise ValueError("complete preregistered scope coverage/schema required")
    definitions = [
        RelationTypeDefinition.model_validate(d)
        for d in validate_definitions(
            schema["plan"]["source"]["relation_names"],
            {"definitions": schema["definitions"]},
        )
    ]
    sources = load_bindings(
        [p[0] for p in cases], manifest, ingestion, args.ingestion_dir
    )
    binding["source_journal"] = hashlib.sha256(
        (args.ingestion_dir / "ingestion.sqlite3").read_bytes()
    ).hexdigest()
    embedder = _LocalEmbeddingProvider(cache_dir=args.embedding_cache)
    if {
        "name": embedder.name,
        "version": embedder.version,
        "dimensions": embedder.dimensions,
    } != ingestion["embedding"]:
        raise ValueError("embedding identity mismatch")
    reranker = LocalContextCrossEncoder(args.reranker_model, device="cuda")
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"),
        schema=ingestion["postgres_schema"],
    )
    from graphiti_core.driver.neo4j_driver import Neo4jDriver

    from benchmarks.evidence_rich_blind_diagnostic import local_credentials

    class ReadOnlyDriver(Neo4jDriver):
        async def build_indices_and_constraints(self):
            return None

    _, password, _ = local_credentials()
    driver = ReadOnlyDriver("bolt://127.0.0.1:7687", "neo4j", password)
    client = SimpleNamespace(driver=driver)
    report = {
        "runner": RUNNER,
        "clock_policy": args.clock_policy,
        "status": "ready",
        "publication_ready": False,
        "judgments_independently_verified": False,
        "record_or_index_writes": 0,
        "reserved_histories_executed": False,
        "scope_ordinal": ordinal,
    }
    try:
        records = await inventory(store, scopes)
        corpus = _hash({k: r.model_dump(mode="json") for k, r in records.items()})
        if corpus != batch["corpus_sha256"]:
            raise ValueError("corpus changed")
        vector = ReadOnlyVectorIndex(store, embedder)
        vectors = await vector_snapshot(store, vector, records, scopes)
        if (
            vectors != batch["vectors"]
            or await snapshot(scope.scope_key) != schema["plan"]["source"]
        ):
            raise ValueError("frozen vector/graph snapshot mismatch")
        projection = GraphitiSemanticIndex(store, graphiti_client=client)
        checks = [
            await inspect_projection(client, projection, records[r["memory_id"]])
            for r in target["records"]
        ]
        if any(not c["complete"] for c in checks):
            raise ValueError("graph projection no longer matches Store")
        plan = scope_plan(
            binding,
            prepared[0],
            scope,
            schema,
            corpus,
            vectors,
            reranker,
            ordinal,
            batch,
            args.clock_policy,
        )
        report.update(plan=plan, projection_count=len(checks))
        if args.live:
            if (
                not args.frozen_preflight
                or json.loads(args.frozen_preflight.read_text(encoding="utf-8"))["plan"]
                != plan
            ):
                raise ValueError("unchanged frozen query preflight required")
            report.update(
                await query_and_answer(
                    args,
                    prepared,
                    scope,
                    records,
                    sources,
                    definitions,
                    vector,
                    client,
                    reranker,
                    plan,
                )
            )
        after = await inventory(store, scopes)
        report["corpus_unchanged"] = (
            _hash({k: r.model_dump(mode="json") for k, r in after.items()}) == corpus
        )
        report["vectors_unchanged"] = (
            await vector_snapshot(store, vector, after, scopes) == vectors
        )
        report["graph_unchanged"] = (
            await snapshot(scope.scope_key) == schema["plan"]["source"]
        )
        if not all(
            report[k]
            for k in ["corpus_unchanged", "vectors_unchanged", "graph_unchanged"]
        ):
            report["status"] = "integrity_failed"
        report["execution_metadata"] = execution_metadata()
        return report
    finally:
        await store.close()
        await driver.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in [
        "dataset",
        "manifest",
        "ingestion",
        "ingestion-dir",
        "backfill",
        "schema",
        "reranker-model",
        "embedding-cache",
        "run-dir",
        "output",
    ]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--scope-ordinal", type=int, required=True)
    parser.add_argument(
        "--clock-policy", choices=POLICIES, default="strict-reference-v1"
    )
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("preserve output; cache-only requires live")
    report = asyncio.run(run(args))
    save(args.output, report)
    print(
        json.dumps(
            {
                k: report.get(k)
                for k in ["status", "scope_ordinal", "task_grade", "failure_type"]
            }
        )
    )
    return 0 if report["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
