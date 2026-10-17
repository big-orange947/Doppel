"""Fixed next-ten public histories: three non-graph retrieval arms, two packers."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_context_baseline import (
    RawHistoryHost,
    _VectorStrategy,
    execution_metadata,
    score_evidence,
)
from benchmarks.public_context_rerank import (
    LocalContextCrossEncoder,
    StrictContextReranker,
)
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_comparison import SourceBinding, context_item
from benchmarks.public_memory_expansion import local_diagnostic_dsn, save
from benchmarks.public_memory_fresh_cohort import validate_fingerprint
from benchmarks.public_memory_packing_fit import compare_row
from benchmarks.public_memory_pilot import _hash, history_group
from benchmarks.public_memory_retrieval_packing import audit_row, summarize
from doppel_memory.lexical import BM25RetrievalStrategy
from doppel_memory.postgres_store import PostgreSQLStore
from doppel_memory.vector import (
    HybridRetrievalStrategy,
    PostgreSQLVectorIndex,
    VectorIndexConfig,
)
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.contract import event_ids, memory_scope

RUNNER = "doppel.raw-next-ten-retrieval-packing.v1"
NAMESPACE = "longmemeval-nograph-retrieval-31-40-v1"
PROFILES = ("raw_local_vector_reranked", "raw_bm25_vector", "raw_bm25_vector_reranked")


def prepare(raw, parent, source_sha):
    validate_fingerprint(parent, "manifest_fingerprint")
    selected = [c for c in parent["cases"] if c["partition"] == "diagnostic"]
    by_id = {r["question_id"]: r for r in raw}
    if (
        source_sha != parent["source_sha256"]
        or len(selected) < 40
        or len(by_id) != len(raw)
    ):
        raise ValueError(
            "unchanged source and at least forty frozen diagnostic histories required"
        )
    forbidden = {
        c["history_group"] for c in parent["cases"] if c["partition"] != "diagnostic"
    } | {c["history_group"] for c in selected[:30]}
    cases, rows = [], []
    for ordinal, row in enumerate(selected[30:40], 31):
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
                "frozen history binding differs or overlaps opened/reserved group"
            )
        forbidden.add(row["history_group"])
        cases.append((case.runtime, case.scoring))
        rows.append(
            {
                "ordinal": ordinal,
                "case_id": row["case_id"],
                "history_group": row["history_group"],
                "raw_turn_count": row["raw_turn_count"],
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


def make_plan(manifest, reranker):
    value = {
        "runner": RUNNER,
        "manifest": manifest,
        "schema": "raw_next_" + manifest["manifest_fingerprint"][:12],
        "profiles": list(PROFILES),
        "candidate_window": 80,
        "output_limit": 20,
        "context_byte_limit": 24000,
        "policies": ["prefix", "ranked_fit"],
        "reranker": {
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
        },
        "embedding": "fastembed:BAAI/bge-small-zh-v1.5/0.8.0/512",
        "runtime_source_sha256": execution_metadata()["runtime_source_sha256"],
        "source_sha256": {
            name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for name, path in {
                "wrapper": __file__,
                "packing": "benchmarks/public_memory_comparison.py",
                "prefix_audit": "benchmarks/public_memory_retrieval_packing.py",
                "fit_audit": "benchmarks/public_memory_packing_fit.py",
            }.items()
        },
        "bm25": BM25RetrievalStrategy().config.model_dump(mode="json"),
        "fusion": "production-RRF-k60-equal-weights-no-fallback",
        "llm_calls": 0,
        "provider_tokens": 0,
        "graph_calls": 0,
        "negative_policy": "exclude-predeclared-abstention-from-answer-support; retain-negative-rows",
        "failure_policy": "stop; keep per-history receipts and dedicated raw data; no reset/automatic retry",
        "publication_ready": False,
    }
    return {**value, "plan_fingerprint": _hash(value)}


def bound_items(runtime, manifest, scope, host, records):
    sources = {}
    for chunk in runtime.ingestion_chunks(max_messages=manifest["max_messages"]):
        for index, (message, event, turn) in enumerate(
            zip(
                chunk.request.messages,
                event_ids(scope, chunk.request),
                chunk.source_turn_indices,
                strict=True,
            )
        ):
            if message.timestamp is None:
                raise ValueError("source timestamp missing")
            sources[(scope.scope_key, event)] = SourceBinding(
                host.sources[(scope.scope_key, event)],
                (chunk.source_session_index, turn),
                message.role,
                message.content,
                message.timestamp,
                chunk.request.session_id,
                index,
            )
    return {
        s.position: context_item(records[s.memory_id], records, sources)
        for s in sources.values()
    }


async def execute(args, cases, manifest, plan, reranker):
    if (
        not args.frozen_preflight
        or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
    ):
        raise ValueError("matching frozen preflight required")
    if any(args.run_dir.glob("*.json")):
        raise ValueError("preserve old attempts; no silent second invocation")
    for key in ("DEEPSEEK_API_KEY", "DOPPEL_API_KEY", "OPENAI_API_KEY"):
        os.environ.pop(key, None)
    save(
        args.run_dir / "attempt.json",
        {"plan_fingerprint": plan["plan_fingerprint"], "status": "started"},
    )
    store = PostgreSQLStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"),
        schema=plan["schema"],
        create_schema=True,
    )
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
    host, rows, receipts = RawHistoryHost(store), [], []
    strict = StrictContextReranker(reranker)
    try:
        for ordinal, (runtime, scoring) in enumerate(cases, 31):
            scope = memory_scope(manifest["run_namespace"], runtime.user_id)
            records_list = await host.ingest(
                runtime, scope, max_messages=manifest["max_messages"]
            )
            indexed = await index.index_records(records_list)
            if not indexed.ok or indexed.indexed + indexed.skipped != len(records_list):
                raise ValueError("vector indexing incomplete")
            records = {r.memory_id: r for r in records_list}
            items = bound_items(runtime, manifest, scope, host, records)
            if len(items) != len(records) or any(v is None for v in items.values()):
                raise ValueError("raw source inventory mismatch")
            hybrid = HybridRetrievalStrategy(
                index,
                lexical_strategy=BM25RetrievalStrategy(),
                candidate_multiplier=1,
                fallback_to_lexical=False,
            )
            case_rows = []
            for profile in PROFILES:
                result = await AttributedContextRetriever(
                    store,
                    strategy=_VectorStrategy(index)
                    if profile == PROFILES[0]
                    else hybrid,
                    resolve_event=host.resolve_event,
                    reranker=strict if profile.endswith("_reranked") else None,
                ).search(scope, runtime.query.query, limit=20)
                positions = host.retrieved_positions(result.snippets)
                candidates = [
                    host.positions[(scope.scope_key, e)]
                    for e in result.candidate_evidence_ids
                ]
                row = {
                    "case_id": scoring.case_id,
                    "profile": profile,
                    "hits": len(positions),
                    "retrieved_source_positions": [list(p) for p in positions],
                    "candidate_window_score": score_evidence(scoring, candidates),
                    "at_5": score_evidence(scoring, positions[:5]),
                    "at_20": score_evidence(scoring, positions),
                    "revalidated": result.revalidated,
                    "rejected": result.rejected,
                    "final_store_checks": result.final_store_checks,
                    "rerank_summary": strict.last_summary.model_dump(mode="json")
                    if profile.endswith("_reranked") and strict.last_summary
                    else None,
                }
                baseline = audit_row(row, scoring, items)
                row["packing"] = compare_row(row, scoring, items, baseline)
                for p in positions:
                    record = records[items[p]["memory_id"]]
                    if await store.get(scope, record.memory_id) != record:
                        raise ValueError("source changed after packing")
                case_rows.append(row)
            receipt = {
                "ordinal": ordinal,
                "case_id": scoring.case_id,
                "raw_records": len(records),
                "rows": case_rows,
                "corpus_sha256": _hash(
                    {k: r.model_dump(mode="json") for k, r in records.items()}
                ),
                "plan_fingerprint": plan["plan_fingerprint"],
            }
            save(args.run_dir / f"history-{ordinal}.json", receipt)
            receipts.append(receipt)
            rows.extend(case_rows)
            print(
                f"completed {ordinal - 30}/10 histories; three profiles/two packers",
                flush=True,
            )
    finally:
        await store.close()
    return {
        "status": "complete",
        "rows": rows,
        "receipts": receipts,
        "raw_records": sum(r["raw_records"] for r in receipts),
        "reranker": reranker.report(),
        "summary": {
            policy: summarize([r["packing"][policy] for r in rows])
            for policy in ("prefix", "ranked_fit")
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "parent-manifest", "reranker-model", "run-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve previous output")
    data = args.dataset.read_bytes()
    cases, manifest = prepare(
        json.loads(data),
        json.loads(args.parent_manifest.read_bytes()),
        hashlib.sha256(data).hexdigest(),
    )
    reranker = LocalContextCrossEncoder(
        args.reranker_model, device="cuda", max_length=8192, batch_size=1
    )
    plan = make_plan(manifest, reranker)
    report = {
        "runner": RUNNER,
        "status": "ready",
        "plan": plan,
        "llm_calls": 0,
        "provider_tokens": 0,
        "graph_calls": 0,
        "qa_metrics_available": False,
    }
    if args.execute:
        report.update(asyncio.run(execute(args, cases, manifest, plan, reranker)))
    save(args.output, report)
    print(
        json.dumps({"status": report["status"], "summary": report.get("summary", {})})
    )


if __name__ == "__main__":
    main()
