"""Final fixed50 BGE/fusion QA selection; no more opened-cohort ranking sweeps."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from pathlib import Path

from benchmarks import public_memory_context_budget_qa as shared
from benchmarks.public_memory_answer_comparison import (
    AnswerRow,
    _default_provider_factory,
    _request_sha256,
    _StageExecutor,
)
from benchmarks.public_memory_context_budget import encode, sha
from benchmarks.public_memory_expansion import config
from benchmarks.public_memory_fresh_cohort import validate_fingerprint
from benchmarks.public_memory_passage_diagnostic import reader_request
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_reader_v2 import structural_check
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_task_accuracy import request as task_request

SOURCE = Path("data/doppel/rank-fusion-local-v1.json")
SOURCE_SHA = "6e6b8c911ace18b75fe8a0d64efa9c9af8f304d8af0a8a625cb3600bf7c85208"
ARMS = ("bge", "fusion")
MIN_NET_GAIN = 3


def prepare():
    parent, original, snapshots = shared.prepare()
    raw = SOURCE.read_bytes()
    if sha(raw) != SOURCE_SHA:
        raise ValueError("fixed local fusion report changed")
    source = json.loads(raw)
    validate_fingerprint(source["plan"], "plan_fingerprint")
    if (
        source["status"] != "complete"
        or source["failure"] is not None
        or len(source["rows"]) != 50
    ):
        raise ValueError("complete frozen local50 required")
    candidates = {row["ordinal"]: row for row in source["rows"]}
    queue = []
    for item in original:
        if item["budget"] != 24000:
            continue
        old, base = candidates[item["ordinal"]], item["row"]
        if (
            old["case_id"] != base.case_id
            or list(base.context) != old["arms"]["cross_encoder"]["context"]
        ):
            raise ValueError("unchanged BGE baseline context required")
        for arm in ARMS:
            context = (
                list(base.context)
                if arm == "bge"
                else old["arms"]["rank_fusion"]["context"]
            )
            if len(encode(context)) > 24000 or len(context) > 20:
                raise ValueError("fixed context cap exceeded")
            row = AnswerRow(
                len(queue),
                base.case_id,
                arm,
                base.runtime,
                base.scoring,
                tuple(context),
            )
            queue.append(
                {**item, "arm": arm, "row": row, "request": reader_request(row)}
            )
    hashes = {_request_sha256(item["request"]) for item in queue}
    old_hashes = {
        _request_sha256(item["request"]) for item in queue if item["arm"] == "bge"
    }
    plan = {
        "runner": "doppel.rank-fusion-qa-final.v1",
        "input_sha256": {**parent["input_sha256"], "fusion_source": SOURCE_SHA},
        "code_sha256": {
            **parent["code_sha256"],
            __file__: sha(Path(__file__).read_bytes()),
            "benchmarks/public_memory_context_budget_qa.py": sha(
                Path(shared.__file__).read_bytes()
            ),
        },
        "implementation_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "arms": list(ARMS),
        "candidate_limit": 80,
        "source_limit": 20,
        "context_bytes": 24000,
        "rrf_k": 60,
        "weights": "equal; no sweep",
        "max_new_unique_reader_requests": len(hashes - old_hashes),
        "requests": [
            {
                "ordinal": i["ordinal"],
                "arm": i["arm"],
                "sha256": _request_sha256(i["request"]),
            }
            for i in queue
        ],
        "stages": {
            name: {**limits, "max_calls": 50, "max_total_request_bytes": 5000000}
            for name, limits in parent["stages"].items()
        },
        "minimum_net_gain_to_select_fusion": MIN_NET_GAIN,
        "decision": "all100 rows complete; fusion net gain>=3, negatives and structural validity not worse; otherwise bge; no retuning",
        "automatic_retries": 0,
        "baseline_rescored": False,
        "scope": "same opened50; no reserved preparation until configuration selected",
        "publication_ready": False,
        "official_longmemeval_score": False,
        "aml_score": False,
        "retrieval_calls": 0,
        "source_writes": 0,
        "graph_calls": 0,
    }
    if len(queue) != 100 or len(hashes - old_hashes) > 50:
        raise ValueError("exact100 rows and bounded new requests required")
    return (
        {**plan, "plan_fingerprint": _hash(plan)},
        queue,
        {**snapshots, "fusion_source": raw},
    )


def summarize(rows):
    def score(values):
        completed = [r for r in values if r.get("grade") is not None]
        return {
            "completed": len(completed),
            "correct": sum(r["grade"]["answer_correct"] for r in completed),
            "accuracy": sum(r["grade"]["answer_correct"] for r in completed)
            / len(completed)
            if completed
            else None,
        }

    result = {}
    for arm in ARMS:
        values = [r for r in rows if r["arm"] == arm]
        result[arm] = {
            "expected": 50,
            **score(values),
            "answerable": score([r for r in values if not r["abstention_label"]]),
            "unanswerable": score([r for r in values if r["abstention_label"]]),
            "positive_by_type": {
                kind: score(
                    [
                        r
                        for r in values
                        if not r["abstention_label"] and r["question_type"] == kind
                    ]
                )
                for kind in sorted({r["question_type"] for r in values})
            },
            "structurally_valid": sum(
                r.get("checks", {}).get("structurally_valid", False) for r in values
            ),
            "context_bytes": sum(r["context_bytes"] for r in values),
        }
    baseline = {
        r["ordinal"]: r
        for r in rows
        if r["arm"] == "bge" and r.get("grade") is not None
    }
    pairs = [
        (
            baseline[r["ordinal"]]["grade"]["answer_correct"],
            r["grade"]["answer_correct"],
        )
        for r in rows
        if r["arm"] == "fusion"
        and r.get("grade") is not None
        and r["ordinal"] in baseline
    ]
    result["paired"] = {
        "count": len(pairs),
        "gains": sum(not a and b for a, b in pairs),
        "losses": sum(a and not b for a, b in pairs),
    }
    complete = all(result[arm]["completed"] == 50 for arm in ARMS) and len(pairs) == 50
    eligible = (
        complete
        and result["fusion"]["correct"] - result["bge"]["correct"] >= MIN_NET_GAIN
        and result["fusion"]["unanswerable"]["correct"]
        >= result["bge"]["unanswerable"]["correct"]
        and result["fusion"]["structurally_valid"]
        >= result["bge"]["structurally_valid"]
    )
    result["selection"] = {
        "complete": complete,
        "profile": ("fusion" if eligible else "bge") if complete else None,
        "engineering_threshold_not_significance_test": True,
    }
    return result


async def run_rows(queue, reader, judge, checkpoint):
    shared.seed_baseline(
        [item for item in queue if item["arm"] == "bge"], reader, judge
    )
    rows = []
    for item in queue:
        row = item["row"]
        entry = {
            "ordinal": item["ordinal"],
            "case_id": row.case_id,
            "arm": item["arm"],
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
                "arm": item["arm"],
                "reason": "failed-request-preserved-no-retry",
            }
        if item["arm"] == "fusion":
            current = summarize(rows)
            print(
                f"completed {item['ordinal']}/50; BGE {current['bge']['correct']} fusion {current['fusion']['correct']}",
                flush=True,
            )
    return rows, None


async def execute(args, plan, queue):
    if args.run_dir.exists():
        raise ValueError("new run directory required; no retry")
    key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not args.cache_only and not key:
        raise ValueError("provider key absent")
    shared.write_new(
        args.run_dir / "attempt.json", {"plan": plan, "cache_only": args.cache_only}
    )
    ledgers, models, executors = {}, {}, {}
    try:
        for name, (schema, tokens) in shared.STAGES.items():
            limits = {
                k: plan["stages"][name][k]
                for k in ("max_calls", "max_request_bytes", "max_total_request_bytes")
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
                read_only_cache_dirs=[p / name for p in args.cache_parent],
            )
            models[name] = model
            executors[name] = _StageExecutor(
                model, ledger, schema, cache_only=args.cache_only
            )
        rows, failure = await run_rows(
            queue,
            executors["reader"],
            executors["judge"],
            lambda entry: shared.write_new(
                args.run_dir / f"row-{entry['ordinal']:02d}-{entry['arm']}.json", entry
            ),
        )
        return {
            "status": "complete" if failure is None else "failed",
            "rows": rows,
            "summary": summarize(rows),
            "failure": failure,
            "usage": {name: model.report() for name, model in models.items()},
        }
    finally:
        for ledger in ledgers.values():
            ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--cache-parent", type=Path, action="append", default=[])
    args = parser.parse_args()
    if args.output.exists():
        parser.error("fresh output required")
    plan, queue, snapshots = prepare()
    result = {"plan": plan, "status": "ready"}
    if args.execute:
        if (
            not args.run_dir
            or not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            parser.error("matching preflight and new run directory required")
        result.update(asyncio.run(execute(args, plan, queue)))
    for name, raw in snapshots.items():
        path = SOURCE if name == "fusion_source" else shared.FILES[name]
        if path.read_bytes() != raw:
            raise ValueError("input changed; checkpoints retained")
    shared.write_new(args.output, result)
    print(
        f"output: {args.output.resolve()}\nsha256: {sha(args.output.read_bytes())}",
        flush=True,
    )
    if "summary" in result:
        print(json.dumps(result["summary"], ensure_ascii=False), flush=True)
    raise SystemExit(0 if result["status"] in {"ready", "complete"} else 1)


if __name__ == "__main__":
    main()
