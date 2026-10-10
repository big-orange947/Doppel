"""Small, cost-bounded full-oracle Reader diagnostic, not a retrieval score.

Select from already-opened S histories using public category/order only. Pair
questions by ID, keep timestamps/roles, strip all labels from Reader requests.
No miner, graph, planner, embedding, reranker or database writes. DeepSeek judge
is explicitly diagnostic, not the official GPT-4o metric or an AML score.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx

from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_answer_comparison import (
    AnswerRow,
    _default_provider_factory,
)
from benchmarks.public_memory_expansion import config, save
from benchmarks.public_memory_high_config_first import persisted_generation
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_reader_v2 import (
    ReaderV2Output,
    build_request,
    structural_check,
)
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_task_accuracy import Grade
from benchmarks.public_memory_task_accuracy import request as grade_request

RUNNER = "doppel.public-memory-full-oracle-cost-diagnostic.v1"
CATEGORIES = (
    "single-session-user",
    "multi-session",
    "single-session-preference",
    "temporal-reasoning",
    "knowledge-update",
    "single-session-assistant",
)


def select_ids(source, manifest, protected_ids=()):
    by_id = {r["question_id"]: r for r in source}
    if len(by_id) != len(source):
        raise ValueError("duplicate source case")
    opened = [r["case_id"] for r in manifest["cases"] if r["partition"] == "diagnostic"]
    chosen = []
    for category in CATEGORIES:
        eligible = [
            i
            for i in opened
            if by_id[i]["question_type"] == category and not i.endswith("_abs")
        ]
        if not eligible:
            raise ValueError("opened cohort missing public category")
        chosen.append(eligible[0])
    refusals = [i for i in opened if i.endswith("_abs")]
    blocked = set(protected_ids) | {
        r["case_id"] for r in manifest["cases"] if r["partition"] == "reserved"
    }
    for item in source:
        identity = item["question_id"]
        if (
            identity.endswith("_abs")
            and identity not in refusals
            and identity not in blocked
        ):
            refusals.append(identity)
        if len(refusals) >= 2:
            break
    if len(refusals) < 2:
        raise ValueError("two non-reserved abstention controls required")
    return chosen + refusals[:2]


def matched_oracle(s, o):
    """Oracle projection of this exact S snapshot, never mix source clocks.

    Oracle selection is intentionally label-aware DATA PREPARATION. Labels are
    removed before the Reader and never used by a retrieval/planner algorithm.
    For refusal controls use official oracle session IDs, not empty context.
    """
    selected = s["answer_session_ids"]
    if s["question_id"].endswith("_abs"):
        selected = o["haystack_session_ids"]
    if not selected:
        raise ValueError(
            "oracle projection requires nonempty evidence/control sessions"
        )
    rows = list(
        zip(
            s["haystack_session_ids"],
            s["haystack_dates"],
            s["haystack_sessions"],
            strict=True,
        )
    )
    chosen = [r for r in rows if r[0] in selected]
    if {r[0] for r in chosen} != set(selected):
        raise ValueError("oracle source IDs not present in S snapshot")
    projected = deepcopy(s)
    projected["haystack_session_ids"] = [r[0] for r in chosen]
    projected["haystack_dates"] = [r[1] for r in chosen]
    projected["haystack_sessions"] = [r[2] for r in chosen]
    return projected


def prepare_rows(source, oracle, manifest, protected_ids=()):
    ids = select_ids(source, manifest, protected_ids)
    s_map = {r["question_id"]: r for r in source}
    o_map = {r["question_id"]: r for r in oracle}
    if len(o_map) != len(oracle):
        raise ValueError("duplicate oracle case")
    rows = []
    for index, identity in enumerate(ids):
        s, o = s_map[identity], o_map[identity]
        projected = matched_oracle(s, o)
        prepared = prepare_case(
            projected, dataset_namespace="full-oracle-cost-diagnostic-v1"
        )
        context = []
        # Date order only, stable on equal timestamps; original source identity kept.
        sessions = sorted(prepared.runtime.sessions, key=lambda x: x.turns[0].at)
        for session in sessions:
            for turn in session.turns:
                if not turn.content.strip():
                    continue
                item_id = "oracle-" + _hash(
                    [
                        identity,
                        turn.source_session_id,
                        turn.turn_index,
                        turn.at.isoformat(),
                        turn.role,
                        turn.content,
                    ]
                )
                context.append(
                    {
                        "memory_id": item_id,
                        "channel": "raw",
                        "role": turn.role,
                        "authority": "human_self"
                        if turn.role == "user"
                        else "agent_output",
                        "text": turn.content,
                        "observed_at": turn.at.isoformat(),
                        "temporal_status": None,
                        "valid_from": None,
                        "valid_to": None,
                    }
                )
        if len({i["memory_id"] for i in context}) != len(context):
            raise ValueError("oracle message identity collision")
        rows.append(
            AnswerRow(
                index,
                identity,
                "full-oracle-no-retrieval",
                prepared.runtime,
                prepared.scoring,
                tuple(context),
            )
        )
    return rows


def build_plan(rows, bindings):
    stages = {"reader": config(2048), "judge": config(1024)}
    request_bytes = [
        len(
            json.dumps(
                build_request(r).model_dump(mode="json"), ensure_ascii=False
            ).encode()
        )
        for r in rows
    ]
    if any(n > 100_000 for n in request_bytes):
        raise ValueError(
            "full oracle request exceeds bound; do not truncate or skip silently"
        )
    files = [
        Path(__file__),
        Path("benchmarks/public_memory_reader_v2.py"),
        Path("benchmarks/public_memory_answer_comparison.py"),
        Path("benchmarks/public_memory_runtime.py"),
        Path("benchmarks/public_memory_task_accuracy.py"),
        Path("benchmarks/public_longmemeval.py"),
    ]
    plan = {
        "runner": RUNNER,
        "binding": bindings,
        "selection": "first-opened-per-public-type-plus-opened-abs-then-source-order-nonreserved-abs-no-score-selection",
        "case_ids": [r.case_id for r in rows],
        "categories": [r.scoring.category for r in rows],
        "reader_requests": [
            _hash(build_request(r).model_dump(mode="json")) for r in rows
        ],
        "reader_request_bytes": request_bytes,
        "context_items": [len(r.context) for r in rows],
        "stages": {k: v.model_dump(mode="json") for k, v in stages.items()},
        "max_calls_per_stage": len(rows),
        "max_new_calls": 2 * len(rows),
        "balance_stop_cny": 1,
        "balance_check": "before-every-new-stage-no-call-if-check-fails",
        "balance_stop_is_post_spend_not_hard_per_request_cap": True,
        "context_policy": "S-derived-oracle-evidence-sessions-with-S-clock-text-timestamp-order-no-truncation",
        "oracle_projection_uses_labels_for_data_preparation_only": True,
        "new_graph_or_miner_calls": 0,
        "publication_ready": False,
        "official_longmemeval_metric": False,
        "aml_academic_model_compliant": False,
        "model_alias_note": "official docs report legacy deepseek-v4-flash served by V4.1-Flash; not a pinned historical version",
        "source_sha256": {
            str(p).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files
        },
    }
    return {**plan, "plan_fingerprint": _hash(plan)}


async def balance(key):
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            "https://api.deepseek.com/user/balance",
            headers={"Authorization": "Bearer " + key},
        )
        response.raise_for_status()
        values = response.json()["balance_infos"]
    matching = [r for r in values if r["currency"] == "CNY"]
    if len(matching) != 1:
        raise ValueError("CNY balance unavailable")
    return float(matching[0]["total_balance"])


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
    baseline_path = args.run_dir / "balance-start.json"
    if not args.cache_only:
        _bind_json(baseline_path, {"initial_cny": initial})
    ledgers, models, results = {}, {}, []
    stopped = ""
    last_balance = initial
    try:
        for stage in ("reader", "judge"):
            ledger = DurableCallLedger(
                args.run_dir / (stage + ".sqlite3"),
                budget_id=plan["plan_fingerprint"] + ":" + stage,
                max_calls=len(rows),
                max_request_bytes=100_000,
                max_total_request_bytes=100_000 * len(rows),
            )
            ledgers[stage] = ledger
            models[stage] = PilotStructuredModel(
                provider_factory(
                    config(2048 if stage == "reader" else 1024),
                    key,
                    ledger.observe_usage,
                ),
                ledger=ledger,
                cache_dir=args.run_dir / stage,
                cache_only=args.cache_only,
            )
        for row in rows:
            item: dict[str, Any] = {
                "case_id": row.case_id,
                "category": row.scoring.category,
                "abstention_case": row.scoring.abstention,
                "status": "failed",
            }
            case_dir = args.run_dir / row.case_id
            case_dir.mkdir(exist_ok=True)
            try:
                for stage in ("reader", "judge"):
                    if not args.cache_only:
                        last_balance = await balance_reader(key)
                        if (
                            initial - last_balance >= plan["balance_stop_cny"]
                            or last_balance <= 0
                        ):
                            stopped = "balance_budget_reached"
                            break
                    if stage == "reader":
                        reader = await persisted_generation(
                            models[stage],
                            build_request(row),
                            ReaderV2Output,
                            case_dir / "reader.json",
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
                            case_dir / "judge.json",
                        )
                        item.update(
                            grade=grade.model_dump(mode="json"), status="complete"
                        )
                if stopped:
                    item["status"] = "budget_stopped"
            except Exception as error:  # noqa: BLE001 - redact provider/balance exceptions
                item["failure_type"] = type(error).__name__
                stopped = "stage_or_balance_failure_no_retry"
            results.append(item)
            print(f"{row.case_id}: {item['status']}", flush=True)
            if stopped:
                break
        if not args.cache_only:
            try:
                last_balance = await balance_reader(key)
            except Exception:  # noqa: BLE001 - balance availability, no credential text
                last_balance = None
        complete = len(results) == len(rows) and all(
            r["status"] == "complete" for r in results
        )
        return {
            "status": "complete" if complete else "stopped",
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
    paths = {k: getattr(args, k) for k in ("source", "oracle", "manifest")}
    data = {k: p.read_bytes() for k, p in paths.items()}
    bindings = {k: hashlib.sha256(v).hexdigest() for k, v in data.items()}
    source, oracle, manifest = (
        json.loads(data[k]) for k in ("source", "oracle", "manifest")
    )
    if manifest["source_sha256"] != bindings["source"]:
        raise ValueError("opened S manifest source mismatch")
    protected = set()
    for path in args.prior_manifest:
        payload = path.read_bytes()
        previous = json.loads(payload)
        if previous["source_sha256"] != bindings["source"]:
            raise ValueError("prior reserved source mismatch")
        bindings[str(path)] = hashlib.sha256(payload).hexdigest()
        protected.update(
            r["case_id"] for r in previous["cases"] if r["partition"] == "reserved"
        )
    rows = prepare_rows(source, oracle, manifest, protected)
    plan = build_plan(rows, bindings)
    report = {
        "runner": RUNNER,
        "status": "ready",
        "plan": plan,
        "publication_ready": False,
        "official_longmemeval_metric": False,
        "record_or_index_writes": 0,
        "reserved_histories_executed": False,
    }
    by_s, by_o = (
        {r["question_id"]: r for r in dataset} for dataset in (source, oracle)
    )
    report["official_oracle_pair_audit"] = {
        i: [
            k
            for k in ("question", "question_type", "question_date", "answer")
            if by_s[i][k] != by_o[i][k]
        ]
        for i in plan["case_ids"]
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
    for name in ("source", "oracle", "manifest", "run-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--prior-manifest", type=Path, action="append", required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("preserve artifacts; cache-only requires live")
    report = asyncio.run(run(args))
    save(args.output, report)
    print(
        json.dumps(
            {"status": report["status"], "case_count": len(report["plan"]["case_ids"])}
        )
    )
    return 0 if report["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
