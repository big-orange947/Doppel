"""Paired response-policy diagnosis on frozen S/oracle contexts, not retrieval.

Only opened cases shared with the previous S diagnostic are selected. Within each
context, both policies receive identical data/schema/settings. No gold, public
category, profile or old answer enters either Reader request. No graph work.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_memory_answer_comparison import (
    _default_provider_factory,
    _request_sha256,
)
from benchmarks.public_memory_expansion import config, save
from benchmarks.public_memory_high_config_first import persisted_generation
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_oracle_diagnostic import balance, prepare_rows
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_reader_v2 import (
    INSTRUCTIONS,
    ReaderV2Output,
    build_request,
    structural_check,
)
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_task_accuracy import Grade
from benchmarks.public_memory_task_accuracy import request as grade_request

RUNNER = "doppel.public-memory-response-policy-paired.v1"
POLICIES = ("reader_v2", "grounded_advice_v1")
ADVICE_INSTRUCTIONS = (
    INSTRUCTIONS.replace(
        "using only\nthe supplied context items.",
        "grounding personal-history claims in the supplied context items.",
    )
    + """

Distinguish recalling personal history from generating new assistance. Determine
which the question requests from its wording, not from a benchmark category.
For recall, require supplied evidence; never use general knowledge to invent a
personal fact, prior recommendation, event, relationship or preference.
For a request for new advice, suggestions or a plan, use the supplied preferences
and constraints as premises and generate useful new advice with general knowledge.
You need not find that exact recommendation already recorded in history. Clearly
present new advice as a proposal, not something the user or assistant previously
said or did. Cite the items supporting remembered preferences and constraints;
do not claim those citations establish the proposed recommendation as history.
If a necessary personal premise is unknown, qualify it or ask for clarification;
do not manufacture that premise. A factual recall question must not be answered
by substituting a suggestion. Keep source authority and temporal rules unchanged.
"""
)


def reader_request(row, policy):
    if policy not in POLICIES:
        raise ValueError("unknown response policy")
    request = build_request(row)
    if policy == POLICIES[1]:
        request = request.model_copy(update={"instructions": ADVICE_INSTRUCTIONS})
    return request


def paired_rows(oracle_rows, comparison, quality, bindings):
    """Only shared opened cases, exact old S request hashes, never score selection."""
    parent = quality["plan"]
    payload = dict(parent)
    fingerprint = payload.pop("plan_fingerprint", None)
    if (
        quality.get("status") != "complete"
        or quality.get("runner") != "doppel.public-memory-quality-50.v1"
        or fingerprint != _hash(payload)
        or parent["input_sha256"]["comparison"] != bindings["comparison"]
        or parent["input_sha256"]["dataset"] != bindings["source"]
        or parent["input_sha256"]["manifest"] != bindings["manifest"]
        or comparison.get("status") != "complete"
        or comparison.get("record_or_index_writes") != 0
        or not comparison.get("corpus_sha256_before")
        or comparison["corpus_sha256_before"] != comparison["corpus_sha256_after"]
    ):
        raise ValueError("unchanged S parent binding required")
    old = {}
    for batch, frozen in zip(quality["batches"], parent["batch_rows"], strict=True):
        for row, identity, sha in zip(
            batch["rows"], frozen["identities"], frozen["reader_requests"], strict=True
        ):
            if [row["index"], row["case_id"], row["profile"]] != identity:
                raise ValueError("old row identity changed")
            if row["reader"]["request_sha256"] != sha:
                raise ValueError("old request binding changed")
            key = (row["case_id"], row["profile"])
            if key in old:
                raise ValueError("duplicate old row")
            old[key] = sha
    contexts = {}
    for row in comparison["rows"]:
        key = (row["case_id"], row["profile"])
        if key in contexts:
            raise ValueError("duplicate comparison row")
        contexts[key] = row["context"]
    result = []
    for oracle in oracle_rows:
        key = (oracle.case_id, "raw_vector_reranked")
        if key not in old:
            continue  # newer oracle-only refusal has no frozen S arm
        context = contexts[key]
        if len({i["memory_id"] for i in context}) != len(context):
            raise ValueError("duplicate S context ids")
        raw = replace(oracle, context=tuple(context), profile="s-raw-vector-reranked")
        if _request_sha256(build_request(raw)) != old[key]:
            raise ValueError("S context/question/clock changed")
        result.extend(
            [replace(raw, index=len(result)), replace(oracle, index=len(result) + 1)]
        )
    if len(result) != 14 or len({r.case_id for r in result}) != 7:
        raise ValueError("seven fixed shared cases required")
    return result


def build_plan(rows, bindings):
    identities = [[r.case_id, r.profile] for r in rows]
    if len(set(map(tuple, identities))) != len(identities):
        raise ValueError("duplicate paired context")
    requests = [reader_request(r, p) for r in rows for p in POLICIES]
    sizes = [len(r.model_dump_json().encode()) for r in requests]
    if any(n > 100_000 for n in sizes):
        raise ValueError("request exceeds bound; no truncation or silent skipping")
    paths = [
        Path(__file__),
        Path("benchmarks/public_memory_oracle_diagnostic.py"),
        Path("benchmarks/public_memory_reader_v2.py"),
        Path("benchmarks/public_memory_answer_comparison.py"),
        Path("benchmarks/public_memory_runtime.py"),
        Path("benchmarks/public_memory_task_accuracy.py"),
        Path("benchmarks/public_longmemeval.py"),
        Path("benchmarks/public_memory_high_config_first.py"),
        Path("benchmarks/public_memory_expansion.py"),
    ]
    plan = {
        "runner": RUNNER,
        "input_sha256": bindings,
        "contexts": identities,
        "policies": list(POLICIES),
        "reader_request_sha256": [_request_sha256(r) for r in requests],
        "reader_request_bytes": sizes,
        "configs": {
            s: config(n).model_dump(mode="json")
            for s, n in (("reader", 2048), ("judge", 1024))
        },
        "max_new_calls": 4 * len(rows),
        "max_calls_per_stage": 2 * len(rows),
        "selection": "previous-first-opened-per-type-plus-first-abs-shared-with-frozen-S; no-score-selection",
        "balance_stop_cny": 1,
        "hard_currency_cap": False,
        "failure_policy": "single-attempt; stop; preserve failures; no repair/resample",
        "source_sha256": {
            str(p).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths
        },
        "reader_gold_or_categories": False,
        "new_graph_miner_retrieval_gpu_calls": 0,
        "cross_context_comparison": "diagnostic only; oracle is label-selected, unequal context budget; not retrieval ablation",
        "within_context_comparison": "identical inputs/schema/settings, alternating policy order per context",
        "judge": "unchanged DeepSeek meaning-only diagnostic, not official judge or support validation",
        "publication_ready": False,
        "aml_academic_model_compliant": False,
    }
    return {**plan, "plan_fingerprint": _hash(plan)}


async def execute(
    args,
    rows,
    plan,
    *,
    provider_factory=_default_provider_factory,
    balance_reader=balance,
):
    _bind_json(args.run_dir / "plan.json", plan)
    key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key and not args.cache_only:
        raise ValueError("key environment absent")
    initial = None if args.cache_only else await balance_reader(key)
    if not args.cache_only:
        _bind_json(args.run_dir / "balance-start.json", {"initial_cny": initial})
    models, ledgers, results = {}, {}, []
    last_balance, stopped = initial, ""
    try:
        for stage, tokens in (("reader", 2048), ("judge", 1024)):
            ledger = DurableCallLedger(
                args.run_dir / (stage + ".sqlite3"),
                budget_id=plan["plan_fingerprint"] + ":" + stage,
                max_calls=plan["max_calls_per_stage"],
                max_request_bytes=100_000,
                max_total_request_bytes=100_000 * plan["max_calls_per_stage"],
            )
            ledgers[stage] = ledger
            models[stage] = PilotStructuredModel(
                provider_factory(config(tokens), key, ledger.observe_usage),
                ledger=ledger,
                cache_dir=args.run_dir / stage,
                cache_only=args.cache_only,
            )
        for index, row in enumerate(rows):
            for policy in POLICIES if index % 2 == 0 else POLICIES[::-1]:
                item = {
                    "case_id": row.case_id,
                    "context_profile": row.profile,
                    "policy": policy,
                    "abstention_case": row.scoring.abstention,
                    "category": row.scoring.category,
                    "status": "failed",
                }
                directory = args.run_dir / f"context-{index:02d}-{policy}"
                directory.mkdir(exist_ok=True)
                try:
                    for stage in ("reader", "judge"):
                        if not args.cache_only:
                            last_balance = await balance_reader(key)
                            if (
                                initial - last_balance >= plan["balance_stop_cny"]
                                or last_balance <= 0
                            ):
                                stopped = "balance_budget_reached"
                                item["status"] = "budget_stopped"
                                break
                        if stage == "reader":
                            reader = await persisted_generation(
                                models[stage],
                                reader_request(row, policy),
                                ReaderV2Output,
                                directory / "reader.json",
                            )
                            item.update(
                                reader=reader.model_dump(mode="json"),
                                checks=structural_check(row, reader),
                            )
                        else:
                            grade = await persisted_generation(
                                models[stage],
                                grade_request(
                                    row.runtime.query.query,
                                    row.scoring.answer,
                                    reader.answer,
                                ),
                                Grade,
                                directory / "judge.json",
                            )
                            item.update(
                                grade=grade.model_dump(mode="json"), status="complete"
                            )
                except Exception as error:  # noqa: BLE001 - never persist exception details
                    item["failure_type"] = type(error).__name__
                    stopped = "stage_or_balance_failure_no_retry"
                results.append(item)
                print(
                    f"{row.case_id} {row.profile} {policy}: {item['status']}",
                    flush=True,
                )
                if stopped:
                    break
            if stopped:
                break
        if not args.cache_only:
            try:
                last_balance = await balance_reader(key)
            except Exception:  # noqa: BLE001 - no provider/key exception text
                last_balance = None
        return {
            "status": "complete"
            if len(results) == 2 * len(rows)
            and all(r["status"] == "complete" for r in results)
            else "stopped",
            "rows": results,
            "stopped_reason": stopped,
            "usage": {k: m.report() for k, m in models.items()},
            "balance_observation": {
                "initial_cny": initial,
                "final_cny": last_balance,
                "delta_cny": None
                if initial is None or last_balance is None
                else initial - last_balance,
                "exclusive_billing_attribution_proven": False,
            },
        }
    finally:
        for ledger in ledgers.values():
            ledger.close()


async def run(args):
    paths = {
        k: getattr(args, k)
        for k in ("source", "oracle", "manifest", "comparison", "quality")
    }
    contents = {k: p.read_bytes() for k, p in paths.items()}
    bindings = {k: hashlib.sha256(v).hexdigest() for k, v in contents.items()}
    data = {k: json.loads(v) for k, v in contents.items()}
    if data["manifest"]["source_sha256"] != bindings["source"]:
        raise ValueError("S source mismatch")
    protected = set()
    for path in args.prior_manifest:
        content = path.read_bytes()
        prior = json.loads(content)
        if prior["source_sha256"] != bindings["source"]:
            raise ValueError("reserved source mismatch")
        bindings[str(path)] = hashlib.sha256(content).hexdigest()
        protected.update(
            r["case_id"] for r in prior["cases"] if r["partition"] == "reserved"
        )
    oracle_rows = prepare_rows(
        data["source"], data["oracle"], data["manifest"], protected
    )
    rows = paired_rows(oracle_rows, data["comparison"], data["quality"], bindings)
    plan = build_plan(rows, bindings)
    report = {
        "runner": RUNNER,
        "plan": plan,
        "status": "ready",
        "record_or_index_writes": 0,
        "publication_ready": False,
        "retrieval_rerun": False,
        "official_longmemeval_metric": False,
        "reserved_histories_executed": False,
    }
    if args.live:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_text(encoding="utf-8"))["plan"]
            != plan
        ):
            raise ValueError("unchanged committed preflight required")
        report.update(await execute(args, rows, plan))
    report["execution_metadata"] = execution_metadata()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "source",
        "oracle",
        "manifest",
        "comparison",
        "quality",
        "run-dir",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--prior-manifest", type=Path, action="append", required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("preserve existing outputs; cache-only requires live")
    report = asyncio.run(run(args))
    save(args.output, report)
    print(
        json.dumps(
            {"status": report["status"], "contexts": len(report["plan"]["contexts"])}
        )
    )
    return 0 if report["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
