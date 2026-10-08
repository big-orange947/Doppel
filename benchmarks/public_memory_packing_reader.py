"""Same Reader over rank-fit contexts; bound reuse before at most five new calls."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.public_context_baseline import select_diagnostic_cases
from benchmarks.public_memory_answer_comparison import (
    AnswerRow,
    ProviderFactory,
    _default_provider_factory,
    _request_sha256,
    _StageExecutor,
)
from benchmarks.public_memory_expansion import answer_rows, config, save
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_packing import compare_packing
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_reader_v2 import (
    ReaderV2Output,
    build_request,
    structural_check,
)
from benchmarks.public_memory_recovery import cache_inventory, file_sha
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from doppel_memory.openai_compatible import OpenAICompatibleStructuredOutputConfig

RUNNER = "doppel.public-memory-packing-reader.v1"
CAP = 5


def fitted_rows(parent, packed, cases) -> tuple[list[AnswerRow], list[AnswerRow]]:
    if packed.get("status") != "complete" or packed["plan"]["max_provider_calls"] != 0:
        raise ValueError("complete zero-provider packing experiment required")
    paired = compare_packing(parent["retrieval"], packed["comparison"])
    if not paired["baseline_reproduced"] or not paired["baseline_contexts_preserved"]:
        raise ValueError("exact source-preserving paired baseline required")
    baseline = answer_rows(parent["retrieval"], cases)
    by_key = {(r["case_id"], r["profile"]): r for r in packed["comparison"]["rows"]}
    rows = []
    for old in baseline:
        fitted = by_key[(old.case_id, old.profile + "_ranked_fit")]
        rows.append(
            AnswerRow(
                old.index,
                old.case_id,
                old.profile,
                old.runtime,
                old.scoring,
                tuple(fitted["context"]),
            )
        )
    return baseline, rows


def build_plan(
    baseline: Sequence[AnswerRow],
    rows: Sequence[AnswerRow],
    parent: Mapping[str, Any],
    *,
    binding: Mapping[str, str],
    cache_inventory_sha256: str,
) -> dict[str, Any]:
    old = parent["answers"]["rows"]
    if (
        len(baseline) != 30
        or len(rows) != 30
        or len(old) != 30
        or (parent["plan"]["reader_config"] != config(2048).model_dump(mode="json"))
    ):
        raise ValueError("unchanged thirty-row Reader/configuration required")
    changed = []
    if len({(r.case_id, r.profile) for r in rows}) != 30:
        raise ValueError("distinct logical row identities required")
    for index, (before, after, previous) in enumerate(
        zip(baseline, rows, old, strict=True)
    ):
        identity = (before.index, before.case_id, before.profile)
        if (
            identity != (after.index, after.case_id, after.profile)
            or identity != (previous["index"], previous["case_id"], previous["profile"])
            or previous["reader"]["status"] != "completed"
            or (
                _request_sha256(build_request(before))
                != previous["reader"]["request_sha256"]
            )
        ):
            raise ValueError("exact original Reader request/output binding required")
        if type(after.index) is not int or after.index != index:
            raise ValueError("ordered contiguous row indices required")
        ReaderV2Output.model_validate(previous["reader"]["output"])
        if (
            _request_sha256(build_request(after))
            != previous["reader"]["request_sha256"]
        ):
            changed.append(after.index)
    if len(changed) > CAP:
        raise ValueError("at most five changed logical requests permitted")
    value = {
        "runner": RUNNER,
        "input_binding": dict(binding),
        "parent_cache_inventory_sha256": cache_inventory_sha256,
        "provider_config": parent["plan"]["reader_config"],
        "request_sha256s": [_request_sha256(build_request(r)) for r in rows],
        "baseline_request_sha256s": [
            _request_sha256(build_request(r)) for r in baseline
        ],
        "changed_row_indices": changed,
        "max_new_reader_calls": CAP,
        "max_new_judge_calls": 0,
        "logical_rows": 30,
        "source_sha256": {
            name: file_sha(Path(__file__).with_name(name))
            for name in (
                "public_memory_packing_reader.py",
                "public_memory_reader_v2.py",
                "public_memory_answer_comparison.py",
                "public_memory_runtime.py",
            )
        },
        "failure_policy": "validate-all-unchanged-cache-first; no-retry-or-rebilling",
        "quality_scope": "structural-and-behavior-diagnostic; no-automatic-QA-score",
    }
    return {**value, "plan_fingerprint": _hash(value)}


async def run_reader(
    baseline,
    rows,
    parent,
    plan,
    *,
    run_dir: Path,
    parent_cache: Path,
    api_key: str,
    cache_only: bool,
    provider_factory: ProviderFactory = _default_provider_factory,
):
    if (
        build_plan(
            baseline,
            rows,
            parent,
            binding=plan["input_binding"],
            cache_inventory_sha256=_hash(cache_inventory(parent_cache)),
        )
        != plan
    ):
        raise ValueError("frozen request/config/cache binding changed")
    if (
        run_dir.resolve() == parent_cache.resolve()
        or parent_cache.resolve() in run_dir.resolve().parents
    ):
        raise ValueError("run directory must not modify the read-only parent cache")
    _bind_json(run_dir / "plan.json", plan)
    ledger = DurableCallLedger(
        run_dir / "usage.sqlite3",
        budget_id=RUNNER + ":" + plan["plan_fingerprint"],
        max_calls=CAP,
    )
    before = ledger.report()["attempts_reserved"]
    if before and not cache_only:
        ledger.close()
        raise ValueError("attempted namespace may only replay cache-only")
    settings = OpenAICompatibleStructuredOutputConfig.model_validate(
        plan["provider_config"]
    )
    reports = {}
    stopped = None
    changed = set(plan["changed_row_indices"])
    try:
        # A missing/corrupt unchanged cache is not permission to spend a live call.
        stages = {}
        for name, only in (("reuse", True), ("changed", cache_only)):
            model = PilotStructuredModel(
                provider_factory(
                    settings, "" if only else api_key, ledger.observe_usage
                ),
                ledger=ledger,
                cache_dir=run_dir / "reader-cache",
                cache_only=only,
                read_only_cache_dirs=[parent_cache],
            )
            stages[name] = _StageExecutor(
                model, ledger, ReaderV2Output, cache_only=only
            )
        for row in [r for r in rows if r.index not in changed]:
            output, record = await stages["reuse"].execute(
                build_request(row), row.index
            )
            expected = ReaderV2Output.model_validate(
                parent["answers"]["rows"][row.index]["reader"]["output"]
            )
            reports[row.index] = (output, record)
            if output != expected:
                stopped = "unchanged-cache-missing-invalid-or-different"
                break
        if stopped is None:
            for row in [r for r in rows if r.index in changed]:
                output, record = await stages["changed"].execute(
                    build_request(row), row.index
                )
                reports[row.index] = (output, record)
        ordered = []
        for row in rows:
            output, record = reports.get(row.index, (None, {"status": "not_run"}))
            previous = parent["answers"]["rows"][row.index]["reader"]["output"]
            ordered.append(
                {
                    "index": row.index,
                    "case_id": row.case_id,
                    "profile": row.profile,
                    "context_changed": row.index in changed,
                    "reader": {
                        **record,
                        "output": output.model_dump(mode="json") if output else None,
                    },
                    "checks": structural_check(row, output) if output else None,
                    "baseline_reader": previous,
                    "answer_changed": output.answer != previous["answer"]
                    if output
                    else None,
                }
            )
        usage = ledger.report()
    finally:
        ledger.close()
    return {
        "runner": RUNNER,
        "status": "complete"
        if stopped is None
        and all(r["reader"]["status"] == "completed" for r in ordered)
        else "partial",
        "plan": plan,
        "stopped_reason": stopped,
        "new_reader_calls": usage["attempts_reserved"] - before,
        "new_judge_calls": 0,
        "usage_cumulative": usage,
        "rows": ordered,
        "structurally_valid_rows": sum(
            bool(r["checks"] and r["checks"]["structurally_valid"]) for r in ordered
        ),
        "answer_changed_rows": sum(r["answer_changed"] is True for r in ordered),
        "qa_metrics_available": False,
        "answer_correct": None,
        "retrieval_rerun": False,
        "store_writes": 0,
        "publication_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "dataset",
        "manifest",
        "parent-report",
        "packing-report",
        "parent-cache",
        "run-dir",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--frozen-plan", type=Path)
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("fresh output required; cache-only requires live")
    if args.parent_cache.resolve() in args.output.resolve().parents or (
        args.output.resolve()
        in {
            getattr(args, name).resolve()
            for name in ("dataset", "manifest", "parent_report", "packing_report")
        }
    ):
        parser.error("output must not overwrite or modify a parent input/cache")
    parent = json.loads(args.parent_report.read_text(encoding="utf-8"))
    packed = json.loads(args.packing_report.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    binding = {
        name: file_sha(path)
        for name, path in (
            ("dataset", args.dataset),
            ("manifest", args.manifest),
            ("parent_report", args.parent_report),
            ("packing_report", args.packing_report),
        )
    }
    if (
        packed["plan"]["input_sha256"]["parent_report"] != binding["parent_report"]
        or (binding["dataset"] != manifest["source_sha256"])
        or parent["plan"]["manifest_fingerprint"] != manifest["manifest_fingerprint"]
    ):
        parser.error("source/parent binding differs")
    cases = select_diagnostic_cases(
        json.loads(args.dataset.read_text(encoding="utf-8")),
        manifest,
        source_sha256=binding["dataset"],
    )
    baseline, rows = fitted_rows(parent, packed, cases)
    cache_sha = _hash(cache_inventory(args.parent_cache))
    plan = build_plan(
        baseline, rows, parent, binding=binding, cache_inventory_sha256=cache_sha
    )
    report = {
        "runner": RUNNER,
        "status": "preflight",
        "plan": plan,
        "new_reader_calls": 0,
        "new_judge_calls": 0,
        "qa_metrics_available": False,
    }
    if args.live:
        if (
            args.frozen_plan is None
            or json.loads(args.frozen_plan.read_text(encoding="utf-8"))["plan"] != plan
        ):
            parser.error("matching frozen preflight required")
        key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not key and not args.cache_only:
            parser.error("key environment variable is absent")
        report = asyncio.run(
            run_reader(
                baseline,
                rows,
                parent,
                plan,
                run_dir=args.run_dir,
                parent_cache=args.parent_cache,
                api_key=key,
                cache_only=args.cache_only,
            )
        )
    report["parent_cache_preserved"] = (
        _hash(cache_inventory(args.parent_cache)) == cache_sha
    )
    report["inputs_preserved"] = all(
        file_sha(path) == binding[name]
        for name, path in (
            ("dataset", args.dataset),
            ("manifest", args.manifest),
            ("parent_report", args.parent_report),
            ("packing_report", args.packing_report),
        )
    )
    save(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "new_reader_calls": report["new_reader_calls"],
                "changed_rows": plan["changed_row_indices"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return (
        0
        if report["status"] in {"complete", "preflight"}
        and report["parent_cache_preserved"]
        and report["inputs_preserved"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
