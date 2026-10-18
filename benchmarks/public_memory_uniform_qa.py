"""Fixed30 opened-history QA baseline; first finish27 previously unanswered items.

Reuse frozen raw BM25/vector/BGE top20 order and exact24KB ranked-fit contexts.
No retrieval/model rerun, graph, LLM selection, source writes or implicit retry.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

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
from benchmarks.public_memory_listwise_diagnostic import request_bytes
from benchmarks.public_memory_passage_diagnostic import reader_request
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_prospective_selection import bind_host
from benchmarks.public_memory_raw_continuation import prepare as prepare_ten
from benchmarks.public_memory_reader_v2 import ReaderV2Output, structural_check
from benchmarks.public_memory_retrieval_expansion import prepare as prepare_twenty
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_task_accuracy import Grade
from benchmarks.public_memory_task_accuracy import request as task_request
from integrations.aml.contract import memory_scope

RUNNER = "doppel.uniform-whole-qa-11-40.v1"
PROFILE = "raw_bm25_vector_reranked_whole_fit"
RETRIEVAL_PROFILE = "raw_bm25_vector_reranked"
PREVIOUS_QA_ORDINALS = (32, 37, 40)
FILES = {
    "dataset": Path("data/public-benchmarks/longmemeval_s_cleaned.json"),
    "manifest": Path("data/doppel/longmemeval-fresh-high-config-50-manifest-v1.json"),
    "twenty": Path("data/doppel/longmemeval-raw-retrieval-11-30-live-v1.json"),
    "packing": Path("data/doppel/longmemeval-raw-packing-fit-11-30-live-v1.json"),
    "ten": Path("data/doppel/longmemeval-raw-31-40-live-v1.json"),
}
STAGES = {"reader": (30, 2048), "judge": (30, 1024)}
SOURCE_FILES = (
    __file__,
    "benchmarks/public_memory_comparison.py",
    "benchmarks/public_memory_passage_diagnostic.py",
    "benchmarks/public_memory_reader_v2.py",
    "benchmarks/public_memory_task_accuracy.py",
    "benchmarks/public_memory_answer_comparison.py",
    "benchmarks/public_memory_prospective_selection.py",
    "benchmarks/public_memory_raw_continuation.py",
    "benchmarks/public_memory_retrieval_expansion.py",
    "benchmarks/public_memory_high_config_first.py",
    "benchmarks/public_memory_expansion.py",
    "benchmarks/public_memory_runtime.py",
    "benchmarks/public_longmemeval.py",
)


def load_inputs():
    content = {k: p.read_bytes() for k, p in FILES.items()}
    binding = {k: hashlib.sha256(v).hexdigest() for k, v in content.items()}
    data = {k: json.loads(v) for k, v in content.items()}
    return (*prepare_inputs(data, binding), binding)


def prepare_inputs(data, binding):
    """Select all30 by frozen parent order, not outcomes or question contents."""
    for key in ("twenty", "packing", "ten"):
        validate_fingerprint(data[key]["plan"], "plan_fingerprint")
        if data[key]["status"] != "complete":
            raise ValueError("complete original reports required")
    groups, queue = {}, []
    for key, factory in (("twenty", prepare_twenty), ("ten", prepare_ten)):
        cases, manifest = factory(
            data["dataset"], data["manifest"], source_sha=binding["dataset"]
        )
        report = data[key]
        if report["plan"]["manifest"] != manifest:
            raise ValueError("original manifest/source binding changed")
        groups[key] = {"manifest": manifest, "schema": report["plan"]["schema"]}
        for meta, pair in zip(manifest["cases"], cases, strict=True):
            runtime, scoring = pair
            original = [
                r
                for r in report["rows"]
                if r["case_id"] == scoring.case_id and r["profile"] == RETRIEVAL_PROFILE
            ]
            if len(original) != 1:
                raise ValueError("exactly one fixed ranking per case required")
            if key == "twenty":
                matches = [
                    r
                    for r in data["packing"]["rows"]
                    if r["case_id"] == scoring.case_id
                    and r["profile"] == RETRIEVAL_PROFILE
                ]
                certs = [
                    r
                    for r in data["packing"]["source_certificates"]
                    if r["case_id"] == scoring.case_id
                ]
                if (
                    len(matches) != 1
                    or len(certs) != 1
                    or certs[0]["before_sha256"] != certs[0]["after_sha256"]
                ):
                    raise ValueError("unique unchanged source/packing receipt required")
                packed, digest = matches[0]["ranked_fit"], certs[0]["after_sha256"]
            else:
                certs = [
                    r for r in report["receipts"] if r["case_id"] == scoring.case_id
                ]
                if len(certs) != 1:
                    raise ValueError("unique ten-history source receipt required")
                packed, digest = (
                    original[0]["packing"]["ranked_fit"],
                    certs[0]["corpus_sha256"],
                )
            queue.append(
                (
                    {
                        "ordinal": meta["ordinal"],
                        "case_id": scoring.case_id,
                        "group": key,
                        "previous_qa": meta["ordinal"] in PREVIOUS_QA_ORDINALS,
                        "corpus_sha256": digest,
                        "packed_sha256": packed["packed_context_sha256"],
                        "positions": original[0]["retrieved_source_positions"],
                        "packed_positions": packed["packed_positions"],
                        "candidate_coverage": original[0]["candidate_window_score"],
                        "retrieved_coverage": original[0]["at_20"],
                        "packed_coverage": packed["after"],
                    },
                    runtime,
                    scoring,
                )
            )
    if data["twenty"]["plan"]["reranker"] != data["ten"]["plan"]["reranker"]:
        raise ValueError("same frozen local reranker required")
    packing_binding = data["packing"]["plan"]["binding"]
    if (
        packing_binding["retrieval_report"] != binding["twenty"]
        or packing_binding["dataset"] != binding["dataset"]
        or packing_binding["parent_manifest"] != binding["manifest"]
    ):
        raise ValueError("packing/retrieval/dataset binding changed")
    if (
        len(queue) != 30
        or {r[0]["ordinal"] for r in queue} != set(range(11, 41))
        or len({r[0]["case_id"] for r in queue}) != 30
    ):
        raise ValueError("exact fixed thirty unique cases required")
    queue.sort(key=lambda r: (r[0]["previous_qa"], r[0]["ordinal"]))
    return queue, groups


def make_plan(phase, queue, groups, binding, preparation=None):
    value = {
        "runner": RUNNER,
        "phase": phase,
        "binding": binding,
        "groups": groups,
        "queue": [
            {
                k: meta[k]
                for k in (
                    "ordinal",
                    "case_id",
                    "group",
                    "previous_qa",
                    "corpus_sha256",
                    "packed_sha256",
                )
            }
            for meta, _, _ in queue
        ],
        "profile": PROFILE,
        "candidate_window": 80,
        "source_limit": 20,
        "context_byte_limit": 24000,
        "packing": "existing-whole-item-ranked-fit; no text truncation",
        "policy": "reuse saved BM25/vector/BGE rankings; no retrieval or source-selection rerun",
        "source_sha256": {
            p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in SOURCE_FILES
        },
        "stages": {
            n: {
                "max_calls": cap,
                "config": config(tokens).model_dump(mode="json"),
                "max_request_bytes": 100000,
                "max_total_request_bytes": 3000000,
            }
            for n, (cap, tokens) in STAGES.items()
        },
        "automatic_retries": 0,
        "graph_calls": 0,
        "source_writes": 0,
        "retrieval_rerun": False,
        "llm_selection": False,
        "opened_development_not_blind": True,
        "publication_ready": False,
        "official_longmemeval_score": False,
        "aml_score": False,
        "primary": "unchanged provisional DeepSeek task accuracy; report positive/negative/type separately",
    }
    if preparation is not None:
        if preparation["status"] != "complete" or any(
            preparation["plan"][k] != v for k, v in value.items() if k != "phase"
        ):
            raise ValueError("preparation/runtime binding changed")
        rows = preparation["rows"]
        if len(rows) != 30 or [r["case_id"] for r in rows] != [
            r[0]["case_id"] for r in queue
        ]:
            raise ValueError("thirty frozen contexts in exact queue order required")
        value.update(
            preparation_sha256=_hash(preparation),
            reader_requests=[
                {
                    k: r[k]
                    for k in (
                        "case_id",
                        "reader_request_sha256",
                        "reader_request_bytes",
                    )
                }
                for r in rows
            ],
        )
    return {**value, "plan_fingerprint": _hash(value)}


def digest(records):
    return _hash({k: r.model_dump(mode="json") for k, r in records.items()})


def checked_context(meta, items):
    positions = [tuple(p) for p in meta["positions"]]
    if len(positions) > 20 or len(set(positions)) != len(positions):
        raise ValueError("original ranking is not a unique bounded source order")
    packed, trace = pack_ranked_fit([items[p] for p in positions])
    selected = [list(positions[i - 1]) for i in trace["selected_rank_positions"]]
    if (
        hashlib.sha256(encoded(packed)).hexdigest() != meta["packed_sha256"]
        or selected != meta["packed_positions"]
        or len(encoded(packed)) > 24000
    ):
        raise ValueError("saved whole-message context not exactly reproduced")
    return packed


async def prepare_run(args, queue, groups, plan):
    save(args.run_dir / "prepare-attempt.json", {"plan": plan})
    rows, stores = [], {}
    current, stage = None, "initialization"
    try:
        for key, group in groups.items():
            stores[key] = ReadOnlyStore(
                local_diagnostic_dsn("doppel-ablation-pgvector"), schema=group["schema"]
            )
        for meta, runtime, scoring in queue:
            current, stage = scoring.case_id, "context-source-validation"
            group, store = groups[meta["group"]], stores[meta["group"]]
            scope = memory_scope(group["manifest"]["run_namespace"], runtime.user_id)
            records = await inventory(store, [scope])
            if digest(records) != meta["corpus_sha256"]:
                raise ValueError("original Store inventory changed")
            _, items = bind_host(runtime, group["manifest"], scope, records, store)
            packed = checked_context(meta, items)
            row = AnswerRow(
                len(rows), current, PROFILE, runtime, scoring, tuple(packed)
            )
            request = reader_request(row)
            if request_bytes(request) > 100000:
                raise ValueError("Reader request exceeds frozen cap")
            if digest(await inventory(store, [scope])) != meta["corpus_sha256"]:
                raise ValueError("Store changed during read-only preparation")
            entry = {
                **meta,
                "context": packed,
                "context_bytes": len(encoded(packed)),
                "reader_request_sha256": _request_sha256(request),
                "reader_request_bytes": request_bytes(request),
            }
            rows.append(entry)
            save(args.run_dir / f"context-{len(rows) - 1}.json", entry)
            print(f"prepared {len(rows)}/30 existing contexts; zero LLM", flush=True)
        status, failure = "complete", None
    except Exception as exc:  # noqa: BLE001 - redact credentials/provider errors
        status, failure = "failed", type(exc).__name__
    finally:
        for store in stores.values():
            await store.close()
    return {
        "status": status,
        "rows": rows,
        "failure_class": failure,
        "stopped_case": current if failure else None,
        "stopped_stage": stage if failure else None,
        "new_calls": 0,
    }


def summary(rows):
    completed = [r for r in rows if r.get("grade") is not None]

    def score(part):
        return {
            "completed": len(part),
            "correct": sum(r["grade"]["answer_correct"] for r in part),
            "accuracy": sum(r["grade"]["answer_correct"] for r in part) / len(part)
            if part
            else None,
        }

    return {
        "expected": 30,
        **score(completed),
        "previously_unanswered": score([r for r in completed if not r["previous_qa"]]),
        "previously_answered_diagnostic": score(
            [r for r in completed if r["previous_qa"]]
        ),
        "answerable": score([r for r in completed if not r["abstention_label"]]),
        "unanswerable": score([r for r in completed if r["abstention_label"]]),
        "by_type": {
            kind: score([r for r in completed if r["question_type"] == kind])
            for kind in sorted({r["question_type"] for r in completed})
        },
        "structurally_valid": sum(
            r.get("checks", {}).get("structurally_valid", False) for r in completed
        ),
        "all_thirty_complete": len(completed) == 30,
    }


async def evaluate_run(args, queue, groups, plan, preparation):
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        raise ValueError("provider key absent")
    save(args.run_dir / "answers-attempt.json", {"plan": plan})
    ledgers, models, stores, rows = {}, {}, {}, []
    current, stage = None, "initialization"
    try:
        for n, limits in plan["stages"].items():
            ledger = DurableCallLedger(
                args.run_dir / "usage.sqlite3",
                budget_id=plan["plan_fingerprint"] + ":" + n,
                max_calls=limits["max_calls"],
                max_request_bytes=limits["max_request_bytes"],
                max_total_request_bytes=limits["max_total_request_bytes"],
            )
            ledgers[n] = ledger
            if ledger.report()["attempts_reserved"]:
                raise ValueError("preserve previous paid attempts")
            models[n] = PilotStructuredModel(
                _default_provider_factory(
                    config(STAGES[n][1]),
                    os.environ["DEEPSEEK_API_KEY"],
                    ledger.observe_usage,
                ),
                ledger=ledger,
                cache_dir=args.run_dir / n,
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
            if context["case_id"] != current:
                raise ValueError("frozen queue changed")
            group, store = groups[meta["group"]], stores[meta["group"]]
            scope = memory_scope(group["manifest"]["run_namespace"], runtime.user_id)
            records = await inventory(store, [scope])
            if digest(records) != meta["corpus_sha256"]:
                raise ValueError("source changed before answering")
            _, items = bind_host(runtime, group["manifest"], scope, records, store)
            packed = checked_context(meta, items)
            if packed != context["context"]:
                raise ValueError("prepared context changed")
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
                "previous_qa": meta["previous_qa"],
                "question_type": scoring.category,
                "abstention_label": scoring.abstention,
                "profile": PROFILE,
                "context_sha256": meta["packed_sha256"],
                "context_bytes": len(encoded(packed)),
                "packed_coverage": meta["packed_coverage"],
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
                raise ValueError("Store changed during read-only QA")
            print(
                f"answered {len(rows)}/30 (ordinal {meta['ordinal']}); correct-so-far {summary(rows)['correct']}/{len(rows)}",
                flush=True,
            )
        status, failure = "complete", None
    except Exception as exc:  # noqa: BLE001 - redact arbitrary errors
        status, failure = "failed", type(exc).__name__
    finally:
        for store in stores.values():
            await store.close()
    result = {
        "status": status,
        "rows": rows,
        "summary": summary(rows),
        "failure_class": failure,
        "stopped_case": current if failure else None,
        "stopped_stage": stage if failure else None,
        "usage": {k: v.report() for k, v in ledgers.items()},
    }
    for ledger in ledgers.values():
        ledger.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("prepare", "answers"), required=True)
    parser.add_argument("--preparation", type=Path)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("fresh output required")
    queue, groups, binding = load_inputs()
    preparation = (
        json.loads(args.preparation.read_bytes()) if args.preparation else None
    )
    if args.phase == "answers":
        if preparation is None:
            parser.error("completed zero-call preparation required")
        validate_fingerprint(preparation["plan"], "plan_fingerprint")
    elif preparation is not None:
        parser.error("prepare cannot accept a preparation")
    plan = make_plan(args.phase, queue, groups, binding, preparation)
    result = {"runner": RUNNER, "status": "ready", "plan": plan}
    if args.execute:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            parser.error("matching frozen preflight required")
        result.update(
            asyncio.run(
                prepare_run(args, queue, groups, plan)
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
