"""Reader-only development comparison on unchanged packed contexts.

No Judge execution or QA score; old answers are reporting-only. Gold never reaches
the reader. Structural derivation checks do not prove arithmetic or entailment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from benchmarks.public_context_baseline import (
    execution_metadata,
    select_diagnostic_cases,
)
from benchmarks.public_memory_answer_comparison import (
    EXPECTED_ROWS,
    READER_INSTRUCTIONS,
    READER_SCHEMA,
    AnswerRow,
    ProviderFactory,
    ReaderOutput,
    _canonical_sha256,
    _default_provider_factory,
    _ledger_records,
    _request_sha256,
    _sha256,
    _StageExecutor,
    build_rows,
    citation_audit,
    context_items_payload,
)
from benchmarks.public_memory_answer_comparison import (
    RUNNER as V1_RUNNER,
)
from benchmarks.public_memory_answer_comparison import (
    build_reader_request as v1_request,
)
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from doppel_memory.intelligence import StructuredGenerationRequest
from doppel_memory.openai_compatible import OpenAICompatibleStructuredOutputConfig

RUNNER = "doppel.public-memory-reader-v2.v1"
CAP = 18
INSTRUCTIONS = (
    READER_INSTRUCTIONS
    + """

Derivation policy: When the requested information follows from the supplied items
by arithmetic (sum, difference, ratio, count) or another defensible inference,
give the derived answer and state its assumptions. Do not refuse solely because
the derived result is not written verbatim. Do not assume equal allocation, unique
events, completed plans or unstated inputs when the items do not justify them.
Use a derived block for a derived answer: kind, exact input_memory_ids and result.
Otherwise omit derived or set it to null. Cite all inputs in cited_memory_ids.
The derived block records your reasoning sources, not an independently proved fact.

Abstention consistency: If you supply the requested information, even with a
qualification or a derivation, abstained is false. Set it true when you cannot
provide the requested information. If only part can be answered, state the known
part and the limitation explicitly; abstained is false for a substantive partial
answer. Do not declare missing information and then provide it as an answer.

Absence policy: Before saying a value, count or other input is missing, check ALL
supplied items, including your own citations. Limit absence claims to these
supplied items, not the entire history or the world. Do not assert that an event
never happened simply because retrieval did not supply it.

Temporal policy: observed_at is when a statement was observed, not necessarily
when its fact was valid. Use explicit effective bounds and textual dates,
corrections, cancellations and temporary changes. A newer observation of an old
fact does not automatically supersede another fact. If dates or authority leave
an unresolved conflict, describe it instead of silently choosing newest-wins.

Language policy: Use the question's language for your answer, including caveats.
Quoting a foreign-language source does not require changing the answer's language.
"""
)

DERIVED_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "kind": {
            "type": "string",
            "enum": ["sum", "difference", "ratio", "count", "other"],
        },
        "input_memory_ids": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string"},
        },
        "result": {"type": "string", "minLength": 1},
    },
    "required": ["kind", "input_memory_ids", "result"],
}
SCHEMA = {
    **READER_SCHEMA,
    "title": "MemoryReaderV2Answer",
    "properties": {
        **READER_SCHEMA["properties"],
        "derived": {"anyOf": [DERIVED_SCHEMA, {"type": "null"}]},
    },
}


class DerivedOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["sum", "difference", "ratio", "count", "other"]
    input_memory_ids: list[str]
    result: str

    @field_validator("input_memory_ids")
    @classmethod
    def nonempty_inputs(cls, value: list[str]) -> list[str]:
        if not value or any(not item.strip() for item in value):
            raise ValueError("derivation requires nonblank source ids")
        return value

    @field_validator("result")
    @classmethod
    def nonblank_result(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("derivation requires a nonblank result")
        return value


class ReaderV2Output(ReaderOutput):
    model_config = ConfigDict(extra="forbid", strict=True)
    derived: DerivedOutput | None = None


def build_request(row: AnswerRow) -> StructuredGenerationRequest:
    return v1_request(row).model_copy(
        update={"instructions": INSTRUCTIONS, "output_schema": SCHEMA}
    )


def bind_baseline(rows: Sequence[AnswerRow], baseline: Mapping[str, Any]) -> None:
    """Bind v1 request payloads, not just case/profile names or a passed flag."""
    old = baseline.get("rows")
    if (
        baseline.get("runner") != V1_RUNNER
        or baseline.get("status") != "complete"
        or not isinstance(old, list)
        or len(old) != EXPECTED_ROWS
    ):
        raise ValueError("complete frozen v1 baseline required")
    for row, previous in zip(rows, old, strict=True):
        if (
            previous.get("index") != row.index
            or previous.get("case_id") != row.case_id
            or previous.get("profile") != row.profile
            or previous.get("reader", {}).get("status") != "completed"
            or previous["reader"].get("request_sha256")
            != _request_sha256(v1_request(row))
        ):
            raise ValueError("v1 baseline request/context binding changed")
        ReaderOutput.model_validate(previous["reader"])


def build_plan(
    rows: Sequence[AnswerRow],
    binding: Mapping[str, str],
    config: OpenAICompatibleStructuredOutputConfig,
) -> dict[str, Any]:
    if len(rows) != EXPECTED_ROWS or len({r.index for r in rows}) != EXPECTED_ROWS:
        raise ValueError("exactly 18 distinct frozen rows required")
    plan = {
        "schema_version": "doppel.public-memory-reader-v2-plan.v1",
        "input_binding": dict(binding),
        "provider_config": config.model_dump(mode="json"),
        "row_identity_sha256": _canonical_sha256(
            [(r.index, r.case_id, r.profile) for r in rows]
        ),
        "request_sha256s": [_request_sha256(build_request(r)) for r in rows],
        "reader_instructions_sha256": _sha256(INSTRUCTIONS.encode()),
        "reader_schema_sha256": _canonical_sha256(SCHEMA),
        "max_new_reader_calls": CAP,
        "max_new_judge_calls": 0,
        "failure_policy": "single-attempt; preserve-invalid-output; no-repair-or-retry",
        "qa_scoring_policy": "none; structural-checks-and-side-by-side-answers-only",
        "scope": "three-opened-development-questions; no-reserved-histories",
    }
    return {**plan, "plan_fingerprint": _hash(plan)}


def structural_check(row: AnswerRow, output: ReaderV2Output) -> dict[str, Any]:
    citation = citation_audit(row.context, output.cited_memory_ids)
    derived = output.derived
    inputs = derived.input_memory_ids if derived else []
    allowed = {item["memory_id"] for item in row.context}
    unknown = [value for value in inputs if value not in allowed]
    uncited = [value for value in inputs if value not in output.cited_memory_ids]
    duplicates = sorted({value for value in inputs if inputs.count(value) > 1})
    conflict = bool(derived and output.abstained)
    return {
        "citation_check": citation,
        "derivation_check": {
            "present": derived is not None,
            "unknown_input_ids": unknown,
            "uncited_input_ids": uncited,
            "duplicate_input_ids": duplicates,
            "abstention_derivation_conflict": conflict,
            "structurally_valid": not (unknown or uncited or duplicates or conflict),
            "arithmetic_or_entailment_verified": False,
        },
        "structurally_valid": citation["legal"]
        and not citation["duplicate_ids"]
        and not (unknown or uncited or duplicates or conflict),
    }


def summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    completed = [r for r in rows if r["reader"]["status"] == "completed"]
    return {
        "logical_rows": len(rows),
        "completed_rows": len(completed),
        "failed_rows": len(rows) - len(completed),
        "structurally_valid_rows": sum(
            r["checks"]["structurally_valid"] for r in completed
        ),
        "derived_rows": sum(
            r["checks"]["derivation_check"]["present"] for r in completed
        ),
        "abstained_rows": sum(r["reader"]["output"]["abstained"] for r in completed),
        "changed_answer_rows": sum(
            r["comparison"]["answer_changed"] for r in completed
        ),
        "abstention_flag_changed_rows": sum(
            r["comparison"]["abstention_flag_changed"] for r in completed
        ),
        "answer_correct": None,
        "citation_supported": None,
        "semantic_abstention_consistency": None,
        "note": "Structural legality and changed behavior are not correctness or improvement.",
    }


async def run_reader(
    rows: Sequence[AnswerRow],
    baseline: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    run_dir: Path,
    api_key: str,
    cache_only: bool,
    provider_factory: ProviderFactory,
) -> dict[str, Any]:
    bind_baseline(rows, baseline)
    if _canonical_sha256(baseline) != plan["input_binding"].get("baseline_canonical"):
        raise ValueError("v1 baseline content changed before execution")
    config = OpenAICompatibleStructuredOutputConfig.model_validate(
        plan["provider_config"]
    )
    if build_plan(rows, plan["input_binding"], config) != dict(plan):
        raise ValueError("reader-v2 plan or request payload changed before execution")
    if config.model_dump(mode="json") != baseline["plan"]["provider_config"]:
        raise ValueError("generation settings must match the v1 baseline")
    _bind_json(run_dir / "plan.json", plan)
    usage_path = run_dir / "usage.sqlite3"
    budget_id = "reader-v2:" + plan["plan_fingerprint"]
    ledger = DurableCallLedger(usage_path, budget_id=budget_id, max_calls=CAP)
    before = ledger.report()["attempts_reserved"]
    reports: list[dict[str, Any]] = []
    try:
        if before and not cache_only:
            raise ValueError(
                "attempted run must use cache-only replay; no rebilling or retry"
            )
        model = PilotStructuredModel(
            provider_factory(config, api_key, ledger.observe_usage),
            ledger=ledger,
            cache_dir=run_dir / "provider-cache",
            cache_only=cache_only,
        )
        stage = _StageExecutor(model, ledger, ReaderV2Output, cache_only=cache_only)
        for row, old in zip(rows, baseline["rows"], strict=True):
            output, record = await stage.execute(build_request(row), row.index)
            previous = ReaderOutput.model_validate(old["reader"]).model_dump(
                mode="json"
            )
            reports.append(
                {
                    "index": row.index,
                    "case_id": row.case_id,
                    "profile": row.profile,
                    "context_items": context_items_payload(row.context),
                    "baseline_reader": previous,
                    "reader": {
                        **{k: v for k, v in record.items() if k != "first_row"},
                        "output": output.model_dump(mode="json") if output else None,
                    },
                    "checks": structural_check(row, output) if output else None,
                    "comparison": {
                        "answer_changed": output.answer != previous["answer"],
                        "abstention_flag_changed": output.abstained
                        != previous["abstained"],
                        "citation_ids_changed": output.cited_memory_ids
                        != previous["cited_memory_ids"],
                    }
                    if output
                    else None,
                }
            )
        model_report = model.report()
        records = _ledger_records(usage_path, budget_id)
    finally:
        ledger.close()
    for report in reports:
        report["reader"]["attempts"] = [
            record
            for record in records
            if record["request_sha256"] == report["reader"]["request_sha256"]
        ]
    return {
        **base_report(plan),
        "status": "complete"
        if len(reports) == EXPECTED_ROWS
        and all(r["reader"]["status"] == "completed" for r in reports)
        else "partial",
        "mode": "live-cache-only-replay" if cache_only else "live-model",
        "budget": {
            "new_reader_calls": model_report["ledger"]["attempts_reserved"] - before,
            "new_judge_calls": 0,
            "ledger": model_report["ledger"],
        },
        "cache": model_report,
        "rows": reports,
        "metrics": summary(reports),
    }


def base_report(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "runner": RUNNER,
        "plan": dict(plan),
        "execution_metadata": {
            **execution_metadata(),
            "reader_v2_source_sha256": _sha256(Path(__file__).read_bytes()),
        },
        "judge_executed": False,
        "retrieval_rerun": False,
        "store_writes": 0,
        "gold_shown_to_reader": False,
        "reserved_histories_executed": False,
        "qa_metrics_available": False,
        "blind_evaluation": False,
        "publication_ready": False,
        "aml_academic_model_compliant": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "manifest", "comparison", "baseline", "output", "run-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--comparison-sha256", required=True)
    parser.add_argument("--baseline-sha256", required=True)
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.cache_only and not args.live:
        parser.error("cache-only requires live")
    inputs = {
        name: getattr(args, name)
        for name in ("dataset", "manifest", "comparison", "baseline")
    }
    if args.output.exists() or args.output.resolve() in {
        p.resolve() for p in inputs.values()
    }:
        parser.error("preserve inputs and existing outputs")
    content = {name: path.read_bytes() for name, path in inputs.items()}
    binding = {name: _sha256(data) for name, data in content.items()}
    if (
        binding["comparison"] != args.comparison_sha256.lower()
        or binding["baseline"] != args.baseline_sha256.lower()
    ):
        parser.error("frozen comparison/baseline hash mismatch")
    loaded = {name: json.loads(data) for name, data in content.items()}
    baseline, comparison, manifest = (
        loaded["baseline"],
        loaded["comparison"],
        loaded["manifest"],
    )
    binding["baseline_canonical"] = _canonical_sha256(baseline)
    if comparison.get("input_sha256", {}).get("manifest") != binding[
        "manifest"
    ] or baseline.get("input_sha256") != {
        k: binding[k] for k in ("dataset", "manifest", "comparison")
    }:
        parser.error("input provenance mismatch")
    cases = select_diagnostic_cases(
        loaded["dataset"], manifest, source_sha256=binding["dataset"]
    )
    rows = build_rows(comparison, cases, manifest)
    bind_baseline(rows, baseline)
    config = OpenAICompatibleStructuredOutputConfig.model_validate(
        baseline["plan"]["provider_config"]
    )
    plan = build_plan(rows, binding, config)
    report = {
        **base_report(plan),
        "status": "ready",
        "mode": "preflight-no-provider",
        "distinct_reader_requests": len(set(plan["request_sha256s"])),
        "new_reader_calls": 0,
    }
    if args.live:
        key = "" if args.cache_only else os.environ.get(args.api_key_env, "").strip()
        if not args.cache_only and not key:
            parser.error("API key environment variable absent")
        try:
            report = asyncio.run(
                run_reader(
                    rows,
                    baseline,
                    plan,
                    run_dir=args.run_dir,
                    api_key=key,
                    cache_only=args.cache_only,
                    provider_factory=_default_provider_factory,
                )
            )
        except Exception as error:  # noqa: BLE001 - sanitize transport/runtime details
            report = {
                **base_report(plan),
                "status": "failed",
                "mode": "live-cache-only-replay" if args.cache_only else "live-model",
                "failure_type": type(error).__name__,
                "new_reader_calls": None,
                "usage_accounting": "inspect retained durable ledger; unknown is not zero",
            }
    report["api_key_read"] = args.live and not args.cache_only
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"output: {args.output.resolve()}")
    print(f"sha256: {_sha256(args.output.read_bytes())}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "qa_metrics_available": False,
                "metrics": report.get("metrics"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
