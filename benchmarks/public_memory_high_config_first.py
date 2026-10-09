"""One opened LongMemEval history, natural high-config pipeline, not AML scores.

Preflight must be frozen before live calls. Exact-scope read-only Store/index
connections, separate durable stage budgets, no retry and no answer-aware packing.
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

from benchmarks.evidence_rich_blind_diagnostic import local_credentials
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
from benchmarks.public_memory_high_config_preflight import bound_scopes
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_reader_v2 import (
    ReaderV2Output,
    build_request,
    structural_check,
)
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_task_accuracy import Grade
from benchmarks.public_memory_task_accuracy import request as task_request
from doppel_memory.graphiti_store import GraphitiRelationIndex, GraphitiSemanticIndex
from doppel_memory.high_config import HighConfigRetrieval, HighConfigRetrievalResult
from doppel_memory.indexing import memory_index_fingerprint
from doppel_memory.models import ACTIVE_MEMORY_STATES
from doppel_memory.personal_rerank import PersonalMemoryRerankConfig
from doppel_memory.postgres_store import PostgreSQLStore
from doppel_memory.query import PersonalMemoryQueryConfig
from doppel_memory.query_path import ReferencePersonalMemoryRelationPathPlannerV7
from doppel_memory.relation import RelationTypeDefinition
from doppel_memory.relation_path_retrieval import EvidenceRichHybridRetrievalConfig
from doppel_memory.vector import PostgreSQLVectorIndex

RUNNER = "doppel.public-memory-high-config-first.v1"
STAGES = {
    "planner": (2, 4096),
    "reader": (1, 2048),
    "task_judge": (1, 2048),
    "citation_judge": (1, 3072),
}


class ReadOnlyStore(PostgreSQLStore):
    async def _ensure_pool(self):
        if self._pool is None:
            import asyncpg

            self._pool = await asyncpg.create_pool(
                dsn=self._dsn,
                min_size=1,
                max_size=4,
                command_timeout=30,
                server_settings={"default_transaction_read_only": "on"},
            )
            async with self._pool.acquire() as connection:
                await connection.fetch(f"SELECT * FROM {self._records_sql} LIMIT 0")
                await connection.fetch(f"SELECT * FROM {self._meta_sql} LIMIT 0")
        return self._pool


class ReadOnlyVectorIndex(PostgreSQLVectorIndex):
    async def _migrate(self, connection, vector_type_sql, opclass_sql):
        # Existing identity/schema is mandatory. No CREATE/ALTER/INSERT/reindex.
        identity = await connection.fetchval(
            f"SELECT value FROM {self._store._meta_sql} WHERE key=$1",
            f"vector_profile:{self._profile}",
        )
        if str(identity) != self._identity_json:
            raise ValueError("existing vector profile identity mismatch")
        await connection.fetch(
            f"SELECT embedding,record_fingerprint,source_version,scope_key FROM {self._table_sql} LIMIT 0"
        )


async def vector_snapshot(store, index, records, scopes):
    await index.initialize()
    pool = await store._ensure_pool()
    rows = await pool.fetch(
        f"SELECT memory_id,scope_key,record_fingerprint,source_version FROM {index._table_sql} "
        "WHERE scope_key=ANY($1::text[]) ORDER BY memory_id",
        [s.scope_key for s in scopes],
    )
    entries = {r["memory_id"]: dict(r) for r in rows}
    active = {k: r for k, r in records.items() if r.state in ACTIVE_MEMORY_STATES}
    if set(entries) != set(active) or any(
        e["scope_key"] != active[k].scope.scope_key
        or e["record_fingerprint"] != memory_index_fingerprint(active[k])
        or e["source_version"] != active[k].version
        for k, e in entries.items()
    ):
        raise ValueError("complete current vector inventory required")
    return {
        "count": len(entries),
        "metadata_sha256": _hash(entries),
        "profile": index.profile,
    }


def reader_request(row, result):
    request = build_request(row)
    if result.base.count.status != "not_requested":
        # Keep engine-wide aggregation separate from top-k evidence/citable IDs.
        request = request.model_copy(
            update={
                "input": {
                    **request.input,
                    "retrieval_aggregation": result.base.count.model_dump(mode="json"),
                    "retrieval_complete": result.base.complete,
                }
            }
        )
    return request


def build_plan(binding, runtime, scope, schema, corpus, vectors, reranker):
    source_files = [
        Path(__file__),
        Path("benchmarks/public_memory_high_config_context.py"),
        Path("doppel_memory/high_config.py"),
        Path("doppel_memory/query_path.py"),
        Path("doppel_memory/relation.py"),
        Path("doppel_memory/query.py"),
        Path("doppel_memory/graphiti_store.py"),
        Path("doppel_memory/vector.py"),
        Path("doppel_memory/relation_path_retrieval.py"),
        Path("benchmarks/public_context_rerank.py"),
        Path("benchmarks/public_memory_comparison.py"),
        Path("benchmarks/public_memory_answer_comparison.py"),
        Path("benchmarks/public_memory_reader_v2.py"),
        Path("benchmarks/public_memory_task_accuracy.py"),
        Path("benchmarks/public_memory_expansion.py"),
    ]
    plan = {
        "runner": RUNNER,
        "binding": binding,
        "scope_key": scope.scope_key,
        "selection": "first-ingestion-scope-only-no-answer-based-selection",
        "query_sha256": _hash(
            {
                "user_id": runtime.query.user_id,
                "query": runtime.query.query,
                "reference_time": runtime.query.reference_time.isoformat(),
            }
        ),
        "graph_snapshot": schema["plan"]["source"],
        "relation_definitions_sha256": _hash(schema["definitions"]),
        "corpus_sha256": corpus,
        "vectors": vectors,
        "embedding": {
            "name": "fastembed:BAAI/bge-small-zh-v1.5",
            "version": "0.8.0",
            "dimensions": 512,
        },
        "reranker": {
            k: v
            for k, v in reranker.report().items()
            if k
            in {
                "name",
                "version",
                "model_path",
                "device_requested",
                "model_artifact_sha256",
                "max_length",
                "batch_size",
            }
        },
        "query_config": PersonalMemoryQueryConfig(
            limit=100,
            candidate_fusion="union",
            semantic_fallback_to_lexical=False,
            relation_fallback_to_nonrelation=False,
        ).model_dump(mode="json"),
        "rerank_config": PersonalMemoryRerankConfig(
            max_candidates=100, timeout_seconds=120
        ).model_dump(mode="json"),
        "hybrid_config": EvidenceRichHybridRetrievalConfig().model_dump(mode="json"),
        "raw_candidate_limit": 80,
        "raw_output_limit": 20,
        "source_limit": 80,
        "context_policy": "whole-item-memory-raw-backing-round-robin-v1",
        "item_limit": 20,
        "context_byte_limit": 24000,
        "stages": {
            stage: {
                "max_calls": calls,
                "config": config(tokens).model_dump(mode="json"),
                "max_request_bytes": 500_000,
                "max_total_request_bytes": calls * 500_000,
            }
            for stage, (calls, tokens) in STAGES.items()
        },
        "source_sha256": {
            str(p).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in source_files
        },
        "publication_ready": False,
        "aml_academic_model_compliant": False,
    }
    return {**plan, "plan_fingerprint": _hash(plan)}


class RecordedPlannerModel:
    def __init__(self, model, path):
        self.model, self.path, self.requests = model, path, []
        self.name, self.version = model.name, model.version

    async def generate(self, request):
        self.requests.append(request.model_dump(mode="json"))
        save(
            self.path.with_name(f"{self.path.stem}-{len(self.requests)}.json"),
            {"request": request.model_dump(mode="json")},
        )
        return await self.model.generate(request)


async def persisted_generation(model, request, parser, path):
    sha = _hash(request.model_dump(mode="json"))
    saved = None
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved["request_sha256"] != sha:
            raise ValueError("persisted stage request changed")
        if saved["status"] != "completed":
            raise ValueError("preserved failed stage must not be silently retried")
        # Still call cache-only/cache-hit path to validate the content-addressed envelope.
    if saved is None:
        started = path.with_name(path.stem + "-started.json")
        if started.exists():
            raise ValueError("interrupted stage must not be silently retried")
        save(started, {"status": "started", "request_sha256": sha})
    try:
        output = parser.model_validate(await model.generate(request))
    except Exception as error:
        if saved is None:
            save(
                path,
                {
                    "status": "failed",
                    "request_sha256": sha,
                    "failure_type": type(error).__name__,
                },
            )
        raise
    if saved is not None:
        if output.model_dump(mode="json") != saved["output"]:
            raise ValueError("cached stage output changed")
        return output
    save(
        path,
        {
            "status": "completed",
            "request_sha256": sha,
            "output": output.model_dump(mode="json"),
        },
    )
    return output


async def evaluate(args):
    paths = {
        "dataset": args.dataset,
        "manifest": args.manifest,
        "ingestion": args.ingestion,
        "backfill": args.backfill,
        "schema": args.schema,
    }
    contents = {k: p.read_bytes() for k, p in paths.items()}
    binding = {k: hashlib.sha256(v).hexdigest() for k, v in contents.items()}
    manifest, ingestion, backfill, schema = (
        json.loads(contents[k]) for k in ["manifest", "ingestion", "backfill", "schema"]
    )
    cases = select_diagnostic_cases(
        json.loads(contents["dataset"]), manifest, source_sha256=binding["dataset"]
    )
    runtime, scoring = cases[0]
    scopes = bound_scopes(manifest, ingestion)
    scope = scopes[0]
    if (
        backfill["status"] != "complete"
        or schema["status"] != "complete"
        or backfill["plan"]["ingestion_plan_fingerprint"]
        != ingestion["plan"]["plan_fingerprint"]
        or {r["scope_key"] for r in backfill["plan"]["records"]} != {scope.scope_key}
        or schema["plan"]["source"]["scope_key"] != scope.scope_key
    ):
        raise ValueError("first history complete graph/schema binding required")
    definitions = validate_definitions(
        schema["plan"]["source"]["relation_names"],
        {"definitions": schema["definitions"]},
    )
    sources = load_bindings(
        [c[0] for c in cases], manifest, ingestion, args.ingestion_dir
    )
    binding["source_journal"] = hashlib.sha256(
        (args.ingestion_dir / "ingestion.sqlite3").read_bytes()
    ).hexdigest()
    provider = _LocalEmbeddingProvider(cache_dir=args.embedding_cache)
    if {
        "name": provider.name,
        "version": provider.version,
        "dimensions": provider.dimensions,
    } != {k: ingestion["embedding"][k] for k in ["name", "version", "dimensions"]}:
        raise ValueError("local embedding identity changed")
    reranker = LocalContextCrossEncoder(args.reranker_model, device="cuda")
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"),
        schema=ingestion["postgres_schema"],
    )
    from graphiti_core.driver.neo4j_driver import Neo4jDriver

    class ReadOnlyDriver(Neo4jDriver):
        async def build_indices_and_constraints(self):
            return None

    _, password, _ = local_credentials()
    driver = ReadOnlyDriver("bolt://127.0.0.1:7687", "neo4j", password)
    client = SimpleNamespace(driver=driver)
    ledgers, models = {}, {}
    report = {
        "runner": RUNNER,
        "status": "ready",
        "record_or_index_writes": 0,
        "reserved_histories_executed": False,
        "publication_ready": False,
        "judgments_independently_verified": False,
        "full_benchmark_score": None,
    }
    records = vector = vectors = None
    try:
        records = await inventory(store, scopes)
        corpus = _hash({k: r.model_dump(mode="json") for k, r in records.items()})
        if corpus != backfill["plan"]["corpus_sha256"]:
            raise ValueError("source corpus changed since graph completion")
        vector = ReadOnlyVectorIndex(store, provider)
        vectors = await vector_snapshot(store, vector, records, scopes)
        if await snapshot(scope.scope_key) != schema["plan"]["source"]:
            raise ValueError("graph differs from frozen schema source")
        projection = GraphitiSemanticIndex(store, graphiti_client=client)
        checks = [
            await inspect_projection(client, projection, records[t["memory_id"]])
            for t in backfill["plan"]["records"]
        ]
        if any(not c["complete"] for c in checks):
            raise ValueError("complete current first-scope projections required")
        plan = build_plan(binding, runtime, scope, schema, corpus, vectors, reranker)
        report.update(
            plan=plan,
            projection_count=len(checks),
            graph_ready_histories=1,
            total_histories=50,
        )
        if not args.live:
            return report
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_text(encoding="utf-8"))["plan"]
            != plan
        ):
            raise ValueError("unchanged frozen preflight required")
        key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not args.cache_only and not key:
            raise ValueError("API key environment absent")
        args.run_dir.mkdir(parents=True, exist_ok=True)
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
        retrieval_path = args.run_dir / "retrieval.json"
        if retrieval_path.exists():
            saved = json.loads(retrieval_path.read_text(encoding="utf-8"))
            if saved["plan_fingerprint"] != plan["plan_fingerprint"]:
                raise ValueError("retrieval checkpoint identity changed")
            result = HighConfigRetrievalResult.model_validate(saved["result"])
            report["retrieval_execution"] = "immutable-checkpoint-replay"
        else:
            marker = args.run_dir / "retrieval-attempt.json"
            if marker.exists():
                raise ValueError(
                    "preserve failed/interrupted retrieval attempt; no silent retry"
                )
            save(
                marker,
                {"plan_fingerprint": plan["plan_fingerprint"], "status": "started"},
            )
            relations = GraphitiRelationIndex(store, graphiti_client=client)
            host = HighConfigRetrieval(
                store,
                semantic_index=vector,
                relation_index=relations,
                path_index=relations,
                exploration_index=relations,
                planner=ReferencePersonalMemoryRelationPathPlannerV7(
                    RecordedPlannerModel(
                        models["planner"], args.run_dir / "planner-requests.json"
                    )
                ),
                memory_reranker=reranker,
                path_reranker=LocalRelationCrossEncoder(reranker),
                source_resolver=JournalSourceResolver(store, sources),
                relation_definitions=[
                    RelationTypeDefinition.model_validate(d) for d in definitions
                ],
            )
            start = perf_counter()
            result = await host.query(
                runtime.query.query,
                [scope],
                now=runtime.query.reference_time,
                default_subject_id=scope.user_id,
                trace_limit=100,
            )
            report["retrieval_ms"] = (perf_counter() - start) * 1000
            report["retrieval_execution"] = "live-production-high-config"
            save(
                retrieval_path,
                {
                    "plan_fingerprint": plan["plan_fingerprint"],
                    "result": result.model_dump(mode="json"),
                    "reranker": reranker.report(),
                    "retrieval_ms": report["retrieval_ms"],
                },
            )
        checkpoint = json.loads(retrieval_path.read_text(encoding="utf-8"))
        report["reranker"] = checkpoint["reranker"]
        context, packing = prepare_context(result, records, sources)
        row = AnswerRow(
            0,
            scoring.case_id,
            "personal-high-config-v1",
            runtime,
            scoring,
            tuple(context),
        )
        report.update(
            case_id=scoring.case_id,
            question=runtime.query.query,
            retrieval=result.model_dump(mode="json"),
            context=context,
            packing=packing,
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
            for i in context
            for event in i["source_events"]
        ]
        report.update(
            task_grade=grade.model_dump(mode="json"),
            citation_grade=support.model_dump(mode="json"),
            citation_checks=primary_checks(row, support),
            evidence_score=score_evidence(scoring, positions),
            reference_answer=scoring.answer,
            status="complete",
        )
        report["degraded"] = bool(
            result.warnings or not result.base.complete or result.source_failures
        )
        report["full_config_success"] = (
            not report["degraded"] and report["reader_checks"]["structurally_valid"]
        )
    except Exception as error:  # noqa: BLE001 - sanitized credential boundary
        report.update(status="failed", failure_type=type(error).__name__)
    finally:
        report["usage"] = {stage: model.report() for stage, model in models.items()}
        if records is not None:
            after = await inventory(store, scopes)
            report["corpus_unchanged"] = _hash(
                {k: r.model_dump(mode="json") for k, r in after.items()}
            ) == _hash({k: r.model_dump(mode="json") for k, r in records.items()})
            report["graph_unchanged"] = (
                await snapshot(scope.scope_key) == schema["plan"]["source"]
            )
            report["vectors_unchanged"] = (
                await vector_snapshot(store, vector, after, scopes) == vectors
                if vector is not None and vectors is not None
                else None
            )
            if any(
                report[k] is False
                for k in ["corpus_unchanged", "graph_unchanged", "vectors_unchanged"]
            ):
                report["status"] = "failed"
        for ledger in ledgers.values():
            ledger.close()
        await store.close()
        await driver.close()
    return report


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
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("preserve output; cache-only requires live")
    report = asyncio.run(evaluate(args))
    report["execution_metadata"] = execution_metadata()
    save(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "task_grade": report.get("task_grade"),
                "failure_type": report.get("failure_type"),
            }
        )
    )
    return 0 if report["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
