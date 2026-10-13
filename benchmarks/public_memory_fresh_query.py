"""Two frozen profiles for one closed, fully graph-indexed prospective history.

Reuse existing production retrieval, Reader v2 and provisional judges. No tuning,
answer-aware packing, repair, source writes or promotion of graph-only scores.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from benchmarks.evidence_rich_blind_diagnostic import local_credentials
from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_context_baseline import execution_metadata, score_evidence
from benchmarks.public_context_rerank import (
    LocalContextCrossEncoder,
    StrictContextReranker,
)
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_answer_comparison import (
    AnswerRow,
    _default_provider_factory,
)
from benchmarks.public_memory_clock_policy import observation_policy
from benchmarks.public_memory_comparison import (
    context_item,
    inventory,
    pack_context,
    positions,
    select_candidates,
)
from benchmarks.public_memory_expansion import (
    PrimaryOutput,
    local_diagnostic_dsn,
    primary_checks,
    primary_request,
    save,
)
from benchmarks.public_memory_fresh_cohort import NAMESPACE, validate_fingerprint
from benchmarks.public_memory_fresh_graph import closed_source, scoped_bindings
from benchmarks.public_memory_graph_backfill import inspect_projection
from benchmarks.public_memory_graph_schema import snapshot, validate_definitions
from benchmarks.public_memory_high_config_first import (
    ReadOnlyStore,
    ReadOnlyVectorIndex,
    build_plan,
    persisted_generation,
    vector_snapshot,
)
from benchmarks.public_memory_high_config_scope import query_and_answer
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_reader_v2 import (
    ReaderV2Output,
    build_request,
    structural_check,
)
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_task_accuracy import Grade
from benchmarks.public_memory_task_accuracy import request as task_request
from doppel_memory.graphiti_store import GraphitiSemanticIndex
from doppel_memory.models import MemoryFilter, MemoryState
from doppel_memory.openai_compatible import OpenAICompatibleStructuredOutputConfig
from doppel_memory.relation import RelationTypeDefinition

RUNNER = "doppel.public-memory-fresh-profile-query.v1"
PROFILES = ("full_high_config", "raw_vector_reranked")


def validate_graph(graph, cohort, ordinal):
    plan = graph["plan"]
    validate_fingerprint(plan, "plan_fingerprint")
    certificate = plan["source_completion_certificate"]
    if (
        graph["runner"] != "doppel.public-memory-fresh-scope-graph.v1"
        or graph["status"] != "complete"
        or graph.get("selected_scope_projection_complete") is not True
        or graph.get("full_corpus_graph_coverage_certified") is not False
        or graph["scope_ordinal"] != ordinal
        or certificate["scope_ordinal"] != ordinal
        or certificate["cohort_plan_fingerprint"] != cohort["plan_fingerprint"]
        or graph["completed_records"] != plan["eligible_records"]
        or len(graph["checks"]) != plan["eligible_records"]
        or not all(c["complete"] for c in graph["checks"])
        or not all(
            graph[k]
            for k in [
                "corpus_unchanged",
                "vectors_unchanged",
                "source_journal_unchanged",
                "other_cohort_graph_scopes_unchanged",
            ]
        )
    ):
        raise ValueError("complete immutable selected-scope graph required")
    return certificate


def profile_plan(base, cohort, ordinal, profile):
    if profile not in PROFILES or type(ordinal) is not int or ordinal < 1:
        raise ValueError("invalid fixed profile or ordinal")
    for k, expected in {
        "query_config": cohort["query_config"],
        "rerank_config": cohort["memory_rerank"],
        "hybrid_config": cohort["hybrid_config"],
    }.items():
        if base[k] != expected:
            raise ValueError("frozen retrieval configuration changed")
    if any(
        base["stages"][k]["config"] != v["provider"]
        or base["stages"][k]["max_calls"] != v["calls_per_question"]
        for k, v in cohort["stage_configs"].items()
    ):
        raise ValueError("frozen provider configuration changed")
    plan = {
        **base,
        "runner": RUNNER,
        "scope_ordinal": ordinal,
        "profile": profile,
        "cohort_plan_fingerprint": cohort["plan_fingerprint"],
        "observation_clock": base["observation_clock"],
        "profile_execution_order": list(
            PROFILES if ordinal % 2 else reversed(PROFILES)
        ),
        "implementation_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "source_writer_calls": 0,
        "graph_writer_calls": 0,
        "publication_ready": False,
    }
    if profile == "raw_vector_reranked":
        plan["stages"] = {k: v for k, v in plan["stages"].items() if k != "planner"}
    plan.pop("plan_fingerprint")
    return {**plan, "plan_fingerprint": _hash(plan)}


async def raw_answer(args, prepared, scope, records, sources, vector, reranker, plan):
    runtime, scoring = prepared
    args.run_dir.mkdir(parents=True, exist_ok=True)
    _bind_json(args.run_dir / "plan.json", plan)
    models, ledgers = {}, {}
    report = {
        "status": "failed",
        "profile": "raw_vector_reranked",
        "case_id": scoring.case_id,
    }
    key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "").strip()
    try:
        if not args.cache_only and not key:
            raise ValueError("provider key absent")
        for stage, settings in plan["stages"].items():
            ledger = DurableCallLedger(
                args.run_dir / (stage + ".sqlite3"),
                budget_id=plan["plan_fingerprint"] + ":" + stage,
                max_calls=settings["max_calls"],
                max_request_bytes=settings["max_request_bytes"],
                max_total_request_bytes=settings["max_total_request_bytes"],
            )
            ledgers[stage] = ledger
            models[stage] = PilotStructuredModel(
                _default_provider_factory(
                    OpenAICompatibleStructuredOutputConfig.model_validate(
                        settings["config"]
                    ),
                    key,
                    ledger.observe_usage,
                ),
                ledger=ledger,
                cache_dir=args.run_dir / stage,
                cache_only=args.cache_only,
            )
        checkpoint = args.run_dir / "retrieval.json"
        if checkpoint.exists():
            saved = json.loads(checkpoint.read_bytes())
            if saved["plan_fingerprint"] != plan["plan_fingerprint"]:
                raise ValueError("raw retrieval checkpoint changed")
        else:
            marker = args.run_dir / "retrieval-attempt.json"
            if args.cache_only or marker.exists():
                raise ValueError("no new retrieval or silent retry in replay")
            save(
                marker,
                {"plan_fingerprint": plan["plan_fingerprint"], "status": "started"},
            )
            ordered = await vector.search(
                runtime.query.query,
                [scope],
                filters=MemoryFilter(states={MemoryState.CONFIRMED}),
                limit=len(records),
            )
            if {c.memory_id for c in ordered} != {
                r.memory_id
                for r in records.values()
                if r.state == MemoryState.CONFIRMED
            }:
                raise ValueError("exhaustive baseline vector ordering incomplete")
            items = {
                k: item
                for k, r in records.items()
                if (item := context_item(r, records, sources)) is not None
            }
            candidates = select_candidates(ordered, items, scope, "raw")
            strict = StrictContextReranker(reranker)
            ranking = await strict.rerank(runtime.query.query, candidates, limit=20)
            context = pack_context([items[c.memory_id] for c in ranking])
            saved = {
                "plan_fingerprint": plan["plan_fingerprint"],
                "context": context,
                "candidate_count": len(candidates),
                "rerank_summary": strict.last_summary.model_dump(mode="json")
                if strict.last_summary
                else None,
                "reranker": reranker.report(),
            }
            save(checkpoint, saved)
        for item in saved["context"]:
            if (
                await vector._store.get(scope, item["memory_id"])
                != records[item["memory_id"]]
            ):
                raise ValueError("source changed after raw ranking")
        row = AnswerRow(
            0,
            scoring.case_id,
            "raw_vector_reranked",
            runtime,
            scoring,
            tuple(saved["context"]),
        )
        reader = await persisted_generation(
            models["reader"],
            build_request(row),
            ReaderV2Output,
            args.run_dir / "reader-output.json",
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
        report.update(
            status="complete",
            question=runtime.query.query,
            reference_answer=scoring.answer,
            context=saved["context"],
            reader=reader.model_dump(mode="json"),
            reader_checks=structural_check(row, reader),
            task_grade=grade.model_dump(mode="json"),
            citation_grade=support.model_dump(mode="json"),
            citation_checks=primary_checks(row, support),
            evidence_score=score_evidence(
                scoring, positions(saved["context"], sources)
            ),
            retrieval=saved,
        )
    except Exception as error:  # noqa: BLE001 - no provider/credential text
        report["failure_type"] = type(error).__name__
    finally:
        report["usage"] = {k: m.report() for k, m in models.items()}
        for ledger in ledgers.values():
            ledger.close()
    return report


async def run(args):
    paths = {
        k: getattr(args, k)
        for k in [
            "dataset",
            "manifest",
            "cohort_plan",
            "parent_report",
            "backfill",
            "schema",
        ]
    }
    content = {k: p.read_bytes() for k, p in paths.items()}
    raw, manifest, cohort, parent, graph, schema = (
        json.loads(content[k]) for k in paths
    )
    certificate = validate_graph(graph, cohort, args.scope_ordinal)
    scope, source_runtime, sources, current = closed_source(
        raw,
        manifest,
        cohort,
        parent,
        source_sha=hashlib.sha256(content["dataset"]).hexdigest(),
        ordinal=args.scope_ordinal,
        ingestion_dir=args.ingestion_dir,
    )
    if current["journal_sha256"] != certificate["journal_sha256"]:
        raise ValueError("closed source changed")
    if (
        schema["status"] != "complete"
        or not schema["graph_unchanged"]
        or schema["plan"]["source"]["scope_key"] != scope.scope_key
    ):
        raise ValueError("complete matching source-only schema required")
    validate_fingerprint(schema["plan"], "plan_fingerprint")
    definitions = [
        RelationTypeDefinition.model_validate(d)
        for d in validate_definitions(
            schema["plan"]["source"]["relation_names"],
            {"definitions": schema["definitions"]},
        )
    ]
    # Only after source/graph readiness do we open the selected actual query/gold.
    selected = [c for c in manifest["cases"] if c["partition"] == "diagnostic"][
        args.scope_ordinal - 1
    ]
    prepared_case = prepare_case(
        next(r for r in raw if r["question_id"] == selected["case_id"]),
        dataset_namespace=NAMESPACE,
    )
    prepared = prepared_case.runtime, prepared_case.scoring
    if (
        prepared[0].sessions != source_runtime.sessions
        or prepared[0].user_id != source_runtime.user_id
    ):
        raise ValueError("query runtime changed source history")
    embedder = _LocalEmbeddingProvider(cache_dir=None)
    if {
        "name": embedder.name,
        "version": embedder.version,
        "dimensions": embedder.dimensions,
    } != parent["ingestion"]["embedding"]:
        raise ValueError("embedding identity changed")
    reranker = LocalContextCrossEncoder(args.reranker_model, device="cuda")
    identity = reranker.report()
    if identity["name"] != "local-cross-encoder:" + cohort["reranker"]["model"] or any(
        identity[k] != cohort["reranker"][alias]
        for k, alias in [
            ("device_requested", "device"),
            ("max_length", "max_length"),
            ("batch_size", "batch_size"),
        ]
    ):
        raise ValueError("frozen local reranker configuration changed")
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"),
        schema=parent["ingestion"]["postgres_schema"],
    )
    Neo4jDriver = importlib.import_module(
        "graphiti_core.driver.neo4j_driver"
    ).Neo4jDriver

    class ReadOnlyDriver(Neo4jDriver):
        async def build_indices_and_constraints(self):
            return None

    _, password, _ = local_credentials()
    driver = ReadOnlyDriver("bolt://127.0.0.1:7687", "neo4j", password)
    client = SimpleNamespace(driver=driver)
    try:
        records = await inventory(store, [scope])
        corpus = _hash({k: r.model_dump(mode="json") for k, r in records.items()})
        vector = ReadOnlyVectorIndex(store, embedder)
        vectors = await vector_snapshot(store, vector, records, [scope])
        if (
            corpus != graph["plan"]["corpus_sha256"]
            or vectors != certificate["vectors"]
            or await snapshot(scope.scope_key) != schema["plan"]["source"]
        ):
            raise ValueError("frozen source/vector/graph snapshot changed")
        index = GraphitiSemanticIndex(store, graphiti_client=client)
        for target in graph["plan"]["records"]:
            if not (
                await inspect_projection(client, index, records[target["memory_id"]])
            )["complete"]:
                raise ValueError("graph no longer matches authoritative Store")
        base = build_plan(
            {k: hashlib.sha256(v).hexdigest() for k, v in content.items()},
            prepared[0],
            scope,
            schema,
            corpus,
            vectors,
            reranker,
        )
        base["observation_clock"] = observation_policy(
            prepared[0], cohort["clock_policy"]
        )
        plans = {p: profile_plan(base, cohort, args.scope_ordinal, p) for p in PROFILES}
        report = {
            "runner": RUNNER,
            "status": "ready",
            "scope_ordinal": args.scope_ordinal,
            "plans": plans,
            "rows": [],
            "publication_ready": False,
            "judgments_independently_verified": False,
            "official_longmemeval_score": False,
            "aml_score": False,
        }
        if args.live:
            if (
                not args.frozen_preflight
                or json.loads(args.frozen_preflight.read_bytes())["plans"] != plans
            ):
                raise ValueError("unchanged frozen two-profile query plans required")
            for profile in plans[PROFILES[0]]["profile_execution_order"]:
                child = SimpleNamespace(
                    run_dir=args.run_dir / profile,
                    cache_only=args.cache_only,
                    clock_policy=cohort["clock_policy"],
                )
                if profile == "full_high_config":
                    row = await query_and_answer(
                        child,
                        prepared,
                        scope,
                        records,
                        sources,
                        definitions,
                        vector,
                        client,
                        reranker,
                        plans[profile],
                    )
                else:
                    row = await raw_answer(
                        child,
                        prepared,
                        scope,
                        records,
                        sources,
                        vector,
                        reranker,
                        plans[profile],
                    )
                row["profile"] = profile
                report["rows"].append(row)
                save(args.run_dir / (profile + "-receipt.json"), row)
            report["status"] = (
                "complete"
                if all(r["status"] == "complete" for r in report["rows"])
                else "partial"
            )
        after = await inventory(store, [scope])
        report["corpus_unchanged"] = (
            _hash({k: r.model_dump(mode="json") for k, r in after.items()}) == corpus
        )
        report["vectors_unchanged"] = (
            await vector_snapshot(store, vector, after, [scope]) == vectors
        )
        report["graph_unchanged"] = (
            await snapshot(scope.scope_key) == schema["plan"]["source"]
        )
        report["source_journal_unchanged"] = (
            scoped_bindings(
                source_runtime, manifest, parent["ingestion"], args.ingestion_dir
            )[1]["journal_sha256"]
            == certificate["journal_sha256"]
        )
        if not all(
            report[k]
            for k in [
                "corpus_unchanged",
                "vectors_unchanged",
                "graph_unchanged",
                "source_journal_unchanged",
            ]
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
        "cohort-plan",
        "parent-report",
        "backfill",
        "schema",
        "ingestion-dir",
        "reranker-model",
        "run-dir",
        "output",
    ]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--scope-ordinal", type=int, default=1)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("preserve outputs; cache-only requires live")
    report = asyncio.run(run(args))
    save(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "scope_ordinal": args.scope_ordinal,
                "rows": [
                    {
                        "profile": r["profile"],
                        "status": r["status"],
                        "task_grade": r.get("task_grade"),
                    }
                    for r in report["rows"]
                ],
            }
        )
    )
    return 0 if report["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
