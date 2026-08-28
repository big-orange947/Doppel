"""Deterministic correctness benchmark for personal-memory governance."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import platform
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doppel_memory import (
    DeterministicMemoryGovernancePolicy,
    FactAuthority,
    InMemoryStore,
    MemoryFilter,
    MemoryGovernanceRunner,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    WriteStatus,
    __version__,
)
from doppel_memory.models import Actor, utc_now

DEFAULT_DATASET = Path(__file__).parent / "datasets" / "governance-quality-zh-v1.json"


class GovernanceQualityCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    memory_id: str
    content: str
    memory_type: str
    importance: float = Field(ge=0.0, le=1.0)
    authority: FactAuthority
    valid_to: datetime | None = None
    retention_class: str = ""
    evidence_count: int = Field(default=1, ge=1)
    expected_operation: Literal["reinforce", "decay", "archive"] | None = None
    expected_importance: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_expectation(self) -> GovernanceQualityCase:
        if self.expected_operation in {"reinforce", "decay"} and (
            self.expected_importance is None
        ):
            raise ValueError("importance-changing expectations require a target")
        return self


class GovernanceQualityDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_version: Literal[1] = 1
    name: str
    language: str
    now: datetime
    cases: list[GovernanceQualityCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_unique_cases(self) -> GovernanceQualityDataset:
        names = [case.name for case in self.cases]
        memory_ids = [case.memory_id for case in self.cases]
        if len(names) != len(set(names)):
            raise ValueError("governance quality case names must be unique")
        if len(memory_ids) != len(set(memory_ids)):
            raise ValueError("governance quality memory IDs must be unique")
        return self

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.model_dump(mode="json"))


def load_governance_quality_dataset(
    path: str | Path = DEFAULT_DATASET,
) -> GovernanceQualityDataset:
    with Path(path).open(encoding="utf-8") as source:
        return GovernanceQualityDataset.model_validate(json.load(source))


async def run_governance_quality_benchmark(
    dataset: GovernanceQualityDataset,
) -> dict[str, Any]:
    started = perf_counter()
    case_results = [await _run_case(dataset, case) for case in dataset.cases]
    metrics = {
        "expected_action_count": sum(
            case.expected_operation is not None for case in dataset.cases
        ),
        "actual_action_count": sum(
            item["actual_operation"] is not None for item in case_results
        ),
        "false_action_count": sum(item["false_action_count"] for item in case_results),
        "missing_action_count": sum(
            item["missing_action_count"] for item in case_results
        ),
        "wrong_operation_count": sum(
            item["wrong_operation_count"] for item in case_results
        ),
        "importance_error_count": sum(
            item["importance_error_count"] for item in case_results
        ),
        "lifecycle_error_count": sum(
            item["lifecycle_error_count"] for item in case_results
        ),
        "scope_leakage_count": sum(
            item["scope_leakage_count"] for item in case_results
        ),
        "latency_ms": _rounded((perf_counter() - started) * 1_000),
    }
    errors = [
        f"{case['name']}: {error}" for case in case_results for error in case["errors"]
    ]
    correctness_counts = [
        metrics[key]
        for key in (
            "false_action_count",
            "missing_action_count",
            "wrong_operation_count",
            "importance_error_count",
            "lifecycle_error_count",
            "scope_leakage_count",
        )
    ]
    return {
        "result_schema_version": 1,
        "doppel_version": __version__,
        "generated_at": utc_now().isoformat(),
        "dataset": {
            "name": dataset.name,
            "version": dataset.dataset_version,
            "language": dataset.language,
            "case_count": len(dataset.cases),
            "fingerprint": dataset.fingerprint,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "metrics": metrics,
        "cases": case_results,
        "correctness": {
            "passed": not any(correctness_counts) and not errors,
            "scope_leakage_count": metrics["scope_leakage_count"],
            "errors": errors,
        },
    }


async def _run_case(
    dataset: GovernanceQualityDataset, case: GovernanceQualityCase
) -> dict[str, Any]:
    store = InMemoryStore()
    scope = MemoryScope(user_id=f"quality-{case.name}", agent_id="governance-quality")
    started = perf_counter()
    try:
        metadata: dict[str, Any] = {
            "personal_memory_type": case.memory_type,
            "subject": Actor.OWNER,
            "temporal_status": "current",
            "evidence": [
                {
                    "evidence_id": f"{case.memory_id}-evidence-{index}",
                    "message_id": f"{case.memory_id}-message-{index}",
                    "actor": Actor.OWNER,
                    "at": "2026-01-01T00:00:00+00:00",
                }
                for index in range(case.evidence_count)
            ],
        }
        if case.valid_to is not None:
            metadata["valid_to"] = case.valid_to.isoformat()
        if case.retention_class:
            metadata["retention_class"] = case.retention_class
        source_write = await store.put(
            MemoryRecord(
                memory_id=case.memory_id,
                scope=scope,
                content=case.content,
                actor=Actor.OWNER,
                authority=case.authority,
                state=MemoryState.CONFIRMED,
                tags=["personal-memory"],
                importance=case.importance,
                extractor="governance-quality-fixture",
                created_at=datetime.fromisoformat("2026-01-01T00:00:00+00:00"),
                updated_at=datetime.fromisoformat("2026-01-01T00:00:00+00:00"),
                metadata=metadata,
            )
        )
        if source_write.status is not WriteStatus.CREATED:
            raise RuntimeError("fixture memory was not created")
        runner = MemoryGovernanceRunner(store)
        plan = await runner.plan_once(
            DeterministicMemoryGovernancePolicy(), scope, now=dataset.now
        )
        actual_operation = plan.actions[0].operation if plan.actions else None
        result = await runner.execute(plan)
        replacement = (
            result.actions[0].replacement_write.record if result.actions else None
        )
        source = await store.get(scope, case.memory_id)
        page = await store.scan(
            scope, filters=MemoryFilter(include_inactive=True), limit=100
        )
        false_action = int(
            case.expected_operation is None and actual_operation is not None
        )
        missing_action = int(
            case.expected_operation is not None and actual_operation is None
        )
        wrong_operation = int(
            case.expected_operation is not None
            and actual_operation is not None
            and actual_operation != case.expected_operation
        )
        importance_error = int(
            case.expected_importance is not None
            and (
                replacement is None
                or abs(replacement.importance - case.expected_importance) > 1e-9
            )
        )
        expected_source_state = (
            MemoryState.SUPERSEDED
            if case.expected_operation is not None
            else MemoryState.CONFIRMED
        )
        lifecycle_error = int(
            source is None
            or source.state is not expected_source_state
            or bool(result.errors)
            or (case.expected_operation is not None and replacement is None)
            or (
                case.expected_operation == "archive"
                and replacement is not None
                and replacement.state is not MemoryState.EXPIRED
            )
        )
        scope_leakage = sum(
            record.scope.scope_key != scope.scope_key for record in page.records
        )
        errors: list[str] = []
        if false_action:
            errors.append(f"unexpected action: {actual_operation}")
        if missing_action:
            errors.append(f"missing expected action: {case.expected_operation}")
        if wrong_operation:
            errors.append(f"operation {actual_operation} != {case.expected_operation}")
        if importance_error:
            errors.append("replacement importance differs from expectation")
        if lifecycle_error:
            errors.append("source/replacement lifecycle differs from expectation")
        if scope_leakage:
            errors.append(f"cross-scope records: {scope_leakage}")
        return {
            "name": case.name,
            "expected_operation": case.expected_operation,
            "actual_operation": actual_operation,
            "source_state": source.state.value if source is not None else None,
            "replacement_state": (
                replacement.state.value if replacement is not None else None
            ),
            "replacement_importance": (
                replacement.importance if replacement is not None else None
            ),
            "false_action_count": false_action,
            "missing_action_count": missing_action,
            "wrong_operation_count": wrong_operation,
            "importance_error_count": importance_error,
            "lifecycle_error_count": lifecycle_error,
            "scope_leakage_count": scope_leakage,
            "latency_ms": _rounded((perf_counter() - started) * 1_000),
            "errors": errors,
        }
    finally:
        await store.close()


def _fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _rounded(value: float) -> float:
    return round(float(value), 4)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output")
    return parser


async def _main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = await run_governance_quality_benchmark(
        load_governance_quality_dataset(args.dataset)
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(f"governance quality result: {output}")
    else:
        sys.stdout.write(rendered)
    return 0 if result["correctness"]["passed"] else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
