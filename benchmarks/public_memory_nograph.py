"""Bounded non-graph follow-up on fixed source ordinals 6--10.

New experiment, not a degraded high-config score. Reuse production RRF/reranking,
source guards and unchanged Reader/judges; never connect to or modify Neo4j.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_context_rerank import (
    LocalContextCrossEncoder,
    StrictContextReranker,
)
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_comparison import (
    context_item,
    inventory,
    pack_context,
    select_candidates,
)
from benchmarks.public_memory_expansion import local_diagnostic_dsn, save
from benchmarks.public_memory_fresh_cohort import NAMESPACE
from benchmarks.public_memory_fresh_continue import completed_prefix
from benchmarks.public_memory_fresh_graph import scoped_bindings
from benchmarks.public_memory_fresh_ingest import prepare_stage
from benchmarks.public_memory_fresh_query import raw_answer
from benchmarks.public_memory_fresh_replay import call_inventory, semantic_row
from benchmarks.public_memory_high_config_first import (
    ReadOnlyStore,
    ReadOnlyVectorIndex,
    vector_snapshot,
)
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_pilot import _hash
from doppel_memory.lexical import BM25Config, BM25RetrievalStrategy
from doppel_memory.models import MemoryFilter, MemoryState
from doppel_memory.vector import HybridRetrievalStrategy
from integrations.aml.contract import memory_scope

RUNNER = "doppel.public-memory-nograph-followup.v1"
ORDINALS = (6, 7, 8, 9, 10)
PROFILES = ("combined_lexical_vector_reranked", "raw_vector_reranked")


class RecordedBM25(BM25RetrievalStrategy):
    """Instrumentation only; preserve the production lexical algorithm."""

    returned_count = 0

    async def search(self, *args, **kwargs):
        result = await super().search(*args, **kwargs)
        self.returned_count = len(result)
        return result


def make_plan(
    binding, cohort, runtime, ordinal, certificate, corpus, vectors, reranker, profile
):
    if ordinal not in ORDINALS or profile not in PROFILES:
        raise ValueError("fixed ordinals and non-graph profiles required")
    stages = {
        name: {
            "max_calls": 1,
            "config": cohort["stage_configs"][name]["provider"],
            "max_request_bytes": 500_000,
            "max_total_request_bytes": 500_000,
        }
        for name in ("reader", "task_judge", "citation_judge")
    }
    plan = {
        "runner": RUNNER,
        "binding": binding,
        "cohort_plan_fingerprint": cohort["plan_fingerprint"],
        "profile": profile,
        "scope_ordinal": ordinal,
        "source": certificate,
        "corpus_sha256": corpus,
        "vectors": vectors,
        "query_sha256": _hash(
            {
                "question": runtime.query.query,
                "reference_time": runtime.query.reference_time.isoformat(),
            }
        ),
        "profile_execution_order": list(
            PROFILES if ordinal % 2 else reversed(PROFILES)
        ),
        "stages": stages,
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
        "retrieval": {
            "candidate_limit": 80,
            "output_limit": 20,
            "context_byte_limit": 24_000,
            "fusion": "production-RRF" if profile == PROFILES[0] else "vector-only",
            "lexical_weight": 1,
            "semantic_weight": 1,
            "rrf_k": 60,
            "source_pool": "all-current-scoped-records-before-authorized-channel-selection",
            "channels": "owner-memory-and-attributed-raw"
            if profile == PROFILES[0]
            else "attributed-raw",
            "packing": "whole-ranked-prefix-no-truncation",
            "fallback_to_lexical": False,
            "lexical": {
                "name": BM25RetrievalStrategy.name,
                "version": BM25RetrievalStrategy.version,
                "config": BM25Config().model_dump(mode="json"),
                "implementation_sha256": hashlib.sha256(
                    Path("doppel_memory/lexical.py").read_bytes()
                ).hexdigest(),
            },
            "temporal_policy": "retain-source-dates-and-validity-for-reader; no-exact-count-or-as-of-certificate",
        },
        "graph_calls": 0,
        "source_writer_calls": 0,
        "planner_calls": 0,
        "publication_ready": False,
        "implementation_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
    }
    return {**plan, "plan_fingerprint": _hash(plan)}


async def retrieve(runtime, scope, records, sources, vector, reranker, plan):
    if plan["profile"] == PROFILES[1]:
        # raw_answer performs the original, unchanged raw-vector baseline.
        raise ValueError("raw profile must use the existing baseline retrieval")
    lexical = RecordedBM25()
    ordered = await HybridRetrievalStrategy(
        vector,
        lexical_strategy=lexical,
        fallback_to_lexical=False,
        candidate_multiplier=1,
        lexical_weight=1,
        semantic_weight=1,
        rrf_k=60,
    ).search(
        vector._store,
        runtime.query.query,
        [scope],
        filters=MemoryFilter(states={MemoryState.CONFIRMED}),
        limit=len(records),
    )
    items = {
        k: item
        for k, r in records.items()
        if (item := context_item(r, records, sources)) is not None
    }
    candidates = select_candidates(ordered, items, scope, "combined")
    strict = StrictContextReranker(reranker)
    ranking = await strict.rerank(runtime.query.query, candidates, limit=20)
    return {
        "plan_fingerprint": plan["plan_fingerprint"],
        "context": pack_context([items[c.memory_id] for c in ranking]),
        "candidate_count": len(candidates),
        "rerank_summary": strict.last_summary.model_dump(mode="json")
        if strict.last_summary
        else None,
        "reranker": reranker.report(),
        "strategy": "production-HybridRetrievalStrategy-RRF-60-1:1-no-fallback",
        "lexical_candidates_returned": lexical.returned_count,
        "fused_candidates_returned": len(ordered),
    }


def preserve_row(path, row, *, cache_only):
    if cache_only:
        old = json.loads(path.read_bytes())
        if old["status"] != "complete" or semantic_row(old) != semantic_row(row):
            raise ValueError("immutable non-graph row differs from replay")
    else:
        save(path, row)


async def evaluate(args):
    paths = {
        k: getattr(args, k)
        for k in ("dataset", "manifest", "cohort_plan", "parent_report")
    }
    content = {k: p.read_bytes() for k, p in paths.items()}
    raw, manifest, cohort, parent = (json.loads(content[k]) for k in paths)
    cases, target = prepare_stage(
        raw,
        manifest,
        cohort,
        source_sha=hashlib.sha256(content["dataset"]).hexdigest(),
        histories=10,
    )
    if (
        completed_prefix(parent["ingestion"], cohort["ingestion_plan"])
        < target["max_new_chunks"]
    ):
        raise ValueError("complete first-ten source prefix required; graph irrelevant")
    binding = {k: hashlib.sha256(v).hexdigest() for k, v in content.items()}
    reranker = LocalContextCrossEncoder(args.reranker_model, device="cuda")
    identity = reranker.report()
    expected = cohort["reranker"]
    if identity["name"] != "local-cross-encoder:" + expected["model"] or any(
        identity[k] != expected[v]
        for k, v in (
            ("device_requested", "device"),
            ("max_length", "max_length"),
            ("batch_size", "batch_size"),
        )
    ):
        raise ValueError("unchanged frozen reranker required")
    embedder = _LocalEmbeddingProvider(cache_dir=None)
    if {
        "name": embedder.name,
        "version": embedder.version,
        "dimensions": embedder.dimensions,
    } != parent["ingestion"]["embedding"]:
        raise ValueError("embedding identity changed")
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"),
        schema=parent["ingestion"]["postgres_schema"],
    )
    vector = ReadOnlyVectorIndex(store, embedder)
    staged, plans = [], {}
    try:
        by_id = {r["question_id"]: r for r in raw}
        selected = [c for c in manifest["cases"] if c["partition"] == "diagnostic"]
        for ordinal in ORDINALS:
            runtime = cases[ordinal - 1]
            scope = memory_scope(manifest["run_namespace"], runtime.user_id)
            sources, cert = scoped_bindings(
                runtime, manifest, parent["ingestion"], args.ingestion_dir
            )
            records = await inventory(store, [scope])
            for record in records.values():
                context_item(record, records, sources)
            corpus = _hash({k: r.model_dump(mode="json") for k, r in records.items()})
            vectors = await vector_snapshot(store, vector, records, [scope])
            # Source-only readiness suffices. No graph, schema, question-based
            # authoring or use of partially built graph 06 is permitted.
            prepared = prepare_case(
                by_id[selected[ordinal - 1]["case_id"]], dataset_namespace=NAMESPACE
            )
            if (
                prepared.runtime.sessions != runtime.sessions
                or prepared.runtime.user_id != runtime.user_id
            ):
                raise ValueError("query runtime changed original source")
            plans[str(ordinal)] = {
                p: make_plan(
                    binding,
                    cohort,
                    prepared.runtime,
                    ordinal,
                    cert,
                    corpus,
                    vectors,
                    reranker,
                    p,
                )
                for p in PROFILES
            }
            staged.append(
                (ordinal, prepared, scope, records, sources, cert, corpus, vectors)
            )
        report = {
            "runner": RUNNER,
            "plans": plans,
            "status": "ready",
            "rows": [],
            "max_new_calls": 30,
            "graph_connections": 0,
            "graph_calls": 0,
            "source_writes": 0,
            "planner_calls": 0,
            "publication_ready": False,
            "official_longmemeval_score": False,
            "aml_score": False,
            "judgments_independently_verified": False,
        }
        if args.live:
            if (
                not args.frozen_preflight
                or json.loads(args.frozen_preflight.read_bytes())["plans"] != plans
            ):
                raise ValueError("unchanged separately frozen non-graph plans required")
            # Refuse a silent second live invocation even if caches could absorb it.
            if not args.cache_only and any(args.run_dir.rglob("receipt.json")):
                raise ValueError(
                    "preserve attempted batch; only explicit cache replay allowed"
                )
            before_calls = call_inventory(args.run_dir) if args.cache_only else None
            failed = False
            for (
                ordinal,
                prepared,
                scope,
                records,
                sources,
                cert,
                corpus,
                vectors,
            ) in staged:
                order = plans[str(ordinal)][PROFILES[0]]["profile_execution_order"]
                for profile in order:
                    plan = plans[str(ordinal)][profile]
                    child = SimpleNamespace(
                        run_dir=args.run_dir / f"scope{ordinal:02}" / profile,
                        cache_only=args.cache_only,
                    )
                    receipt = child.run_dir / "receipt.json"
                    checkpoint = child.run_dir / "retrieval.json"
                    if profile == PROFILES[0] and not checkpoint.exists():
                        if args.cache_only:
                            raise ValueError("no retrieval in cache-only replay")
                        _bind_json(child.run_dir / "plan.json", plan)
                        save(
                            child.run_dir / "retrieval-attempt.json",
                            {
                                "status": "started",
                                "plan_fingerprint": plan["plan_fingerprint"],
                            },
                        )
                        save(
                            checkpoint,
                            await retrieve(
                                prepared.runtime,
                                scope,
                                records,
                                sources,
                                vector,
                                reranker,
                                plan,
                            ),
                        )
                    # Existing helper's internal AnswerRow profile is not included
                    # in Reader/judge requests. Only source evidence reaches them.
                    row = await raw_answer(
                        child,
                        (prepared.runtime, prepared.scoring),
                        scope,
                        records,
                        sources,
                        vector,
                        reranker,
                        plan,
                    )
                    row.update(profile=profile, scope_ordinal=ordinal)
                    preserve_row(receipt, row, cache_only=args.cache_only)
                    report["rows"].append(row)
                    print(f"scope {ordinal:02} {profile}: {row['status']}", flush=True)
                    if row["status"] != "complete":
                        failed = True
                        break
                if failed:
                    break
            report["status"] = "partial" if failed else "complete"
            if args.cache_only and call_inventory(args.run_dir) != before_calls:
                raise ValueError("replay changed durable provider calls")
            report["cache_only_replay"] = args.cache_only
        integrity = []
        for ordinal, prepared, scope, records, sources, cert, corpus, vectors in staged:
            after = await inventory(store, [scope])
            okay = (
                _hash({k: r.model_dump(mode="json") for k, r in after.items()})
                == corpus
                and await vector_snapshot(store, vector, after, [scope]) == vectors
                and scoped_bindings(
                    prepared.runtime, manifest, parent["ingestion"], args.ingestion_dir
                )[1]
                == cert
            )
            integrity.append(
                {"ordinal": ordinal, "source_store_vectors_unchanged": okay}
            )
        report["integrity"] = integrity
        if not all(r["source_store_vectors_unchanged"] for r in integrity):
            report["status"] = "integrity_failed"
        report["execution_metadata"] = execution_metadata()
        return report
    finally:
        await store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "dataset",
        "manifest",
        "cohort-plan",
        "parent-report",
        "ingestion-dir",
        "reranker-model",
        "run-dir",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or args.cache_only and not args.live:
        parser.error("preserve outputs; cache-only requires live")
    result = asyncio.run(evaluate(args))
    save(args.output, result)
    print(
        json.dumps(
            {"status": result["status"], "rows": len(result["rows"]), "max_calls": 30}
        )
    )
    return 0 if result["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
