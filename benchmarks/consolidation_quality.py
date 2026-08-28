"""Deterministic correctness benchmark for personal-memory consolidation."""

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
    Actor,
    ConsolidationRunner,
    DeterministicMemoryConsolidator,
    FactAuthority,
    InMemoryStore,
    MemoryFilter,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    WriteStatus,
    __version__,
)
from doppel_memory.models import utc_now

DEFAULT_DATASET = (
    Path(__file__).parent / "datasets" / "consolidation-quality-zh-v1.json"
)


class ConsolidationQualityScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    user_id: str
    agent_id: str = "quality-agent"

    def to_scope(self) -> MemoryScope:
        return MemoryScope(user_id=self.user_id, agent_id=self.agent_id)


class ConsolidationQualityMemory(BaseModel):
    model_config = ConfigDict(frozen=True)

    memory_id: str
    scope: str
    content: str
    at: datetime
    memory_type: str
    topic_key: str = ""
    temporal_status: str = "current"
    evidence_ids: list[str] = Field(min_length=1)


class ExpectedConsolidationAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    operation: Literal["merge", "correct"]
    source_memory_ids: list[str] = Field(min_length=2)
    canonical_source_memory_id: str

    @model_validator(mode="after")
    def _canonical_is_a_source(self) -> ExpectedConsolidationAction:
        if self.canonical_source_memory_id not in self.source_memory_ids:
            raise ValueError("expected canonical source must be in source_memory_ids")
        return self


class ConsolidationQualityCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    category: str
    description: str
    scope: str
    memories: list[ConsolidationQualityMemory] = Field(min_length=2)
    expected_actions: list[ExpectedConsolidationAction] = Field(default_factory=list)


class ConsolidationQualityDataset(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_version: Literal[1] = 1
    name: str
    language: str = "zh-CN"
    scopes: list[ConsolidationQualityScope] = Field(min_length=2)
    cases: list[ConsolidationQualityCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_references(self) -> ConsolidationQualityDataset:
        scope_names = [scope.name for scope in self.scopes]
        if len(scope_names) != len(set(scope_names)):
            raise ValueError("consolidation quality scope names must be unique")
        known_scopes = set(scope_names)
        seen_ids: set[str] = set()
        for case in self.cases:
            if case.scope not in known_scopes:
                raise ValueError(f"unknown case scope: {case.scope}")
            ids = {memory.memory_id for memory in case.memories}
            if len(ids) != len(case.memories):
                raise ValueError(f"duplicate memory ID in case {case.name}")
            if seen_ids.intersection(ids):
                raise ValueError("memory IDs must be dataset-unique")
            seen_ids.update(ids)
            if any(memory.scope != case.scope for memory in case.memories):
                raise ValueError(f"case {case.name} contains a cross-scope input")
            claimed: set[str] = set()
            for action in case.expected_actions:
                if not set(action.source_memory_ids).issubset(ids):
                    raise ValueError(f"unknown expected source in case {case.name}")
                if claimed.intersection(action.source_memory_ids):
                    raise ValueError(
                        f"overlapping expected actions in case {case.name}"
                    )
                claimed.update(action.source_memory_ids)
        return self

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.model_dump(mode="json"))


def load_consolidation_quality_dataset(
    path: str | Path = DEFAULT_DATASET,
) -> ConsolidationQualityDataset:
    with Path(path).open(encoding="utf-8") as source:
        return ConsolidationQualityDataset.model_validate(json.load(source))


async def run_consolidation_quality_benchmark(
    dataset: ConsolidationQualityDataset,
) -> dict[str, Any]:
    scopes = {item.name: item.to_scope() for item in dataset.scopes}
    case_reports: list[dict[str, Any]] = []
    errors: list[str] = []
    total_leakage = 0
    total_false_merges = 0
    total_missing_actions = 0
    total_wrong_canonical = 0
    latencies: list[float] = []
    for case in dataset.cases:
        report = await _run_case(scopes, case)
        case_reports.append(report)
        errors.extend(f"{case.name}: {error}" for error in report["errors"])
        total_leakage += report["scope_leakage_count"]
        total_false_merges += report["false_action_count"]
        total_missing_actions += report["missing_action_count"]
        total_wrong_canonical += report["wrong_canonical_count"]
        latencies.append(report["latency_ms"])
    return {
        "result_schema_version": 1,
        "doppel_version": __version__,
        "generated_at": utc_now().isoformat(),
        "dataset": {
            "name": dataset.name,
            "version": dataset.dataset_version,
            "language": dataset.language,
            "fingerprint": dataset.fingerprint,
            "case_count": len(dataset.cases),
            "memory_count": sum(len(case.memories) for case in dataset.cases),
            "expected_action_count": sum(
                len(case.expected_actions) for case in dataset.cases
            ),
        },
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "metrics": {
            "false_action_count": total_false_merges,
            "missing_action_count": total_missing_actions,
            "wrong_canonical_count": total_wrong_canonical,
            "scope_leakage_count": total_leakage,
            "latency_ms": {
                "total": _rounded(sum(latencies)),
                "max": _rounded(max(latencies, default=0.0)),
            },
        },
        "cases": case_reports,
        "correctness": {
            "passed": not errors
            and not total_leakage
            and not total_false_merges
            and not total_missing_actions
            and not total_wrong_canonical,
            "scope_leakage_count": total_leakage,
            "errors": errors,
        },
    }


async def _run_case(
    scopes: dict[str, MemoryScope],
    case: ConsolidationQualityCase,
) -> dict[str, Any]:
    store = InMemoryStore()
    scope = scopes[case.scope]
    errors: list[str] = []
    started = perf_counter()
    try:
        for item in case.memories:
            record = MemoryRecord(
                memory_id=item.memory_id,
                scope=scope,
                content=item.content,
                kind="fact",
                actor=Actor.OWNER,
                authority=FactAuthority.HUMAN_SELF,
                state=MemoryState.CANDIDATE,
                tags=["personal-memory", item.memory_type],
                source_event_id=f"event:{item.memory_id}",
                source_message_id=item.evidence_ids[-1],
                extractor="quality-fixture",
                created_at=item.at,
                updated_at=item.at,
                metadata={
                    "personal_memory_type": item.memory_type,
                    "topic_key": item.topic_key,
                    "subject": Actor.OWNER,
                    "subject_id": scope.user_id,
                    "temporal_status": item.temporal_status,
                    "valid_from": item.at.isoformat(),
                    "evidence": [
                        {
                            "evidence_id": evidence_id,
                            "message_id": evidence_id,
                            "actor": Actor.OWNER,
                            "at": item.at.isoformat(),
                        }
                        for evidence_id in item.evidence_ids
                    ],
                },
            )
            written = await store.put(record)
            if written.status is not WriteStatus.CREATED:
                raise RuntimeError(f"fixture memory was not created: {item.memory_id}")
        result = await ConsolidationRunner(store).run_once(
            DeterministicMemoryConsolidator(),
            scope,
            run_id=f"quality:{case.name}",
        )
        actual = [
            {
                "operation": action.operation,
                "source_memory_ids": sorted(
                    source.memory_id for source in action.sources
                ),
                "canonical_source_memory_id": action.proposal.metadata["consolidation"][
                    "canonical_source_memory_id"
                ],
                "decision_id": action.decision_id,
            }
            for action in result.plan.actions
        ]
        expected = [
            {
                "operation": action.operation,
                "source_memory_ids": sorted(action.source_memory_ids),
                "canonical_source_memory_id": action.canonical_source_memory_id,
            }
            for action in case.expected_actions
        ]
        actual_keys = {
            (
                item["operation"],
                tuple(item["source_memory_ids"]),
            )
            for item in actual
        }
        expected_keys = {
            (
                item["operation"],
                tuple(item["source_memory_ids"]),
            )
            for item in expected
        }
        false_actions = actual_keys.difference(expected_keys)
        missing_actions = expected_keys.difference(actual_keys)
        wrong_canonical = sum(
            1
            for expected_item in expected
            for actual_item in actual
            if expected_item["operation"] == actual_item["operation"]
            and expected_item["source_memory_ids"] == actual_item["source_memory_ids"]
            and expected_item["canonical_source_memory_id"]
            != actual_item["canonical_source_memory_id"]
        )
        if false_actions:
            errors.append(f"unexpected consolidation actions: {sorted(false_actions)}")
        if missing_actions:
            errors.append(f"missing consolidation actions: {sorted(missing_actions)}")
        if wrong_canonical:
            errors.append(f"wrong canonical selections: {wrong_canonical}")
        if result.errors:
            errors.extend(error.message for error in result.errors)
        if result.committable_checkpoint is None:
            errors.append("clean fixture run did not release a checkpoint")
        all_records = await store.scan(
            scope,
            filters=MemoryFilter(include_inactive=True),
            limit=100,
        )
        scope_leakage = sum(
            record.scope.scope_key != scope.scope_key for record in all_records.records
        )
        active = [
            record
            for record in all_records.records
            if record.state in {MemoryState.CANDIDATE, MemoryState.CONFIRMED}
        ]
        return {
            "name": case.name,
            "category": case.category,
            "input_memory_count": len(case.memories),
            "expected_action_count": len(expected),
            "actual_action_count": len(actual),
            "false_action_count": len(false_actions),
            "missing_action_count": len(missing_actions),
            "wrong_canonical_count": wrong_canonical,
            "scope_leakage_count": scope_leakage,
            "active_memory_count": len(active),
            "active_contents": [record.content for record in active],
            "actions": actual,
            "latency_ms": _rounded((perf_counter() - started) * 1_000),
            "errors": errors,
        }
    finally:
        await store.close()


def _fingerprint(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
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
    result = await run_consolidation_quality_benchmark(
        load_consolidation_quality_dataset(args.dataset)
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(f"consolidation quality result: {output}")
    else:
        sys.stdout.write(rendered)
    return 0 if result["correctness"]["passed"] else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
