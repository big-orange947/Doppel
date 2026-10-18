"""Fixed opened-three listwise comparison, read-only sources and <=12 paid calls."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_context_baseline import RawHistoryHost
from benchmarks.public_memory_answer_comparison import (
    AnswerRow,
    _default_provider_factory,
    _request_sha256,
    _StageExecutor,
)
from benchmarks.public_memory_comparison import encoded, inventory, pack_ranked_fit
from benchmarks.public_memory_expansion import config, local_diagnostic_dsn, save
from benchmarks.public_memory_fresh_cohort import validate_fingerprint
from benchmarks.public_memory_high_config_first import (
    ReadOnlyStore,
    ReadOnlyVectorIndex,
)
from benchmarks.public_memory_passage_diagnostic import (
    CASES,
    SavedOrder,
    passage_item,
    reader_request,
)
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_raw_continuation import bound_items, prepare
from benchmarks.public_memory_reader_v2 import ReaderV2Output, structural_check
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_source_aware_diagnostic import (
    SavedCandidates,
    reused_baseline,
)
from benchmarks.public_memory_task_accuracy import Grade
from benchmarks.public_memory_task_accuracy import request as task_request
from doppel_memory.lexical import BM25RetrievalStrategy
from doppel_memory.models import MemoryFilter, MemoryState, RecallResult
from doppel_memory.personal_rerank import (
    PersonalMemoryRerankItem,
    PersonalMemoryRerankRequest,
)
from doppel_memory.reference_rerank import ReferencePersonalMemoryReranker
from doppel_memory.source_aware_rerank import SourceAwareReranker, source_content
from doppel_memory.vector import HybridRetrievalStrategy
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.contract import memory_scope
from integrations.aml.passages import AttributedPassageRetriever

ROOT = Path("data/doppel")
FILES = {
    "dataset": Path("data/public-benchmarks/longmemeval_s_cleaned.json"),
    "manifest": ROOT / "longmemeval-fresh-high-config-50-manifest-v1.json",
    "parent": ROOT / "longmemeval-raw-31-40-live-v1.json",
    "old_contexts": ROOT / "passage-diagnostic-context-live-v1.json",
    "old_qa": ROOT / "passage-diagnostic-qa-live-v1.json",
    "pool_parent": ROOT / "source-aware-context-live-v1.json",
}
RUNNER = "doppel.listwise-opened-three.v1"
PROFILE = "metadata_listwise_no_mmr"
STAGES = {
    "ranker": (6, 2048, 500000, 1500000),
    "reader": (3, 2048, 100000, 300000),
    "judge": (3, 1024, 100000, 300000),
}


def request_bytes(request):
    return len(
        json.dumps(
            request.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def load_inputs():
    raw = {k: path.read_bytes() for k, path in FILES.items()}
    hashes = {k: hashlib.sha256(v).hexdigest() for k, v in raw.items()}
    data = {k: json.loads(v) for k, v in raw.items()}
    all_cases, manifest = prepare(data["dataset"], data["manifest"], hashes["dataset"])
    selected = [next(c for c in all_cases if c[1].case_id == key) for key in CASES]
    for key in ("parent", "old_contexts", "old_qa", "pool_parent"):
        report = data[key]
        validate_fingerprint(report["plan"], "plan_fingerprint")
        if report["status"] != "complete":
            raise ValueError("complete frozen parents required")
    if (
        data["old_qa"]["plan"]["binding"]["contexts"] != hashes["old_contexts"]
        or data["parent"]["plan"]["manifest"] != manifest
    ):
        raise ValueError("frozen baseline binding changed")
    # A historical request is reused, not regenerated or relabelled.
    baselines = []
    for runtime, scoring in selected:
        row = next(
            r
            for r in data["old_contexts"]["rows"]
            if r["case_id"] == scoring.case_id
            and r["profile"] == "saved_source_passages_fit"
        )
        baselines.append(
            reused_baseline(
                row, (runtime, scoring), data["old_contexts"], data["old_qa"]
            )
        )
    return data, hashes, manifest, selected, baselines


class NoGenerate:
    name, version = "preflight-only", "1"

    async def generate(self, request):
        raise RuntimeError("preflight must not generate")


def source_request(query, scope, snippets):
    return ReferencePersonalMemoryReranker(NoGenerate()).build_request(
        PersonalMemoryRerankRequest(
            question=query,
            items=[
                PersonalMemoryRerankItem(
                    item_id=f"candidate-{i}",
                    content=source_content(
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
                    ),
                )
                for i, s in enumerate(snippets)
            ],
        )
    )


async def get_pool(store, index, runtime, scoring, manifest, parent, pool_parent):
    scope = memory_scope(manifest["run_namespace"], runtime.user_id)
    records = await inventory(store, [scope])
    digest = _hash({k: r.model_dump(mode="json") for k, r in records.items()})
    receipt = next(r for r in parent["receipts"] if r["case_id"] == scoring.case_id)
    if digest != receipt["corpus_sha256"]:
        raise ValueError("original Store changed")
    host = RawHistoryHost(store)
    host.sources = {
        (scope.scope_key, r.source_event_id): r.memory_id for r in records.values()
    }
    bound = bound_items(runtime, manifest, scope, host, records)
    if any(i is None for i in bound.values()):
        raise ValueError("unclassified source")
    strategy = HybridRetrievalStrategy(
        index,
        lexical_strategy=BM25RetrievalStrategy(),
        candidate_multiplier=1,
        fallback_to_lexical=False,
    )
    pool = list(
        await strategy.search(
            store,
            runtime.query.query,
            [scope],
            filters=MemoryFilter(states={MemoryState.CONFIRMED}),
            limit=80,
        )
    )
    pool_hash = _hash([c.model_dump(mode="json") for c in pool])
    previous = next(
        r
        for r in pool_parent["rows"]
        if r["case_id"] == scoring.case_id and r["profile"] == "content_only"
    )
    if pool_hash != previous["candidate_pool_sha256"]:
        raise ValueError("same-pool comparison cannot reproduce frozen candidates")
    retriever = AttributedContextRetriever(
        store, strategy=SavedCandidates(pool), resolve_event=host.resolve_event
    )
    authorized = await retriever.search(scope, runtime.query.query, limit=80)
    if len(authorized.snippets) != len(pool) or authorized.rejected:
        raise ValueError("source preflight did not revalidate complete candidate pool")
    generation = source_request(runtime.query.query, scope, authorized.snippets)
    certificate = {
        "case_id": scoring.case_id,
        "corpus_sha256": digest,
        "candidate_pool_sha256": pool_hash,
        "source_candidates": len(pool),
        "source_request_sha256": _request_sha256(generation),
        "source_request_bytes": request_bytes(generation),
        "source_content_chars": sum(
            len(i["content"]) for i in generation.input["items"]
        ),
    }
    return scope, host, pool, certificate


class AuditedRankModel:
    """Check the source request before its paid call; record every actual request."""

    def __init__(self, model, path):
        self.name, self.version = model.name, model.version
        self.model, self.path = model, path
        self.requests = []
        self.expected_source_sha = None

    async def generate(self, request):
        sha = _request_sha256(request)
        if self.expected_source_sha is not None and sha != self.expected_source_sha:
            raise ValueError("source request differs from zero-call preflight")
        self.expected_source_sha = None
        entry = {
            "request_sha256": sha,
            "bytes": request_bytes(request),
            "candidate_count": len(request.input["items"]),
        }
        self.requests.append(entry)
        # Before awaiting the provider: even an interrupted attempt has a receipt.
        save(self.path / f"rank-request-{len(self.requests)}.json", entry)
        return await self.model.generate(request)


def make_plan(hashes, certificates, schema):
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
        "diversity_weight": 0.0,
        "ranking_config": ReferencePersonalMemoryReranker(
            NoGenerate()
        ).config.model_dump(),
        "stages": {
            name: {
                "max_calls": cap,
                "config": config(tokens).model_dump(mode="json"),
                "max_request_bytes": size,
                "max_total_request_bytes": total,
            }
            for name, (cap, tokens, size, total) in STAGES.items()
        },
        "source_sha256": {
            path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in (
                __file__,
                "doppel_memory/reference_rerank.py",
                "doppel_memory/source_aware_rerank.py",
                "integrations/aml/context.py",
                "integrations/aml/passages.py",
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
    }
    if any(c["source_request_bytes"] > STAGES["ranker"][2] for c in certificates):
        raise ValueError("source request exceeds frozen byte cap")
    return {**value, "plan_fingerprint": _hash(value)}


async def execute(args, data, manifest, selected, baselines, plan, store, index):
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        raise ValueError("provider key absent")
    save(args.run_dir / "attempt.json", {"plan": plan})
    ledgers, models, rows = {}, {}, []
    rank_model = None
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
            # Exact config is bound in the plan; all keys stay in process memory.
            tokens = STAGES[name][1]
            models[name] = PilotStructuredModel(
                _default_provider_factory(
                    config(tokens), os.environ["DEEPSEEK_API_KEY"], ledger.observe_usage
                ),
                ledger=ledger,
                cache_dir=args.run_dir / name,
            )
        rank_model = AuditedRankModel(models["ranker"], args.run_dir)
        ranker = SourceAwareReranker(ReferencePersonalMemoryReranker(rank_model))
        reader = _StageExecutor(
            models["reader"], ledgers["reader"], ReaderV2Output, cache_only=False
        )
        judge = _StageExecutor(
            models["judge"], ledgers["judge"], Grade, cache_only=False
        )
        for i, (runtime, scoring) in enumerate(selected):
            scope, host, pool, certificate = await get_pool(
                store,
                index,
                runtime,
                scoring,
                manifest,
                data["parent"],
                data["pool_parent"],
            )
            if certificate != plan["certificates"][i]:
                raise ValueError("preflight certificate changed")
            rank_model.expected_source_sha = certificate["source_request_sha256"]
            sources = await AttributedContextRetriever(
                store,
                strategy=SavedCandidates(pool),
                resolve_event=host.resolve_event,
                reranker=ranker,
            ).search(scope, runtime.query.query, limit=20)
            source_parent = AttributedContextRetriever(
                store,
                strategy=SavedOrder(scope, [s.memory_id for s in sources.snippets]),
                resolve_event=host.resolve_event,
            )
            resolver = AttributedPassageRetriever(source_parent, reranker=ranker)
            result = await resolver.search(scope, runtime.query.query, limit=20)
            for passage in result.passages:
                await resolver.resolve_original(scope, passage)
            packed, trace = pack_ranked_fit([passage_item(p) for p in result.passages])
            entry = {
                "case_id": scoring.case_id,
                "profile": PROFILE,
                "context": packed,
                "context_bytes": len(encoded(packed)),
                "source_events": [s.evidence_id for s in sources.snippets],
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
            row = AnswerRow(
                i, scoring.case_id, PROFILE, runtime, scoring, tuple(packed)
            )
            output, record = await reader.execute(reader_request(row), i)
            entry.update(
                reader=record,
                reader_output=output.model_dump(mode="json") if output else None,
            )
            if output:
                grade, judged = await judge.execute(
                    task_request(runtime.query.query, scoring.answer, output.answer), i
                )
                entry.update(
                    checks=structural_check(row, output),
                    task_judge=judged,
                    grade=grade.model_dump(mode="json") if grade else None,
                )
            after = await inventory(store, [scope])
            if certificate["corpus_sha256"] != _hash(
                {k: r.model_dump(mode="json") for k, r in after.items()}
            ):
                raise ValueError("Store changed during read-only comparison")
            rows.append(entry)
            save(args.run_dir / f"answer-{i}.json", entry)
            print(
                f"completed {scoring.case_id}: grade={entry.get('grade')}", flush=True
            )
            if not output or not entry.get("grade"):
                raise RuntimeError("answer stage failed; no retry")
        status, failure = "complete", None
    except Exception as exc:  # noqa: BLE001 - no arbitrary exception content or secrets
        status, failure = "failed", type(exc).__name__
    result = {
        "runner": RUNNER,
        "status": status,
        "plan": plan,
        "rows": rows,
        "reused_baselines": baselines,
        "usage": {k: v.report() for k, v in ledgers.items()},
        "rank_requests": rank_model.requests if rank_model else [],
        "failure_class": failure,
    }
    for ledger in ledgers.values():
        ledger.close()
    return result


async def run(args):
    data, hashes, manifest, selected, baselines = load_inputs()
    schema = data["parent"]["plan"]["schema"]
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"), schema=schema
    )
    index = ReadOnlyVectorIndex(store, _LocalEmbeddingProvider(cache_dir=None))
    try:
        certificates = []
        for runtime, scoring in selected:
            *_, certificate = await get_pool(
                store,
                index,
                runtime,
                scoring,
                manifest,
                data["parent"],
                data["pool_parent"],
            )
            certificates.append(certificate)
        plan = make_plan(hashes, certificates, schema)
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
