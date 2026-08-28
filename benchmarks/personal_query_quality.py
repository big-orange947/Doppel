"""Deterministic correctness benchmark for Chinese personal-memory queries."""

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
    DeterministicPersonalMemoryQueryPlanner,
    FactAuthority,
    InMemoryStore,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    PersonalMemoryQueryEngine,
    WriteStatus,
    __version__,
)
from doppel_memory.models import utc_now

DEFAULT_DATASET = (
    Path(__file__).parent / "datasets" / "personal-query-quality-zh-v1.json"
)


class QueryQualityScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    user_id: str
    agent_id: str

    def to_scope(self) -> MemoryScope:
        return MemoryScope(user_id=self.user_id, agent_id=self.agent_id)


class QueryQualityMemory(BaseModel):
    model_config = ConfigDict(frozen=True)

    memory_id: str
    scope: str
    content: str
    at: datetime
    memory_type: str
    topic_key: str = ""
    event_key: str = ""
    temporal_status: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    evidence_ids: list[str] = Field(min_length=1)


class QueryQualityCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    scope: str
    query: str
    expected_intent: Literal[
        "lookup", "current", "history", "planned", "list", "count", "as_of"
    ]
    required_hit_ids: list[str] = Field(default_factory=list)
    forbidden_hit_ids: list[str] = Field(default_factory=list)
    expected_count_status: Literal["not_requested", "exact", "indeterminate"]
    expected_count_value: int | None = Field(default=None, ge=0)
    expected_ambiguous: bool = False


class PersonalQueryQualityDataset(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_version: Literal[1] = 1
    name: str
    language: str
    now: datetime
    scopes: list[QueryQualityScope] = Field(min_length=2)
    memories: list[QueryQualityMemory] = Field(min_length=1)
    queries: list[QueryQualityCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_references(self) -> PersonalQueryQualityDataset:
        scope_names = [scope.name for scope in self.scopes]
        if len(scope_names) != len(set(scope_names)):
            raise ValueError("query quality scope names must be unique")
        known_scopes = set(scope_names)
        memory_ids = [memory.memory_id for memory in self.memories]
        if len(memory_ids) != len(set(memory_ids)):
            raise ValueError("query quality memory IDs must be unique")
        known_ids = set(memory_ids)
        for memory in self.memories:
            if memory.scope not in known_scopes:
                raise ValueError(f"unknown memory scope: {memory.scope}")
        query_names = [query.name for query in self.queries]
        if len(query_names) != len(set(query_names)):
            raise ValueError("query quality case names must be unique")
        for query in self.queries:
            if query.scope not in known_scopes:
                raise ValueError(f"unknown query scope: {query.scope}")
            referenced = set(query.required_hit_ids + query.forbidden_hit_ids)
            if not referenced.issubset(known_ids):
                raise ValueError(f"unknown expected memory in query {query.name}")
            if set(query.required_hit_ids).intersection(query.forbidden_hit_ids):
                raise ValueError(f"required and forbidden hits overlap in {query.name}")
            if (
                query.expected_count_status == "exact"
                and query.expected_count_value is None
            ):
                raise ValueError(f"exact count needs a value in {query.name}")
        return self

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.model_dump(mode="json"))


def load_personal_query_quality_dataset(
    path: str | Path = DEFAULT_DATASET,
) -> PersonalQueryQualityDataset:
    with Path(path).open(encoding="utf-8") as source:
        return PersonalQueryQualityDataset.model_validate(json.load(source))


async def run_personal_query_quality_benchmark(
    dataset: PersonalQueryQualityDataset,
) -> dict[str, Any]:
    store = InMemoryStore()
    scopes = {item.name: item.to_scope() for item in dataset.scopes}
    try:
        for item in dataset.memories:
            scope = scopes[item.scope]
            record = MemoryRecord(
                memory_id=item.memory_id,
                scope=scope,
                content=item.content,
                kind="fact",
                actor=Actor.OWNER,
                authority=FactAuthority.HUMAN_SELF,
                state=MemoryState.CANDIDATE,
                tags=["personal-memory", item.memory_type],
                source_message_id=item.evidence_ids[-1],
                extractor="query-quality-fixture",
                created_at=item.at,
                updated_at=item.at,
                metadata={
                    "personal_memory_type": item.memory_type,
                    "topic_key": item.topic_key,
                    "event_key": item.event_key,
                    "subject": Actor.OWNER,
                    "subject_id": scope.user_id,
                    "temporal_status": item.temporal_status,
                    "valid_from": (
                        item.valid_from.isoformat() if item.valid_from else None
                    ),
                    "valid_to": item.valid_to.isoformat() if item.valid_to else None,
                    "evidence": [
                        {"evidence_id": evidence_id}
                        for evidence_id in item.evidence_ids
                    ],
                },
            )
            written = await store.put(record)
            if written.status is not WriteStatus.CREATED:
                raise RuntimeError(f"fixture memory was not created: {item.memory_id}")

        engine = PersonalMemoryQueryEngine(store)
        planner = DeterministicPersonalMemoryQueryPlanner()
        reports: list[dict[str, Any]] = []
        for case in dataset.queries:
            reports.append(await _run_case(engine, planner, scopes, dataset.now, case))
    finally:
        await store.close()

    errors = [
        f"{report['name']}: {error}" for report in reports for error in report["errors"]
    ]
    missing_hits = sum(report["missing_hit_count"] for report in reports)
    forbidden_hits = sum(report["forbidden_hit_count"] for report in reports)
    intent_errors = sum(report["intent_error_count"] for report in reports)
    count_errors = sum(report["count_error_count"] for report in reports)
    ambiguity_errors = sum(report["ambiguity_error_count"] for report in reports)
    scope_leakage = sum(report["scope_leakage_count"] for report in reports)
    latencies = [report["latency_ms"] for report in reports]
    return {
        "result_schema_version": 1,
        "doppel_version": __version__,
        "generated_at": utc_now().isoformat(),
        "dataset": {
            "name": dataset.name,
            "version": dataset.dataset_version,
            "language": dataset.language,
            "fingerprint": dataset.fingerprint,
            "memory_count": len(dataset.memories),
            "query_count": len(dataset.queries),
        },
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "metrics": {
            "missing_hit_count": missing_hits,
            "forbidden_hit_count": forbidden_hits,
            "intent_error_count": intent_errors,
            "count_error_count": count_errors,
            "ambiguity_error_count": ambiguity_errors,
            "scope_leakage_count": scope_leakage,
            "latency_ms": {
                "total": _rounded(sum(latencies)),
                "max": _rounded(max(latencies, default=0.0)),
            },
        },
        "cases": reports,
        "correctness": {
            "passed": not errors
            and not missing_hits
            and not forbidden_hits
            and not intent_errors
            and not count_errors
            and not ambiguity_errors
            and not scope_leakage,
            "scope_leakage_count": scope_leakage,
            "errors": errors,
        },
    }


async def _run_case(
    engine: PersonalMemoryQueryEngine,
    planner: DeterministicPersonalMemoryQueryPlanner,
    scopes: dict[str, MemoryScope],
    now: datetime,
    case: QueryQualityCase,
) -> dict[str, Any]:
    scope = scopes[case.scope]
    started = perf_counter()
    errors: list[str] = []
    result = await engine.query(planner, case.query, [scope], now=now)
    actual_ids = [hit.record.memory_id for hit in result.hits]
    actual_set = set(actual_ids)
    missing = sorted(set(case.required_hit_ids).difference(actual_set))
    forbidden = sorted(set(case.forbidden_hit_ids).intersection(actual_set))
    intent_error = int(result.plan.intent != case.expected_intent)
    count_error = int(
        result.count.status != case.expected_count_status
        or (
            case.expected_count_value is not None
            and result.count.value != case.expected_count_value
        )
    )
    ambiguity_error = int(result.ambiguous != case.expected_ambiguous)
    scope_leakage = sum(
        hit.record.scope.scope_key != scope.scope_key for hit in result.hits
    )
    if missing:
        errors.append(f"missing required hits: {missing}")
    if forbidden:
        errors.append(f"returned forbidden hits: {forbidden}")
    if intent_error:
        errors.append(f"intent {result.plan.intent!r} != {case.expected_intent!r}")
    if count_error:
        errors.append(
            "count result "
            f"{result.count.status}/{result.count.value} != "
            f"{case.expected_count_status}/{case.expected_count_value}"
        )
    if ambiguity_error:
        errors.append(f"ambiguous {result.ambiguous} != {case.expected_ambiguous}")
    if scope_leakage:
        errors.append(f"cross-scope hits: {scope_leakage}")
    return {
        "name": case.name,
        "query": case.query,
        "expected_intent": case.expected_intent,
        "actual_intent": result.plan.intent,
        "required_hit_ids": case.required_hit_ids,
        "actual_hit_ids": actual_ids,
        "missing_hit_count": len(missing),
        "forbidden_hit_count": len(forbidden),
        "intent_error_count": intent_error,
        "count_error_count": count_error,
        "ambiguity_error_count": ambiguity_error,
        "scope_leakage_count": scope_leakage,
        "count_status": result.count.status,
        "count_value": result.count.value,
        "ambiguous": result.ambiguous,
        "warnings": result.warnings,
        "latency_ms": _rounded((perf_counter() - started) * 1_000),
        "errors": errors,
    }


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
    result = await run_personal_query_quality_benchmark(
        load_personal_query_quality_dataset(args.dataset)
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(f"personal query quality result: {output}")
    else:
        sys.stdout.write(rendered)
    return 0 if result["correctness"]["passed"] else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
