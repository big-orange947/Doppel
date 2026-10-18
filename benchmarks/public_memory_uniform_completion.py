"""Finish the same affordable raw-only QA baseline on ordinals01-10/41-50.

Existing PostgreSQL sources/vectors are read-only. Local BGE prepares20 contexts;
at most40 paid QA calls; aggregate with the frozen30 without best-arm selection.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_context_baseline import score_evidence
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
from benchmarks.public_memory_high_config_first import (
    ReadOnlyStore,
    ReadOnlyVectorIndex,
)
from benchmarks.public_memory_listwise_diagnostic import request_bytes
from benchmarks.public_memory_passage_diagnostic import reader_request
from benchmarks.public_memory_pilot import _hash, history_group
from benchmarks.public_memory_prospective_selection import bind_host, model_identity
from benchmarks.public_memory_reader_v2 import ReaderV2Output, structural_check
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_source_aware_diagnostic import SavedCandidates
from benchmarks.public_memory_task_accuracy import Grade
from benchmarks.public_memory_task_accuracy import request as task_request
from benchmarks.public_memory_uniform_qa import PROFILE, digest
from doppel_memory.lexical import BM25RetrievalStrategy
from doppel_memory.models import RecallResult
from doppel_memory.vector import HybridRetrievalStrategy
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.contract import memory_scope

RUNNER = "doppel.uniform-whole-qa-completion.v1"
ORDINALS = (*range(1, 11), *range(41, 51))
ROOT = Path("data/doppel")
FILES = {
    "dataset": Path("data/public-benchmarks/longmemeval_s_cleaned.json"),
    "manifest": ROOT / "longmemeval-fresh-high-config-50-manifest-v1.json",
    "ingestion": ROOT
    / "longmemeval-fresh-high-config-50-ingestion-stage04-live-v1.json",
    "nograph": ROOT / "longmemeval-nograph-06-10-live-v1.json",
    "selection": ROOT / "prospective-selection-41-45-prepare-live-v1.json",
    "neighborhood": ROOT / "neighborhood-trial-46-50-prepare-live-v1.json",
    "baseline_retrieval": ROOT / "longmemeval-raw-retrieval-11-30-live-v1.json",
    "baseline_contexts": ROOT / "uniform-qa-11-40-prepare-live-v1.json",
    "baseline_answers": ROOT / "uniform-qa-11-40-answers-live-v1.json",
    **{
        f"query{i}": ROOT
        / f"longmemeval-fresh-high-config-50-query-scope{i:02d}-live-v1.json"
        for i in range(1, 6)
    },
}
STAGES = {"reader": (20, 2048), "judge": (20, 1024)}
SOURCES = (
    __file__,
    "benchmarks/public_memory_uniform_qa.py",
    "benchmarks/public_memory_answer_comparison.py",
    "benchmarks/public_memory_runtime.py",
    "benchmarks/public_memory_reader_v2.py",
    "benchmarks/public_memory_task_accuracy.py",
    "benchmarks/public_memory_passage_diagnostic.py",
    "benchmarks/public_memory_comparison.py",
    "benchmarks/public_memory_prospective_selection.py",
    "benchmarks/public_memory_high_config_first.py",
    "benchmarks/public_context_rerank.py",
    "benchmarks/public_longmemeval.py",
    "doppel_memory/lexical.py",
    "doppel_memory/vector.py",
    "doppel_memory/postgres_store.py",
    "integrations/aml/context.py",
)


class RawOnlyStore(ReadOnlyStore):
    """Query-only channel restriction BEFORE BM25 corpus statistics/vector LIMIT.

    Raw-only schemas have the same eligible corpus. Mixed schemas must not let
    extracted EVENT records affect IDF or consume the80-candidate window.
    No schema/view creation, mutation, role filtering or question heuristics.
    """

    @staticmethod
    def _append_filters(where, params, filters, *, prefix=""):
        if prefix not in {"", "record."}:
            raise ValueError("unexpected internal SQL prefix")
        ReadOnlyStore._append_filters(where, params, filters, prefix=prefix)
        params.append("ingestor")
        where.append(f"{prefix}extractor=${len(params)}")


def load_inputs():
    content = {k: p.read_bytes() for k, p in FILES.items()}
    binding = {k: hashlib.sha256(v).hexdigest() for k, v in content.items()}
    data = {k: json.loads(v) for k, v in content.items()}
    queue, groups = prepare_inputs(data, binding)
    return data, binding, queue, groups


def prepare_inputs(data, binding):
    parent = data["manifest"]
    validate_fingerprint(parent, "manifest_fingerprint")
    if binding["dataset"] != parent["source_sha256"]:
        raise ValueError("unchanged dataset required")
    selected = [r for r in parent["cases"] if r["partition"] == "diagnostic"]
    by_id = {r["question_id"]: r for r in data["dataset"]}
    if len(selected) != 50 or len(by_id) != len(data["dataset"]):
        raise ValueError("fifty fixed unique diagnostic cases required")
    for key in (
        "selection",
        "neighborhood",
        "baseline_retrieval",
        "baseline_contexts",
        "baseline_answers",
    ):
        report = data[key]
        validate_fingerprint(report["plan"], "plan_fingerprint")
        if report["status"] != "complete":
            raise ValueError("complete frozen parent reports required")
    baseline = data["baseline_answers"]
    if (
        baseline["plan"]["preparation_sha256"] != _hash(data["baseline_contexts"])
        or len(baseline["rows"]) != 30
        or {r["ordinal"] for r in baseline["rows"]} != set(range(11, 41))
    ):
        raise ValueError("exact completed uniform30 baseline required")
    for stage, (_, tokens) in STAGES.items():
        if baseline["plan"]["stages"][stage]["config"] != config(tokens).model_dump(
            mode="json"
        ):
            raise ValueError("same Reader/judge configuration required")
    for path in (
        "benchmarks/public_memory_comparison.py",
        "benchmarks/public_memory_reader_v2.py",
        "benchmarks/public_memory_task_accuracy.py",
        "benchmarks/public_memory_passage_diagnostic.py",
    ):
        if (
            hashlib.sha256(Path(path).read_bytes()).hexdigest()
            != baseline["plan"]["source_sha256"][path]
        ):
            raise ValueError("shared baseline code changed")
    groups = {
        "first": {
            "manifest": parent,
            "schema": data["ingestion"]["ingestion"]["postgres_schema"],
        },
        **{
            key: {
                "manifest": data[key]["plan"]["manifest"],
                "schema": data[key]["plan"]["schema"],
            }
            for key in ("selection", "neighborhood")
        },
    }
    forbidden = {
        r["history_group"] for r in parent["cases"] if r["partition"] != "diagnostic"
    }
    queue = []
    for ordinal in ORDINALS:
        meta = selected[ordinal - 1]
        case = prepare_case(
            by_id[meta["case_id"]], dataset_namespace=parent["dataset_namespace"]
        )
        chunks = case.runtime.ingestion_chunks(max_messages=parent["max_messages"])
        if (
            history_group(case) != meta["history_group"]
            or meta["history_group"] in forbidden
            or len(chunks) != meta["chunk_count"]
            or sum(len(s.turns) for s in case.runtime.sessions)
            != meta["raw_turn_count"]
            or _hash([c.request.model_dump(mode="json") for c in chunks])
            != meta["history_payload_sha256"]
        ):
            raise ValueError("fixed source binding changed or overlaps reserved")
        forbidden.add(meta["history_group"])
        pool = None
        if ordinal <= 10:
            group = "first"
            if ordinal <= 5:
                report = data[f"query{ordinal}"]
                if report["status"] != "complete":
                    raise ValueError("original source receipt incomplete")
                source = report["plans"]["raw_vector_reranked"]
            else:
                if data["nograph"]["status"] != "complete":
                    raise ValueError("original non-graph source receipt incomplete")
                source = data["nograph"]["plans"][str(ordinal)]["raw_vector_reranked"]
            validate_fingerprint(source, "plan_fingerprint")
            corpus = source["corpus_sha256"]
        else:
            group = "selection" if ordinal <= 45 else "neighborhood"
            report = data[group]
            receipt = next(
                r for r in report["receipts"] if r["case_id"] == case.scoring.case_id
            )
            if ordinal <= 45:
                pool = receipt["pool"]
                if _hash(pool) != receipt["pool_sha256"]:
                    raise ValueError("original80 pool changed")
            else:
                frozen = receipt["pools"]["neighborhood"]
                if (
                    _hash(frozen["pool"]) != frozen["pool_sha256"]
                    or receipt["expansion"]["anchor_count"] != 80
                ):
                    raise ValueError("original anchor pool binding changed")
                pool = frozen["pool"][
                    :80
                ]  # preserved original anchors, NOT nativeN prefix
            if len(pool) != 80:
                raise ValueError("exact original80 candidate window required")
            corpus = receipt["corpus_sha256"]
        queue.append(
            (
                {
                    "ordinal": ordinal,
                    "case_id": case.scoring.case_id,
                    "group": group,
                    "corpus_sha256": corpus,
                    "raw_records": meta["raw_turn_count"],
                    "pool": pool,
                },
                case.runtime,
                case.scoring,
            )
        )
    return queue, groups


def make_plan(phase, data, binding, queue, groups, preparation=None):
    value = {
        "runner": RUNNER,
        "phase": phase,
        "binding": binding,
        "groups": groups,
        "profile": PROFILE,
        "queue": [
            {
                k: m[k]
                for k in ("ordinal", "case_id", "group", "corpus_sha256", "raw_records")
            }
            for m, _, _ in queue
        ],
        "candidate_window": 80,
        "source_limit": 20,
        "context_byte_limit": 24000,
        "packing": "existing-whole-item-ranked-fit; no text truncation",
        "fusion": "production-BM25-vector-RRF60-equal-no-fallback",
        "channel": "all raw ingestor events only; SQL before lexical IDF/vector LIMIT",
        "pool_policy": "first10 fresh raw-only search; last10 frozen original80 anchors; no nativeN-prefix reuse",
        "embedding": "fastembed:BAAI/bge-small-zh-v1.5/0.8.0/512",
        "reranker": data["baseline_retrieval"]["plan"]["reranker"],
        "bm25": BM25RetrievalStrategy().config.model_dump(mode="json"),
        "source_sha256": {
            p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in SOURCES
        },
        "stages": {
            n: {
                "max_calls": cap,
                "config": config(tokens).model_dump(mode="json"),
                "max_request_bytes": 100000,
                "max_total_request_bytes": 2000000,
            }
            for n, (cap, tokens) in STAGES.items()
        },
        "automatic_retries": 0,
        "graph_calls": 0,
        "source_writes": 0,
        "llm_selection": False,
        "local_query_embeddings_max": 10,
        "local_rerank_operations_max": 20,
        "pairs_max": 1600,
        "opened_development_not_blind": True,
        "publication_ready": False,
        "official_longmemeval_score": False,
        "aml_score": False,
    }
    if preparation is not None:
        if preparation["status"] != "complete" or any(
            preparation["plan"][k] != v for k, v in value.items() if k != "phase"
        ):
            raise ValueError("preparation/runtime changed")
        if len(preparation["rows"]) != 20 or [
            r["ordinal"] for r in preparation["rows"]
        ] != list(ORDINALS):
            raise ValueError("exact twenty frozen contexts required")
        value.update(
            preparation_sha256=_hash(preparation),
            reader_requests=[
                {
                    k: r[k]
                    for k in (
                        "ordinal",
                        "reader_request_sha256",
                        "reader_request_bytes",
                        "context_sha256",
                    )
                }
                for r in preparation["rows"]
            ],
        )
    return {**value, "plan_fingerprint": _hash(value)}


async def bound_source(store, meta, runtime, group):
    scope = memory_scope(group["manifest"]["run_namespace"], runtime.user_id)
    records = await inventory(store, [scope])
    if digest(records) != meta["corpus_sha256"]:
        raise ValueError("original full Store inventory changed")
    raw = {k: r for k, r in records.items() if r.extractor == "ingestor"}
    if len(raw) != meta["raw_records"]:
        raise ValueError("raw source count mismatch")
    host, items = bind_host(runtime, group["manifest"], scope, raw, store)
    return scope, host, items


async def prepare_run(args, data, queue, groups, plan):
    save(args.run_dir / "prepare-attempt.json", {"plan": plan})
    stores, raw_stores, rows = {}, {}, []
    current, stage = None, "initialization"
    provider = None
    try:
        provider = LocalContextCrossEncoder(
            Path(plan["reranker"]["model_path"]),
            device="cuda",
            max_length=8192,
            batch_size=1,
        )
        if model_identity(provider) != plan["reranker"]:
            raise ValueError("exact frozen BGE runtime/weights required")
        embedder = _LocalEmbeddingProvider(cache_dir=None)
        if (embedder.name, embedder.version, embedder.dimensions) != (
            "fastembed:BAAI/bge-small-zh-v1.5",
            "0.8.0",
            512,
        ):
            raise ValueError("embedding identity differs")
        for key, group in groups.items():
            dsn = local_diagnostic_dsn("doppel-ablation-pgvector")
            stores[key] = ReadOnlyStore(dsn, schema=group["schema"])
            raw_stores[key] = RawOnlyStore(dsn, schema=group["schema"])
        vector = ReadOnlyVectorIndex(raw_stores["first"], embedder)
        hybrid = HybridRetrievalStrategy(
            vector,
            lexical_strategy=BM25RetrievalStrategy(),
            candidate_multiplier=1,
            fallback_to_lexical=False,
        )
        for meta, runtime, scoring in queue:
            current, stage = scoring.case_id, "source-validation"
            group, store = groups[meta["group"]], stores[meta["group"]]
            scope, host, items = await bound_source(store, meta, runtime, group)
            strategy = (
                hybrid
                if meta["pool"] is None
                else SavedCandidates(
                    [RecallResult.model_validate(c) for c in meta["pool"]]
                )
            )
            source_store = raw_stores[meta["group"]] if meta["pool"] is None else store
            # Freeze the actual authorized80 without another query embedding.
            anchors = await AttributedContextRetriever(
                source_store,
                strategy=strategy,
                resolve_event=host.resolve_event,
                candidate_multiplier=1,
            ).search(scope, runtime.query.query, limit=80)
            if anchors.rejected or len(anchors.snippets) != 80:
                raise ValueError("complete raw-only80 window required")
            from integrations.aml.neighborhood import as_candidate

            pool = [as_candidate(scope, s) for s in anchors.snippets]
            strict = StrictContextReranker(provider)
            stage = "local-rerank"
            result = await AttributedContextRetriever(
                store,
                strategy=SavedCandidates(pool),
                resolve_event=host.resolve_event,
                reranker=strict,
            ).search(scope, runtime.query.query, limit=20)
            if (
                result.rejected
                or result.revalidated != 80
                or len(result.snippets) != 20
                or strict.last_summary is None
                or strict.last_summary.status != "completed"
            ):
                raise ValueError("strict local raw reranking failed")
            positions = {i["memory_id"]: p for p, i in items.items()}
            ranked = [items[positions[s.memory_id]] for s in result.snippets]
            packed, trace = pack_ranked_fit(ranked)
            chosen = [positions[i["memory_id"]] for i in packed]
            row = AnswerRow(
                len(rows), current, PROFILE, runtime, scoring, tuple(packed)
            )
            request = reader_request(row)
            if request_bytes(request) > 100000:
                raise ValueError("frozen Reader cap exceeded")
            entry = {
                **{
                    k: meta[k] for k in ("ordinal", "case_id", "group", "corpus_sha256")
                },
                "context": packed,
                "context_bytes": len(encoded(packed)),
                "context_sha256": hashlib.sha256(encoded(packed)).hexdigest(),
                "pool": [c.model_dump(mode="json") for c in pool],
                "pool_sha256": _hash([c.model_dump(mode="json") for c in pool]),
                "candidate_coverage": score_evidence(
                    scoring, [positions[s.memory_id] for s in anchors.snippets]
                ),
                "retrieved_coverage": score_evidence(
                    scoring, [positions[s.memory_id] for s in result.snippets]
                ),
                "packed_coverage": score_evidence(scoring, chosen),
                "source_execution": result.model_dump(
                    mode="json", exclude={"snippets"}
                ),
                "rerank_summary": strict.last_summary.model_dump(mode="json"),
                "packing_trace": trace,
                "reader_request_sha256": _request_sha256(request),
                "reader_request_bytes": request_bytes(request),
            }
            if digest(await inventory(store, [scope])) != meta["corpus_sha256"]:
                raise ValueError("Store changed during local preparation")
            rows.append(entry)
            save(args.run_dir / f"context-{len(rows) - 1}.json", entry)
            print(
                f"prepared {len(rows)}/20 (ordinal {meta['ordinal']}); local BGE only",
                flush=True,
            )
        status, failure = "complete", None
    except Exception as exc:  # noqa: BLE001 - redact credentials/model text
        status, failure = "failed", type(exc).__name__
    finally:
        for store in (*stores.values(), *raw_stores.values()):
            await store.close()
    return {
        "status": status,
        "rows": rows,
        "failure_class": failure,
        "stopped_case": current if failure else None,
        "stopped_stage": stage if failure else None,
        "new_calls": 0,
        "reranker": provider.report() if provider else None,
    }


def summarize(rows, expected):
    completed = [r for r in rows if r.get("grade") is not None]

    def score(part):
        return {
            "n": len(part),
            "correct": sum(r["grade"]["answer_correct"] for r in part),
            "accuracy": sum(r["grade"]["answer_correct"] for r in part) / len(part)
            if part
            else None,
        }

    positive = [r for r in completed if not r["abstention_label"]]
    return {
        "expected": expected,
        **score(completed),
        "complete": len(completed) == expected,
        "answerable": score(positive),
        "unanswerable": score([r for r in completed if r["abstention_label"]]),
        "positive_by_type": {
            k: score([r for r in positive if r["question_type"] == k])
            for k in sorted({r["question_type"] for r in positive})
        },
        "structurally_valid": sum(r["checks"]["structurally_valid"] for r in completed),
    }


async def evaluate_run(args, queue, groups, plan, preparation):
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        raise ValueError("provider key absent")
    save(args.run_dir / "answers-attempt.json", {"plan": plan})
    ledgers, models, stores, rows = {}, {}, {}, []
    current, stage = None, "initialization"
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
                raise ValueError("preserve prior attempts")
            models[name] = PilotStructuredModel(
                _default_provider_factory(
                    config(STAGES[name][1]),
                    os.environ["DEEPSEEK_API_KEY"],
                    ledger.observe_usage,
                ),
                ledger=ledger,
                cache_dir=args.run_dir / name,
            )
        reader = _StageExecutor(
            models["reader"], ledgers["reader"], ReaderV2Output, cache_only=False
        )
        judge = _StageExecutor(
            models["judge"], ledgers["judge"], Grade, cache_only=False
        )
        for key, group in groups.items():
            stores[key] = ReadOnlyStore(
                local_diagnostic_dsn("doppel-ablation-pgvector"), schema=group["schema"]
            )
        for (meta, runtime, scoring), context in zip(
            queue, preparation["rows"], strict=True
        ):
            current, stage = scoring.case_id, "source-validation"
            if context["ordinal"] != meta["ordinal"] or context["case_id"] != current:
                raise ValueError("frozen context order changed")
            group, store = groups[meta["group"]], stores[meta["group"]]
            scope, host, items = await bound_source(store, meta, runtime, group)
            pool = [RecallResult.model_validate(c) for c in context["pool"]]
            if _hash(context["pool"]) != context["pool_sha256"]:
                raise ValueError("prepared pool changed")
            valid = await AttributedContextRetriever(
                store,
                strategy=SavedCandidates(pool),
                resolve_event=host.resolve_event,
                candidate_multiplier=1,
            ).search(scope, runtime.query.query, limit=80)
            if valid.rejected or len(valid.snippets) != 80:
                raise ValueError("prepared candidates no longer eligible")
            by_id = {i["memory_id"]: i for i in items.values()}
            packed = context["context"]
            if (
                hashlib.sha256(encoded(packed)).hexdigest() != context["context_sha256"]
                or len(encoded(packed)) > 24000
                or len(packed) > 20
                or any(by_id.get(i["memory_id"]) != i for i in packed)
            ):
                raise ValueError("prepared original context changed")
            row = AnswerRow(
                len(rows), current, PROFILE, runtime, scoring, tuple(packed)
            )
            request = reader_request(row)
            if _request_sha256(request) != context["reader_request_sha256"]:
                raise ValueError("frozen Reader request changed")
            stage = "reader"
            output, record = await reader.execute(request, len(rows))
            entry = {
                "ordinal": meta["ordinal"],
                "case_id": current,
                "profile": PROFILE,
                "question_type": scoring.category,
                "abstention_label": scoring.abstention,
                "context_sha256": context["context_sha256"],
                "context_bytes": len(encoded(packed)),
                "packed_coverage": context["packed_coverage"],
                "reader": record,
                "reader_output": output.model_dump(mode="json") if output else None,
            }
            if output:
                stage = "task-judge"
                grade, judged = await judge.execute(
                    task_request(runtime.query.query, scoring.answer, output.answer),
                    len(rows),
                )
                entry.update(
                    checks=structural_check(row, output),
                    task_judge=judged,
                    grade=grade.model_dump(mode="json") if grade else None,
                )
            rows.append(entry)
            save(args.run_dir / f"answer-{len(rows) - 1}.json", entry)
            if not output or not entry.get("grade"):
                raise RuntimeError("QA failure retained; no retry")
            stage = "final-store-validation"
            if digest(await inventory(store, [scope])) != meta["corpus_sha256"]:
                raise ValueError("Store changed during QA")
            print(f"answered {len(rows)}/20 (ordinal {meta['ordinal']})", flush=True)
        status, failure = "complete", None
    except Exception as exc:  # noqa: BLE001 - redact provider errors
        status, failure = "failed", type(exc).__name__
    finally:
        for store in stores.values():
            await store.close()
    result = {
        "status": status,
        "rows": rows,
        "summary": summarize(rows, 20),
        "failure_class": failure,
        "stopped_case": current if failure else None,
        "stopped_stage": stage if failure else None,
        "usage": {k: l.report() for k, l in ledgers.items()},
    }
    for ledger in ledgers.values():
        ledger.close()
    return result


def aggregate(data, binding, completion, preparation):
    validate_fingerprint(completion["plan"], "plan_fingerprint")
    validate_fingerprint(preparation["plan"], "plan_fingerprint")
    queue, groups = prepare_inputs(data, binding)
    expected = make_plan("answers", data, binding, queue, groups, preparation)
    if (
        completion["status"] != "complete"
        or completion["plan"] != expected
        or completion["plan"]["binding"] != binding
        or completion["plan"]["preparation_sha256"] != _hash(preparation)
    ):
        raise ValueError("complete bound20 required")
    old = data["baseline_answers"]
    if completion["plan"]["profile"] != old["plan"]["profile"] or any(
        completion["plan"][k] != old["plan"][k]
        for k in ("candidate_window", "source_limit", "context_byte_limit", "packing")
    ):
        raise ValueError("uniform profile contract differs")
    for stage in STAGES:
        if (
            completion["plan"]["stages"][stage]["config"]
            != old["plan"]["stages"][stage]["config"]
        ):
            raise ValueError("uniform QA model differs")
    rows = sorted([*old["rows"], *completion["rows"]], key=lambda r: r["ordinal"])
    selected = [r for r in data["manifest"]["cases"] if r["partition"] == "diagnostic"]
    if (
        len(rows) != 50
        or [r["ordinal"] for r in rows] != list(range(1, 51))
        or [r["case_id"] for r in rows] != [r["case_id"] for r in selected]
        or any(r.get("grade") is None for r in rows)
    ):
        raise ValueError("fifty exact disjoint graded rows required")
    return {
        "runner": "doppel.uniform-whole-qa-fifty-summary.v1",
        "status": "complete",
        "summary": summarize(rows, 50),
        "rows": rows,
        "parent_sha256": {
            "uniform30": binding["baseline_answers"],
            "completion20": _hash(completion),
            "completion_contexts": _hash(preparation),
        },
        "publication_ready": False,
        "official_longmemeval_score": False,
        "aml_score": False,
        "opened_development_not_blind": True,
        "usage": {"uniform30": old["usage"], "completion20": completion["usage"]},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase", choices=("prepare", "answers", "aggregate"), required=True
    )
    parser.add_argument("--preparation", type=Path)
    parser.add_argument("--answers", type=Path)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("fresh output required")
    data, binding, queue, groups = load_inputs()
    preparation = (
        json.loads(args.preparation.read_bytes()) if args.preparation else None
    )
    if args.phase == "aggregate":
        if preparation is None or args.answers is None:
            parser.error("completed contexts and answers required")
        result = aggregate(
            data, binding, json.loads(args.answers.read_bytes()), preparation
        )
    else:
        if args.phase == "answers":
            if preparation is None:
                parser.error("completed preparation required")
            validate_fingerprint(preparation["plan"], "plan_fingerprint")
        elif preparation is not None:
            parser.error("prepare cannot accept previous preparation")
        plan = make_plan(args.phase, data, binding, queue, groups, preparation)
        result = {"runner": RUNNER, "status": "ready", "plan": plan}
        if args.execute:
            if (
                not args.frozen_preflight
                or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
            ):
                parser.error("matching frozen preflight required")
            result.update(
                asyncio.run(
                    prepare_run(args, data, queue, groups, plan)
                    if args.phase == "prepare"
                    else evaluate_run(args, queue, groups, plan, preparation)
                )
            )
    save(args.output, result)
    print(
        json.dumps({"status": result["status"], "summary": result.get("summary", {})})
    )
    raise SystemExit(0 if result["status"] in {"ready", "complete"} else 1)


if __name__ == "__main__":
    main()
