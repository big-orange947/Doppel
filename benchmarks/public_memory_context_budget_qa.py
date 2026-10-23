"""Frozen Reader/task-judge comparison of saved 24/48/96KB contexts, all opened50.

No retrieval, extraction, graph, DB, model-policy tuning or baseline rescoring.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from pathlib import Path

from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_answer_comparison import (
    AnswerRow,
    _default_provider_factory,
    _request_sha256,
    _StageExecutor,
)
from benchmarks.public_memory_context_budget import (
    BUDGETS,
    INPUTS,
    encode,
    pack,
    replay,
    sha,
)
from benchmarks.public_memory_expansion import config
from benchmarks.public_memory_fresh_cohort import validate_fingerprint
from benchmarks.public_memory_listwise_diagnostic import request_bytes
from benchmarks.public_memory_passage_diagnostic import reader_request
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_reader_v2 import ReaderV2Output, structural_check
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_task_accuracy import Grade
from benchmarks.public_memory_task_accuracy import request as task_request

ROOT = Path("data/doppel")
FILES = {
    "source": ROOT / "window-ablation-live-v1.json",
    "qa": ROOT / "uniform-qa-fifty-summary-v1.json",
    "curve": ROOT / "context-budget-curve-v1.json",
    "manifest": ROOT / "longmemeval-fresh-high-config-50-manifest-v1.json",
    "dataset": Path("data/public-benchmarks/longmemeval_s_cleaned.json"),
    "thirty": ROOT / "uniform-qa-11-40-prepare-live-v1.json",
    "twenty": ROOT / "uniform-qa-completion-prepare-live-v1.json",
}
CODE = (
    __file__,
    "benchmarks/public_memory_context_budget.py",
    "benchmarks/public_memory_passage_diagnostic.py",
    "benchmarks/public_memory_reader_v2.py",
    "benchmarks/public_memory_answer_comparison.py",
    "benchmarks/public_memory_task_accuracy.py",
    "benchmarks/public_memory_runtime.py",
    "benchmarks/public_memory_expansion.py",
    "benchmarks/public_longmemeval.py",
    "doppel_memory/openai_compatible.py",
)
STAGES = {"reader": (ReaderV2Output, 2048), "judge": (Grade, 1024)}
CALL_CAP = 58


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, allow_nan=False, indent=2)
        handle.write("\n")


def prepare():
    raw = {name: path.read_bytes() for name, path in FILES.items()}
    data = {name: json.loads(value) for name, value in raw.items()}
    binding = {name: sha(value) for name, value in raw.items()}
    source, qa, curve = data["source"], data["qa"], data["curve"]
    if (
        binding["source"] != INPUTS["window-ablation-live-v1.json"]
        or binding["qa"] != INPUTS["uniform-qa-fifty-summary-v1.json"]
        or binding["curve"]
        != "90dfb893ec72a8a821be2e86d39b4cf100f0bc1140f905949cb4f265d59d536b"
        or any(
            binding[key] != source["plan"]["binding"][key]
            for key in ("manifest", "dataset", "thirty", "twenty")
        )
        or replay(source) != {key: curve[key] for key in ("rows", "summary")}
    ):
        raise ValueError("frozen source/QA/budget-curve binding differs")
    validate_fingerprint(source["plan"], "plan_fingerprint")
    validate_fingerprint(data["manifest"], "manifest_fingerprint")
    for name in ("thirty", "twenty"):
        validate_fingerprint(data[name]["plan"], "plan_fingerprint")
        if any(
            data[name]["plan"]["stages"][stage]["config"]
            != config(tokens).model_dump(mode="json")
            for stage, (_, tokens) in STAGES.items()
        ):
            raise ValueError("same frozen Reader/judge provider configuration required")
    by_id = {row["question_id"]: row for row in data["dataset"]}
    old = {row["ordinal"]: row for row in qa["rows"]}
    cohort = {
        row["case_id"]
        for row in data["manifest"]["cases"]
        if row["partition"] == "diagnostic"
    }
    if len(cohort) != 50 or {row["case_id"] for row in source["rows"]} != cohort:
        raise ValueError("opened diagnostic cohort differs")
    queue = []
    for row in sorted(source["rows"], key=lambda r: r["ordinal"]):
        ordinal = row["ordinal"]
        previous = old[ordinal]
        case = prepare_case(
            by_id[row["case_id"]],
            dataset_namespace=data["manifest"]["dataset_namespace"],
        )
        for budget in BUDGETS:
            context, _ = pack(row["arms"]["80"]["top20"], budget)
            answer_row = AnswerRow(
                len(queue),
                row["case_id"],
                "fixed80-budget-only",
                case.runtime,
                case.scoring,
                tuple(context),
            )
            request = reader_request(answer_row)
            if request_bytes(request) > 100000:
                raise ValueError("Reader request exceeds frozen byte bound")
            if budget == 24000 and (
                row["case_id"] != previous["case_id"]
                or sha(encode(context)) != previous["context_sha256"]
                or _request_sha256(request) != previous["reader"]["request_sha256"]
                or previous["task_judge"]["request_sha256"]
                != _request_sha256(
                    task_request(
                        case.runtime.query.query,
                        case.scoring.answer,
                        previous["reader_output"]["answer"],
                    )
                )
            ):
                raise ValueError("original Reader/judge request identity differs")
            queue.append(
                {
                    "ordinal": ordinal,
                    "budget": budget,
                    "row": answer_row,
                    "request": request,
                    "baseline": previous,
                }
            )
    old_requests = {r["reader"]["request_sha256"] for r in qa["rows"]}
    new = {_request_sha256(item["request"]) for item in queue} - old_requests
    if len(new) != CALL_CAP:
        raise ValueError(
            "expected exactly58 new Reader requests before any provider call"
        )
    plan = {
        "runner": "doppel.context-budget-qa.v1",
        "input_sha256": binding,
        "code_sha256": {str(Path(path)): sha(Path(path).read_bytes()) for path in CODE},
        "implementation_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "candidate_window": 80,
        "budgets_utf8_json_bytes": list(BUDGETS),
        "contexts": [
            {
                "ordinal": item["ordinal"],
                "budget": item["budget"],
                "reader_request_sha256": _request_sha256(item["request"]),
                "request_bytes": request_bytes(item["request"]),
            }
            for item in queue
        ],
        "new_unique_reader_requests": len(new),
        "stages": {
            name: {
                "config": config(tokens).model_dump(mode="json"),
                "max_calls": CALL_CAP,
                "max_request_bytes": 100000,
                "max_total_request_bytes": CALL_CAP * 100000,
            }
            for name, (_, tokens) in STAGES.items()
        },
        "automatic_retries": 0,
        "order": "all50 ordinal order; within each case24/48/96; exact-request deduplication",
        "baseline_reuse": "immutable previous answers/grades; exact same question/reference/candidate reuses previous grade",
        "primary": "unchanged provisional DeepSeek task judge; paired positive/negative/type and structural checks; no official score",
        "source_writes": 0,
        "retrieval_calls": 0,
        "graph_calls": 0,
        "opened_development_not_blind": True,
        "publication_ready": False,
        "official_longmemeval_score": False,
        "aml_score": False,
    }
    return {**plan, "plan_fingerprint": _hash(plan)}, queue, raw


def seed_baseline(queue, reader, judge):
    for item in queue:
        if item["budget"] != 24000:
            continue
        old, row = item["baseline"], item["row"]
        output = ReaderV2Output.model_validate(old["reader_output"])
        for executor, request, parsed in (
            (reader, item["request"], output),
            (
                judge,
                task_request(
                    row.runtime.query.query, row.scoring.answer, output.answer
                ),
                Grade.model_validate(old["grade"]),
            ),
        ):
            digest = _request_sha256(request)
            if digest in executor.results and executor.results[digest][0] != parsed:
                raise ValueError("conflicting historical exact-request outputs")
            executor.results[digest] = (
                parsed,
                {
                    "status": "completed",
                    "request_sha256": digest,
                    "first_row": row.index,
                    "failure_class": None,
                    "origin": "frozen24KB-baseline",
                },
            )


def summary(rows):
    result = {}

    def score(values):
        completed = [row for row in values if row.get("grade") is not None]
        return {
            "expected": len(values),
            "completed": len(completed),
            "correct": sum(row["grade"]["answer_correct"] for row in completed),
            "accuracy": sum(row["grade"]["answer_correct"] for row in completed)
            / len(completed)
            if completed
            else None,
        }

    for budget in BUDGETS:
        values = [row for row in rows if row["budget"] == budget]
        result[str(budget)] = {
            **score(values),
            "answerable": score([row for row in values if not row["abstention_label"]]),
            "unanswerable": score([row for row in values if row["abstention_label"]]),
            "by_type": {
                kind: score([row for row in values if row["question_type"] == kind])
                for kind in sorted({row["question_type"] for row in values})
            },
            "structurally_valid": sum(
                row.get("checks", {}).get("structurally_valid", False) for row in values
            ),
            "all_case_context_bytes": sum(row["context_bytes"] for row in values),
        }
        baseline = {
            row["ordinal"]: row
            for row in rows
            if row["budget"] == 24000 and row.get("grade") is not None
        }
        paired = [
            (
                baseline[row["ordinal"]]["grade"]["answer_correct"],
                row["grade"]["answer_correct"],
            )
            for row in values
            if row.get("grade") is not None and row["ordinal"] in baseline
        ]
        result[str(budget)]["paired_vs_24000"] = {
            "paired": len(paired),
            "gains": sum(not a and b for a, b in paired),
            "losses": sum(a and not b for a, b in paired),
        }
    return result


async def run_rows(queue, reader, judge, checkpoint):
    seed_baseline(queue, reader, judge)
    rows = []
    for item in queue:
        row = item["row"]
        entry = {
            "ordinal": item["ordinal"],
            "case_id": row.case_id,
            "budget": item["budget"],
            "question_type": row.scoring.category,
            "abstention_label": row.scoring.abstention,
            "context_sha256": sha(encode(list(row.context))),
            "context_bytes": len(encode(list(row.context))),
        }
        output, record = await reader.execute(item["request"], row.index)
        entry.update(
            reader=record,
            reader_output=output.model_dump(mode="json") if output else None,
        )
        if output:
            grade, judged = await judge.execute(
                task_request(
                    row.runtime.query.query, row.scoring.answer, output.answer
                ),
                row.index,
            )
            entry.update(
                checks=structural_check(row, output),
                task_judge=judged,
                grade=grade.model_dump(mode="json") if grade else None,
            )
        rows.append(entry)
        checkpoint(entry)
        if not output or not entry.get("grade"):
            return rows, {
                "ordinal": item["ordinal"],
                "budget": item["budget"],
                "stage": "reader" if not output else "judge",
                "reason": "failed-request-preserved-no-retry",
            }
        if item["budget"] == 96000:
            print(
                f"completed {item['ordinal']}/50; correct by cap: "
                + "/".join(str(summary(rows)[str(b)]["correct"]) for b in BUDGETS),
                flush=True,
            )
    return rows, None


async def execute(args, plan, queue):
    if args.run_dir.exists():
        raise ValueError(
            "fresh run directory required; previous failed attempts must not be retried"
        )
    key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not args.cache_only and not key:
        raise ValueError("provider key absent")
    write_new(
        args.run_dir / "attempt.json", {"plan": plan, "cache_only": args.cache_only}
    )
    ledgers, models, executors = {}, {}, {}
    try:
        for name, (schema, tokens) in STAGES.items():
            limits = {
                key: plan["stages"][name][key]
                for key in ("max_calls", "max_request_bytes", "max_total_request_bytes")
            }
            ledger = DurableCallLedger(
                args.run_dir / "usage.sqlite3",
                budget_id=plan["plan_fingerprint"] + ":" + name,
                **limits,
            )
            ledgers[name] = ledger
            model = PilotStructuredModel(
                _default_provider_factory(
                    config(tokens),
                    key or "cache-only-no-credential",
                    ledger.observe_usage,
                ),
                ledger=ledger,
                cache_dir=args.run_dir / name,
                cache_only=args.cache_only,
                read_only_cache_dirs=[parent / name for parent in args.cache_parent],
            )
            models[name] = model
            executors[name] = _StageExecutor(
                model, ledger, schema, cache_only=args.cache_only
            )
        rows, failure = await run_rows(
            queue,
            executors["reader"],
            executors["judge"],
            lambda entry: write_new(
                args.run_dir / f"row-{entry['ordinal']:02d}-{entry['budget']}.json",
                entry,
            ),
        )
        return {
            "status": "complete" if failure is None else "failed",
            "rows": rows,
            "summary": summary(rows),
            "failure": failure,
            "usage": {name: model.report() for name, model in models.items()},
        }
    finally:
        for ledger in ledgers.values():
            ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--cache-parent", type=Path, action="append", default=[])
    args = parser.parse_args()
    if args.output.exists():
        parser.error("new output required")
    plan, queue, snapshots = prepare()
    result = {"plan": plan, "status": "ready"}
    if args.execute:
        if (
            not args.run_dir
            or not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            parser.error("matching frozen preflight and new run directory required")
        result.update(asyncio.run(execute(args, plan, queue)))
    for name, value in snapshots.items():
        if FILES[name].read_bytes() != value:
            raise ValueError("frozen input changed during run; checkpoints retained")
    write_new(args.output, result)
    print(f"output: {args.output.resolve()}", flush=True)
    print(f"sha256: {sha(args.output.read_bytes())}", flush=True)
    if "summary" in result:
        print(json.dumps(result["summary"], ensure_ascii=False), flush=True)
    raise SystemExit(0 if result["status"] in {"ready", "complete"} else 1)


if __name__ == "__main__":
    main()
