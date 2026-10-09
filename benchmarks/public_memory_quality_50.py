"""Frozen fifty-question Reader/primary-Judge diagnostic on packed contexts.

Reuse the established thirty-row answer runner in five fixed ten-question batches.
No ingestion, retrieval, context expansion or database access occurs here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.public_context_baseline import (
    execution_metadata,
    select_diagnostic_cases,
)
from benchmarks.public_longmemeval import RuntimeCase, ScoringCase
from benchmarks.public_memory_answer_comparison import (
    COMPARISON_RUNNER,
    PROFILE_NAMES,
    READER_ITEM_FIELDS,
    AnswerRow,
    ProviderFactory,
    _default_provider_factory,
    _request_sha256,
    _sha256,
)
from benchmarks.public_memory_comparison import (
    CANDIDATE_LIMIT,
    CONTEXT_BYTE_LIMIT,
    ITEM_LIMIT,
    encoded,
)
from benchmarks.public_memory_expansion import (
    PRIMARY_INSTRUCTIONS,
    PRIMARY_SCHEMA,
    PROFILES,
    answer_rows,
    config,
    reader_request,
    run_answers,
    save,
)
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_pilot import _hash

RUNNER = "doppel.public-memory-quality-50.v1"
QUESTION_COUNT = 50
BATCH_SIZE = 10


def prepare_batches(
    cases: Sequence[tuple[RuntimeCase, ScoringCase]],
    manifest: Mapping[str, Any],
    comparison: Mapping[str, Any],
) -> list[list[AnswerRow]]:
    """Bind the entire six-profile parent before selecting the fixed QA profiles."""
    old = comparison.get("rows")
    expected = {(s.case_id, p) for _, s in cases for p in PROFILE_NAMES}
    if (
        len(cases) != QUESTION_COUNT
        or len({s.case_id for _, s in cases}) != QUESTION_COUNT
        or comparison.get("runner") != COMPARISON_RUNNER
        or comparison.get("status") != "complete"
        or comparison.get("manifest_fingerprint") != manifest["manifest_fingerprint"]
        or comparison.get("corpus_sha256_before")
        != comparison.get("corpus_sha256_after")
        or not comparison.get("corpus_sha256_before")
        or comparison.get("record_or_index_writes") != 0
        or not isinstance(old, list)
        or len(old) != len(expected)
        or {(r.get("case_id"), r.get("profile")) for r in old} != expected
    ):
        raise ValueError("complete unchanged fifty-question comparison required")
    for row in old:
        context = row.get("context")
        if (
            not isinstance(context, list)
            or len(context) > ITEM_LIMIT
            or row.get("packed_item_count") != len(context)
            or row.get("packed_context_bytes") != len(encoded(context))
            or len(encoded(context)) > CONTEXT_BYTE_LIMIT
            or any(
                any(field not in item for field in READER_ITEM_FIELDS)
                for item in context
            )
            or len({item["memory_id"] for item in context}) != len(context)
        ):
            raise ValueError("packed context identity/budget invalid")
    by_key = {(r["case_id"], r["profile"]): r for r in old}
    batches = []
    for start in range(0, QUESTION_COUNT, BATCH_SIZE):
        selected = cases[start : start + BATCH_SIZE]
        parent_rows = [by_key[s.case_id, p] for _, s in selected for p in PROFILES]
        batches.append(
            answer_rows({"status": "complete", "rows": parent_rows}, selected)
        )
    return batches


def build_plan(
    batches: Sequence[Sequence[AnswerRow]], input_sha256: Mapping[str, str]
) -> dict[str, Any]:
    if (
        len(batches) != 5
        or any(len(b) != 30 for b in batches)
        or len({r.case_id for batch in batches for r in batch}) != QUESTION_COUNT
        or any({r.profile for r in batch} != set(PROFILES) for batch in batches)
    ):
        raise ValueError("five fixed thirty-row batches required")
    root = Path(__file__).parent
    source_names = (
        "public_memory_quality_50.py",
        "public_memory_expansion.py",
        "public_memory_answer_comparison.py",
        "public_memory_reader_v2.py",
        "public_memory_runtime.py",
    )
    value = {
        "runner": RUNNER,
        "input_sha256": dict(input_sha256),
        "source_sha256": {
            name: _sha256((root / name).read_bytes()) for name in source_names
        },
        "profiles": list(PROFILES),
        "questions": QUESTION_COUNT,
        "logical_rows": 150,
        "batch_question_count": BATCH_SIZE,
        "reader_config": config(2048).model_dump(mode="json"),
        "judge_config": config(3072).model_dump(mode="json"),
        "reader_instructions_sha256": _sha256(
            reader_request(batches[0][0]).instructions.encode()
        ),
        "reader_schema_sha256": _hash(reader_request(batches[0][0]).output_schema),
        "judge_instructions_sha256": _sha256(PRIMARY_INSTRUCTIONS.encode()),
        "judge_schema_sha256": _hash(PRIMARY_SCHEMA),
        "max_reader_calls": 150,
        "max_judge_calls": 150,
        "max_total_calls": 300,
        "candidate_budget": CANDIDATE_LIMIT,
        "batch_rows": [
            {
                "batch_id": f"batch-{i + 1:02d}",
                "identities": [(r.index, r.case_id, r.profile) for r in batch],
                "reader_requests": [_request_sha256(reader_request(r)) for r in batch],
                "scoring_binding": _hash(
                    [
                        (
                            r.case_id,
                            r.scoring.category,
                            r.scoring.abstention,
                            r.scoring.answer,
                        )
                        for r in batch
                    ]
                ),
            }
            for i, batch in enumerate(batches)
        ],
        "failure_policy": "single-attempt; retain-failures; no-retry-or-resampling",
        "scoring_policy": "same-model-provisional-with-quote-anchoring-and-explicit-unscored",
    }
    # Use JSON-compatible identities so disk replay binds the exact same plan.
    value = json.loads(json.dumps(value))
    return {**value, "plan_fingerprint": _hash(value)}


def batch_plan(plan: Mapping[str, Any], index: int) -> dict[str, Any]:
    value = {
        "parent_plan_fingerprint": plan["plan_fingerprint"],
        "batch": plan["batch_rows"][index],
        "reader_config": plan["reader_config"],
        "judge_config": plan["judge_config"],
        "max_reader_calls": 30,
        "max_judge_calls": 30,
    }
    return {**value, "plan_fingerprint": _hash(value)}


async def run(
    batches: Sequence[Sequence[AnswerRow]],
    plan: Mapping[str, Any],
    *,
    run_dir: Path,
    api_key: str,
    cache_only: bool,
    provider_factory: ProviderFactory = _default_provider_factory,
) -> dict[str, Any]:
    if build_plan(batches, plan["input_sha256"]) != dict(plan):
        raise ValueError("frozen plan/requests changed")
    _bind_json(run_dir / "plan.json", plan)
    reports = []
    for i, rows in enumerate(batches):
        child = batch_plan(plan, i)
        report = await run_answers(
            rows,
            child,
            run_dir=run_dir / f"batch-{i + 1:02d}",
            api_key=api_key,
            cache_only=cache_only,
            provider_factory=provider_factory,
        )
        mode = "replay" if cache_only else "live"
        save(run_dir / f"batch-{i + 1:02d}-{mode}.json", report)
        reports.append(report)
        print(
            f"batch-{i + 1:02d}: {report['status']} ({len(report['rows'])} rows)",
            flush=True,
        )
    summary = {}
    for profile in PROFILES:
        summary[profile] = {
            key: sum(r["summary"][profile][key] for r in reports)
            for key in reports[0]["summary"][profile]
        }
    return {
        "status": "complete"
        if all(r["status"] == "complete" for r in reports)
        else "partial",
        "batches": reports,
        "summary": summary,
        "scoring_metadata": {
            r.case_id: {
                "category": r.scoring.category,
                "abstention": r.scoring.abstention,
            }
            for batch in batches
            for r in batch
        },
        "new_calls": sum(v["new_calls"] for r in reports for v in r["usage"].values()),
        "judgments_independently_verified": False,
        "publication_ready": False,
        "aml_academic_model_compliant": False,
        "reserved_histories_executed": False,
        "record_or_index_writes": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "manifest", "comparison", "run-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve existing output")
    if args.cache_only and not args.live:
        parser.error("cache-only requires live")
    paths = {
        name: getattr(args, name) for name in ("dataset", "manifest", "comparison")
    }
    content = {name: path.read_bytes() for name, path in paths.items()}
    binding = {name: _sha256(data) for name, data in content.items()}
    manifest = json.loads(content["manifest"])
    cases = select_diagnostic_cases(
        json.loads(content["dataset"]), manifest, source_sha256=binding["dataset"]
    )
    batches = prepare_batches(cases, manifest, json.loads(content["comparison"]))
    plan = build_plan(batches, binding)
    report = {"runner": RUNNER, "plan": plan, "status": "ready", "new_calls": 0}
    if args.live:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_text(encoding="utf-8")).get("plan")
            != plan
        ):
            parser.error("live requires the unchanged frozen preflight")
        key = "" if args.cache_only else os.environ.get(args.api_key_env, "").strip()
        if not args.cache_only and not key:
            parser.error("API key environment variable absent")
        try:
            report.update(
                asyncio.run(
                    run(
                        batches,
                        plan,
                        run_dir=args.run_dir,
                        api_key=key,
                        cache_only=args.cache_only,
                    )
                )
            )
        except Exception as error:  # noqa: BLE001 - sanitized provider boundary
            report.update(
                status="failed",
                failure_type=type(error).__name__,
                new_calls=None,
                usage="see preserved batch ledgers",
            )
    report["execution_metadata"] = execution_metadata()
    save(args.output, report)
    print(f"output: {args.output.resolve()}")
    print(f"sha256: {_sha256(args.output.read_bytes())}")
    print(json.dumps({k: report[k] for k in ("status", "new_calls")}))
    return 0 if report["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
