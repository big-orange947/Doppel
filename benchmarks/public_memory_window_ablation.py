"""Fresh80 vs160 raw RRF candidates, same top20/24KB, opened50 only.

Read-only sources/indices; local pointwise BGE scores reused across arm overlap.
No LLM, source repair, graph, label-dependent selection or historical QA rescore.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_context_rerank import LocalContextCrossEncoder
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_comparison import encoded, inventory, pack_ranked_fit
from benchmarks.public_memory_expansion import local_diagnostic_dsn, save
from benchmarks.public_memory_fresh_cohort import validate_fingerprint
from benchmarks.public_memory_high_config_first import (
    ReadOnlyStore,
    ReadOnlyVectorIndex,
)
from benchmarks.public_memory_packing_replay import FILES, stage_totals
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_prospective_selection import model_identity
from benchmarks.public_memory_source_aware_diagnostic import SavedCandidates
from benchmarks.public_memory_uniform_completion import RawOnlyStore, bound_source
from benchmarks.public_memory_uniform_qa import digest
from doppel_memory.indexing import memory_index_fingerprint
from doppel_memory.lexical import BM25RetrievalStrategy
from doppel_memory.personal_rerank import (
    PersonalMemoryRerankConfig,
    PersonalMemoryRerankItem,
    PersonalMemoryRerankRequest,
    score_personal_memories,
)
from doppel_memory.vector import HybridRetrievalStrategy
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.neighborhood import as_candidate

WIDTHS = (80, 160)
SOURCES = (
    __file__,
    "benchmarks/public_context_rerank.py",
    "benchmarks/public_memory_comparison.py",
    "benchmarks/public_memory_uniform_completion.py",
    "doppel_memory/vector.py",
    "doppel_memory/lexical.py",
    "doppel_memory/personal_rerank.py",
    "integrations/aml/context.py",
)


class CachedEmbedding:
    def __init__(self, base):
        self.base = base
        self.name, self.version, self.dimensions = (
            base.name,
            base.version,
            base.dimensions,
        )
        self.cache = {}
        self.calls = self.hits = 0

    async def embed(self, texts):
        key = tuple(texts)
        if key in self.cache:
            self.hits += 1
        else:
            self.cache[key] = [list(v) for v in await self.base.embed(texts)]
            self.calls += 1
        return [list(v) for v in self.cache[key]]


def union_candidates(pools):
    result, seen = [], {}
    for pool in pools:
        for candidate in pool:
            key = candidate.memory_id
            identity = (candidate.scope.scope_key, candidate.raw_text or candidate.fact)
            if key in seen and seen[key] != identity:
                raise ValueError("conflicting candidate snapshots")
            if key not in seen:
                seen[key] = identity
                result.append(candidate)
    return result


class PointwiseOrder:
    def __init__(self, query, candidates, scores):
        self.query = query
        self.values = {
            c.memory_id: (
                c.scope.scope_key,
                c.raw_text or c.fact,
                scores[f"candidate-{i}"],
            )
            for i, c in enumerate(candidates)
        }

    async def rerank(self, query, candidates, *, limit):
        if query != self.query:
            raise ValueError("scored query changed")
        for c in candidates:
            value = self.values[c.memory_id]
            if (
                c.scope is None
                or (c.scope.scope_key, c.raw_text or c.fact) != value[:2]
            ):
                raise ValueError("scored source changed")
        # Ties use each arm's own input order, not the union order.
        order = sorted(
            range(len(candidates)),
            key=lambda i: (-self.values[candidates[i].memory_id][2], i),
        )
        return [candidates[i].model_copy(deep=True) for i in order[:limit]]


async def vector_receipt(store, index, scope, records):
    await index.initialize()
    pool = await store._ensure_pool()
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            f"SELECT memory_id,scope_key,record_fingerprint,source_version FROM {index._table_sql} WHERE scope_key=$1 AND memory_id=ANY($2::text[])",
            scope.scope_key,
            list(records),
        )
    entries = {r["memory_id"]: dict(r) for r in rows}
    if set(entries) != set(records) or any(
        entry["scope_key"] != scope.scope_key
        or entry["source_version"] != records[key].version
        or entry["record_fingerprint"] != memory_index_fingerprint(records[key])
        for key, entry in entries.items()
    ):
        raise ValueError("raw vector catalog is missing or stale")
    return {"count": len(entries), "sha256": _hash(entries), "profile": index.profile}


def load(args, provider):
    raw = {key: path.read_bytes() for key, path in FILES.items()}
    data = {key: json.loads(value) for key, value in raw.items()}
    binding = {key: hashlib.sha256(value).hexdigest() for key, value in raw.items()}
    parent = data["manifest"]
    validate_fingerprint(parent, "manifest_fingerprint")
    if binding["dataset"] != parent["source_sha256"]:
        raise ValueError("frozen dataset changed")
    groups, rows = {}, []
    for key in ("thirty", "twenty"):
        validate_fingerprint(data[key]["plan"], "plan_fingerprint")
        if data[key]["status"] != "complete":
            raise ValueError("completed preparation required")
        groups.update(data[key]["plan"]["groups"])
        rows.extend(data[key]["rows"])
    if len(rows) != 50 or {r["ordinal"] for r in rows} != set(range(1, 51)):
        raise ValueError("all50 opened cases required")
    expected_model = data["twenty"]["plan"]["reranker"]
    if model_identity(provider) != expected_model:
        raise ValueError("same frozen local BGE weights/runtime required")
    selected = {
        m["case_id"]: m for m in parent["cases"] if m["partition"] == "diagnostic"
    }
    if len(selected) != 50 or {r["case_id"] for r in rows} != set(selected):
        raise ValueError("cohort differs from diagnostic partition")
    source = {r["question_id"]: r for r in data["dataset"]}
    scores = {r["ordinal"]: r for r in data["summary"]["rows"]}
    queue = []
    for row in sorted(rows, key=lambda r: r["ordinal"]):
        if (
            hashlib.sha256(encoded(row["context"])).hexdigest()
            != scores[row["ordinal"]]["context_sha256"]
            or row["case_id"] != scores[row["ordinal"]]["case_id"]
        ):
            raise ValueError("frozen context binding differs")
        meta = selected[row["case_id"]]
        case = prepare_case(
            source[row["case_id"]], dataset_namespace=parent["dataset_namespace"]
        )
        chunks = case.runtime.ingestion_chunks(max_messages=parent["max_messages"])
        if (
            _hash([c.request.model_dump(mode="json") for c in chunks])
            != meta["history_payload_sha256"]
        ):
            raise ValueError("opened history payload changed")
        queue.append(({**row, "raw_records": meta["raw_turn_count"]}, case))
    plan = {
        "runner": "doppel.window-ablation.v1",
        "binding": binding,
        "code_sha256": {
            str(Path(p)): hashlib.sha256(Path(p).read_bytes()).hexdigest()
            for p in SOURCES
        },
        "implementation_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "ordinals": list(range(1, 51)),
        "widths": list(WIDTHS),
        "output_items": 20,
        "context_bytes": 24000,
        "fusion": "production-BM25-vector-RRF60-equal-weights-no-fallback-independently-retrieved-widths",
        "embedding": "fastembed:BAAI/bge-small-zh-v1.5/0.8.0/512/symmetric",
        "embedding_cache": str(args.embedding_cache_dir.resolve()),
        "reranker": expected_model,
        "score_reuse": "pointwise-union-once-per-source/query;per-arm-input-order-ties",
        "max_pairs": 12000,
        "max_query_embeddings": 50,
        "scoring_limits": {
            "max_candidates": 240,
            "max_input_chars": 2000000,
            "timeout_seconds": 300,
        },
        "policy": "fresh controlled80/160; historical37/50 not rescored; no source repair or automatic retry",
        "paid_calls": 0,
        "graph_calls": 0,
        "source_writes": 0,
        "publication_ready": False,
        "opened_development_not_blind": True,
    }
    return {**plan, "plan_fingerprint": _hash(plan)}, queue, groups, rows


def summarize(rows):
    result = {}
    for width in WIDTHS:
        positives = [r["arms"][str(width)] for r in rows if not r["abstention_label"]]
        result[str(width)] = {
            "positive_questions": len(positives),
            "annotated": sum(r["annotated"] for r in positives),
            **{
                stage: sum(len(r[stage + "_annotated_ids"]) for r in positives)
                for stage in ("candidate", "top20", "packed")
            },
            "complete_positive_questions": sum(
                len(r["packed_annotated_ids"]) == r["annotated"] for r in positives
            ),
            "items": sum(r["arms"][str(width)]["packed_items"] for r in rows),
        }
    result["paired"] = {}
    for stage in ("candidate", "top20", "packed"):
        pairs = [
            (
                set(r["arms"]["80"][stage + "_annotated_ids"]),
                set(r["arms"]["160"][stage + "_annotated_ids"]),
            )
            for r in rows
            if not r["abstention_label"]
        ]
        result["paired"][stage] = {
            "recovered_turns": sum(len(b - a) for a, b in pairs),
            "displaced_turns": sum(len(a - b) for a, b in pairs),
            "gain_questions": sum(len(b) > len(a) for a, b in pairs),
            "loss_questions": sum(len(b) < len(a) for a, b in pairs),
        }
    result["fresh80_historical_context_matches"] = sum(
        r["historical_context_match"] for r in rows
    )
    return result


async def execute(args, plan, queue, groups, frozen, provider):
    if json.loads(args.frozen_plan.read_bytes()) != plan or args.run_dir.exists():
        raise ValueError("matching frozen plan and new run directory required")
    save(args.run_dir / "attempt.json", {"plan": plan})
    stores, raw_stores, indices, rows = {}, {}, {}, []
    embedding = CachedEmbedding(
        _LocalEmbeddingProvider(cache_dir=args.embedding_cache_dir)
    )
    if (embedding.name, embedding.version, embedding.dimensions) != (
        "fastembed:BAAI/bge-small-zh-v1.5",
        "0.8.0",
        512,
    ):
        raise ValueError("embedding identity differs")
    current, stage = None, "initialization"
    failure = None
    try:
        for key, group in groups.items():
            dsn = local_diagnostic_dsn("doppel-ablation-pgvector")
            stores[key] = ReadOnlyStore(dsn, schema=group["schema"])
            raw_stores[key] = RawOnlyStore(dsn, schema=group["schema"])
            indices[key] = ReadOnlyVectorIndex(raw_stores[key], embedding)
        for meta, case in queue:
            started = time.monotonic()
            current, stage = meta["ordinal"], "source-binding"
            store, raw_store, index = (
                stores[meta["group"]],
                raw_stores[meta["group"]],
                indices[meta["group"]],
            )
            scope, host, items = await bound_source(
                store, meta, case.runtime, groups[meta["group"]]
            )
            records = await inventory(store, [scope])
            raw = {key: r for key, r in records.items() if r.extractor == "ingestor"}
            before = await vector_receipt(raw_store, index, scope, raw)
            hybrid = HybridRetrievalStrategy(
                index,
                lexical_strategy=BM25RetrievalStrategy(),
                candidate_multiplier=1,
                fallback_to_lexical=False,
            )
            pools = {}
            stage = "independent-candidate-retrieval"
            for width in WIDTHS:
                anchors = await AttributedContextRetriever(
                    raw_store,
                    strategy=hybrid,
                    resolve_event=host.resolve_event,
                    candidate_multiplier=1,
                ).search(scope, case.runtime.query.query, limit=width)
                if anchors.rejected or len(anchors.snippets) != min(width, len(raw)):
                    raise ValueError("complete revalidated candidate window required")
                pools[width] = [as_candidate(scope, item) for item in anchors.snippets]
            union = union_candidates(pools.values())
            stage = "pointwise-local-scores"
            request = PersonalMemoryRerankRequest(
                question=case.runtime.query.query,
                items=[
                    PersonalMemoryRerankItem(
                        item_id=f"candidate-{i}", content=c.raw_text or c.fact
                    )
                    for i, c in enumerate(union)
                ],
            )
            values, summary = await score_personal_memories(
                provider,
                request,
                PersonalMemoryRerankConfig(**plan["scoring_limits"]),
                total_candidates=len(union),
            )
            if summary.status != "completed":
                raise ValueError("local scoring did not complete")
            order = PointwiseOrder(case.runtime.query.query, union, values)
            position = {item["memory_id"]: p for p, item in items.items()}
            arms = {}
            for width in WIDTHS:
                stage = f"final-store-check-{width}"
                selected = await AttributedContextRetriever(
                    store,
                    strategy=SavedCandidates(pools[width]),
                    resolve_event=host.resolve_event,
                    reranker=order,
                    candidate_limit=len(pools[width]),
                ).search(scope, case.runtime.query.query, limit=20)
                if (
                    selected.rejected
                    or selected.revalidated != len(pools[width])
                    or selected.final_store_checks != 20
                ):
                    raise ValueError("final source revalidation failed")
                ranked = [items[position[s.memory_id]] for s in selected.snippets]
                context, trace = pack_ranked_fit(ranked)
                # Annotations are read only AFTER candidate/order/packing decisions.
                required = (
                    set()
                    if case.scoring.abstention
                    else {items[p]["memory_id"] for p in case.scoring.evidence_turns}
                )
                ids = {
                    "candidate": [c.memory_id for c in pools[width]],
                    "top20": [i["memory_id"] for i in ranked],
                    "packed": [i["memory_id"] for i in context],
                }
                arms[str(width)] = {
                    "candidate_ids": ids["candidate"],
                    "top20": ranked,
                    "context": context,
                    "annotated": len(required),
                    **{
                        k + "_annotated_ids": sorted(required & set(v))
                        for k, v in ids.items()
                    },
                    "packed_items": len(context),
                    "context_bytes": len(encoded(context)),
                    "packing_trace": trace,
                    "context_sha256": hashlib.sha256(encoded(context)).hexdigest(),
                }
            stage = "after-snapshot"
            if (
                digest(await inventory(store, [scope])) != meta["corpus_sha256"]
                or await vector_receipt(raw_store, index, scope, raw) != before
            ):
                raise ValueError("source/vector metadata changed")
            first, second = (
                {c.memory_id for c in pools[80]},
                {c.memory_id for c in pools[160]},
            )
            row = {
                "ordinal": current,
                "case_id": case.scoring.case_id,
                "abstention_label": case.scoring.abstention,
                "query_sha256": _hash(case.runtime.query.query),
                "arms": arms,
                "vector_snapshot": before,
                "candidate_overlap": len(first & second),
                "candidate80_displaced": sorted(first - second),
                "union_pairs": len(union),
                "local_seconds": round(time.monotonic() - started, 3),
                "historical_context_match": arms["80"]["context"] == meta["context"],
            }
            save(args.run_dir / f"case-{current:02d}.json", row)
            rows.append(row)
            print(
                f"completed {len(rows)}/50 ordinal={current} union_pairs={len(union)} local_seconds={row['local_seconds']}",
                flush=True,
            )
    except Exception as exc:  # noqa: BLE001 - redact provider/credential details
        failure = {"ordinal": current, "stage": stage, "error_type": type(exc).__name__}
    finally:
        for store in [*stores.values(), *raw_stores.values()]:
            await store.close()
    report = {
        "runner": plan["runner"],
        "plan": plan,
        "status": "complete" if len(rows) == 50 and failure is None else "failed",
        "rows": rows,
        "failure": failure,
        "summary": summarize(rows),
        "frozen_fifty_stages": stage_totals(frozen),
        "local_model": provider.report(),
        "query_embedding_calls": embedding.calls,
        "query_embedding_cache_hits": embedding.hits,
        "paid_calls": 0,
        "qa_metrics_available": False,
        "publication_ready": False,
        "official_longmemeval_score": False,
        "aml_score": False,
    }
    save(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "failure": failure,
                "summary": report["summary"],
            },
            sort_keys=True,
        )
    )
    return report["status"] == "complete"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-local", action="store_true")
    parser.add_argument("--frozen-plan", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--embedding-cache-dir", type=Path, required=True)
    parser.add_argument("--reranker-model-path", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or (args.live_local and not args.frozen_plan):
        parser.error("new output and frozen plan required")
    for key in list(os.environ):
        if "API_KEY" in key.upper():
            os.environ.pop(key)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    provider = LocalContextCrossEncoder(
        args.reranker_model_path, device="cuda", max_length=8192, batch_size=1
    )
    plan, queue, groups, frozen = load(args, provider)
    if not args.live_local:
        save(args.output, plan)
        print("preflight: all50 source payloads bound; no DB/model inference")
    elif not asyncio.run(execute(args, plan, queue, groups, frozen, provider)):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
