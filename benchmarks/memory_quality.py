"""Layered, deterministic quality baselines for long-horizon IM memory."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import platform
import re
import sys
import unicodedata
from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doppel_memory import (
    Actor,
    ChatMessage,
    DoppelClient,
    HistoryWindow,
    InMemoryStore,
    MemoryKind,
    MemoryScope,
    PersonalMemoryAnalyzer,
    PersonalMemoryMiner,
    PersonalMemoryMinerConfig,
    RecallResult,
    Retriever,
    WriteStatus,
    __version__,
)
from doppel_memory.models import utc_now

DEFAULT_DATASET = Path(__file__).parent / "datasets" / "memory-quality-zh-v1.json"
RESULT_SCHEMA_VERSION = 1
_HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[a-z0-9]+")


class QualityScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    user_id: str
    agent_id: str = "quality-agent"
    platform: str = "qq"
    chat_type: str = "private"
    chat_id: str = ""

    def to_scope(self) -> MemoryScope:
        return MemoryScope(
            user_id=self.user_id,
            agent_id=self.agent_id,
            platform=self.platform,
            chat_type=self.chat_type,
            chat_id=self.chat_id,
        )


class QualityMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    message_id: str
    scope: str
    actor: str
    text: str
    at: datetime

    def to_message(self) -> ChatMessage:
        return ChatMessage(
            actor=self.actor,
            text=self.text,
            at=self.at,
            event_id=self.message_id,
            message_id=self.message_id,
            sender_id=f"quality-{self.actor}",
        )


class GoldMemory(BaseModel):
    """A future extraction/consolidation target, not a prewritten Doppel record."""

    model_config = ConfigDict(frozen=True)

    memory_key: str
    scope: str
    content: str
    kind: str = MemoryKind.FACT
    subject: str = Actor.OWNER
    status: Literal["current", "historical"] = "current"
    evidence_message_ids: list[str] = Field(min_length=1)


class EvidenceGroup(BaseModel):
    """Alternative source messages that can satisfy one required fact."""

    model_config = ConfigDict(frozen=True)

    message_ids: list[str] = Field(min_length=1)


class QualityQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    text: str
    scopes: list[str] = Field(min_length=1)
    required_evidence: list[EvidenceGroup] = Field(default_factory=list)
    forbidden_message_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1, le=100)


class QualityCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    category: str
    description: str
    messages: list[QualityMessage] = Field(min_length=1)
    gold_memories: list[GoldMemory] = Field(default_factory=list)
    ignored_message_ids: list[str] = Field(default_factory=list)
    queries: list[QualityQuery] = Field(min_length=1)


class MemoryQualityDataset(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_version: Literal[1] = 1
    name: str
    language: str = "zh-CN"
    recent_window_size: int = Field(default=5, ge=1, le=100)
    scopes: list[QualityScope] = Field(min_length=2)
    cases: list[QualityCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_references(self) -> MemoryQualityDataset:
        scope_names = [scope.name for scope in self.scopes]
        if len(scope_names) != len(set(scope_names)):
            raise ValueError("memory quality scope names must be unique")
        known_scopes = set(scope_names)
        seen_message_ids: set[str] = set()
        seen_memory_keys: set[str] = set()
        seen_query_names: set[str] = set()
        for case in self.cases:
            case_message_ids = {message.message_id for message in case.messages}
            if len(case_message_ids) != len(case.messages):
                raise ValueError(f"duplicate message ID in case {case.name}")
            overlap = seen_message_ids.intersection(case_message_ids)
            if overlap:
                raise ValueError(
                    f"message IDs must be dataset-unique: {sorted(overlap)}"
                )
            seen_message_ids.update(case_message_ids)
            for message in case.messages:
                if message.scope not in known_scopes:
                    raise ValueError(f"unknown message scope: {message.scope}")
            ignored = set(case.ignored_message_ids)
            if not ignored.issubset(case_message_ids):
                raise ValueError(f"ignored message does not exist in case {case.name}")
            for memory in case.gold_memories:
                if memory.memory_key in seen_memory_keys:
                    raise ValueError(f"duplicate gold memory key: {memory.memory_key}")
                seen_memory_keys.add(memory.memory_key)
                if memory.scope not in known_scopes:
                    raise ValueError(f"unknown gold memory scope: {memory.scope}")
                if not set(memory.evidence_message_ids).issubset(case_message_ids):
                    raise ValueError(
                        f"gold memory evidence does not exist in case {case.name}"
                    )
                if ignored.intersection(memory.evidence_message_ids):
                    raise ValueError("ignored messages cannot support a gold memory")
            for query in case.queries:
                if query.name in seen_query_names:
                    raise ValueError(
                        f"query names must be dataset-unique: {query.name}"
                    )
                seen_query_names.add(query.name)
                if not set(query.scopes).issubset(known_scopes):
                    raise ValueError(f"unknown query scope in {query.name}")
                required_ids = {
                    message_id
                    for group in query.required_evidence
                    for message_id in group.message_ids
                }
                forbidden_ids = set(query.forbidden_message_ids)
                if not required_ids.issubset(case_message_ids):
                    raise ValueError(
                        f"required evidence does not exist in {query.name}"
                    )
                if not forbidden_ids.issubset(case_message_ids):
                    raise ValueError(
                        f"forbidden evidence does not exist in {query.name}"
                    )
                if required_ids.intersection(forbidden_ids):
                    raise ValueError(
                        f"required and forbidden evidence overlap in {query.name}"
                    )
                message_scopes = {
                    message.message_id: message.scope for message in case.messages
                }
                if any(
                    message_scopes[message_id] not in query.scopes
                    for message_id in required_ids
                ):
                    raise ValueError(
                        f"required evidence is outside authorized scopes in {query.name}"
                    )
        return self

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(payload).hexdigest()


class QualityCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str
    scope: str
    content: str
    source_message_ids: list[str] = Field(min_length=1)
    score: float | None = None


class QualityExtractionCandidate(BaseModel):
    """One evidence-bound extracted memory before retrieval evaluation."""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    scope: str
    content: str
    subject: str
    source_message_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


@dataclass(frozen=True, slots=True)
class ExtractionCaseRun:
    candidates: list[QualityExtractionCandidate]
    latency_ms: float = 0.0


@runtime_checkable
class MemoryExtractionBaseline(Protocol):
    name: str
    version: str

    async def run_case(
        self, dataset: MemoryQualityDataset, case: QualityCase
    ) -> ExtractionCaseRun: ...


class PersonalMemoryExtractionBaseline:
    """Run the real periodic extraction path with an injected analyzer."""

    name = "doppel_v0_7_2_personal_memory"
    version = "1"

    def __init__(
        self,
        analyzer: PersonalMemoryAnalyzer,
        *,
        config: PersonalMemoryMinerConfig | None = None,
    ) -> None:
        self.analyzer = analyzer
        self.config = config or PersonalMemoryMinerConfig()

    async def run_case(
        self, dataset: MemoryQualityDataset, case: QualityCase
    ) -> ExtractionCaseRun:
        scopes = {item.name: item.to_scope() for item in dataset.scopes}
        scope_names = {scope.scope_key: name for name, scope in scopes.items()}
        store = InMemoryStore()
        client = DoppelClient(store)
        started = perf_counter()
        candidates: list[QualityExtractionCandidate] = []
        try:
            for message in sorted(
                case.messages, key=lambda item: (item.at, item.message_id)
            ):
                result = await client.ingest(
                    scopes[message.scope], message.to_message()
                )
                if result.status is not WriteStatus.CREATED:
                    raise RuntimeError(
                        f"quality fixture event was not created: {message.message_id}"
                    )
            source_scope_names = list(
                dict.fromkeys(message.scope for message in case.messages)
            )
            for source_scope_name in source_scope_names:
                source_messages = [
                    message
                    for message in case.messages
                    if message.scope == source_scope_name
                ]
                source_scope = scopes[source_scope_name]
                window = HistoryWindow(
                    start=min(message.at for message in source_messages),
                    end=max(message.at for message in source_messages)
                    + timedelta(microseconds=1),
                )
                result = await client.run_batch_task(
                    PersonalMemoryMiner(self.analyzer, self.config),
                    source_scope,
                    window,
                    allowed_scopes=[source_scope.user_scope()],
                    run_id=f"quality:{case.name}:{source_scope_name}",
                )
                if result.errors or any(
                    item.status is WriteStatus.FAILED for item in result.write_results
                ):
                    details = [error.message for error in result.errors]
                    details.extend(
                        item.message or item.error_code or "write failed"
                        for item in result.write_results
                        if item.status is WriteStatus.FAILED
                    )
                    raise RuntimeError(
                        "personal memory quality extraction failed: "
                        + "; ".join(details)
                    )
                for proposal in result.proposals:
                    evidence = proposal.metadata.get("evidence", [])
                    evidence_ids = [
                        str(item.get("evidence_id", ""))
                        for item in evidence
                        if isinstance(item, dict) and item.get("evidence_id")
                    ]
                    scope_name = scope_names.get(proposal.scope.scope_key, "")
                    candidates.append(
                        QualityExtractionCandidate(
                            candidate_id=proposal.idempotency_key,
                            scope=scope_name,
                            content=proposal.content,
                            subject=str(proposal.metadata.get("subject", "")),
                            source_message_ids=evidence_ids,
                            confidence=proposal.confidence,
                        )
                    )
        finally:
            await client.close()
        return ExtractionCaseRun(
            candidates=candidates,
            latency_ms=_milliseconds_since(started),
        )


@dataclass(frozen=True, slots=True)
class BaselineCaseRun:
    candidates: dict[str, list[QualityCandidate]]
    query_latency_ms: dict[str, float]
    prepare_latency_ms: float = 0.0


@runtime_checkable
class MemoryQualityBaseline(Protocol):
    name: str
    version: str

    async def run_case(
        self, dataset: MemoryQualityDataset, case: QualityCase
    ) -> BaselineCaseRun: ...


class _Baseline(ABC):
    version = "1"

    @abstractmethod
    async def run_case(
        self, dataset: MemoryQualityDataset, case: QualityCase
    ) -> BaselineCaseRun: ...


class NoMemoryBaseline(_Baseline):
    name = "no_memory"

    async def run_case(
        self, dataset: MemoryQualityDataset, case: QualityCase
    ) -> BaselineCaseRun:
        del dataset
        return BaselineCaseRun(
            candidates={query.name: [] for query in case.queries},
            query_latency_ms={query.name: 0.0 for query in case.queries},
        )


class RecentWindowBaseline(_Baseline):
    name = "recent_window"

    async def run_case(
        self, dataset: MemoryQualityDataset, case: QualityCase
    ) -> BaselineCaseRun:
        results: dict[str, list[QualityCandidate]] = {}
        latencies: dict[str, float] = {}
        for query in case.queries:
            started = perf_counter()
            allowed = set(query.scopes)
            messages = sorted(
                (message for message in case.messages if message.scope in allowed),
                key=lambda message: (message.at, message.message_id),
                reverse=True,
            )[: min(dataset.recent_window_size, query.limit)]
            results[query.name] = [_message_candidate(message) for message in messages]
            latencies[query.name] = _milliseconds_since(started)
        return BaselineCaseRun(candidates=results, query_latency_ms=latencies)


class RawLexicalBaseline(_Baseline):
    """Naive all-message character n-gram retrieval without memory extraction."""

    name = "raw_lexical"

    async def run_case(
        self, dataset: MemoryQualityDataset, case: QualityCase
    ) -> BaselineCaseRun:
        del dataset
        message_vectors = {
            message.message_id: _features(message.text) for message in case.messages
        }
        results: dict[str, list[QualityCandidate]] = {}
        latencies: dict[str, float] = {}
        for query in case.queries:
            started = perf_counter()
            query_vector = _features(query.text)
            allowed = set(query.scopes)
            ranked = sorted(
                (
                    (
                        _cosine(query_vector, message_vectors[message.message_id]),
                        message,
                    )
                    for message in case.messages
                    if message.scope in allowed
                ),
                key=lambda item: (item[0], item[1].at, item[1].message_id),
                reverse=True,
            )
            results[query.name] = [
                _message_candidate(message, score=score)
                for score, message in ranked[: query.limit]
                if score > 0
            ]
            latencies[query.name] = _milliseconds_since(started)
        return BaselineCaseRun(candidates=results, query_latency_ms=latencies)


class CurrentDoppelBaseline(_Baseline):
    """Current core behavior: raw event ingest plus default Store retrieval."""

    name = "doppel_v0_7_events"

    async def run_case(
        self, dataset: MemoryQualityDataset, case: QualityCase
    ) -> BaselineCaseRun:
        scopes = {item.name: item.to_scope() for item in dataset.scopes}
        store = InMemoryStore()
        prepare_started = perf_counter()
        for message in sorted(
            case.messages, key=lambda item: (item.at, item.message_id)
        ):
            result = await store.write_event(
                scopes[message.scope], message.to_message()
            )
            if result.status is not WriteStatus.CREATED:
                raise RuntimeError(
                    f"quality fixture event was not created: {message.message_id}"
                )
        prepare_latency = _milliseconds_since(prepare_started)
        retriever = Retriever(store)
        scope_names_by_key = {scope.scope_key: name for name, scope in scopes.items()}
        results: dict[str, list[QualityCandidate]] = {}
        latencies: dict[str, float] = {}
        try:
            for query in case.queries:
                started = perf_counter()
                hits = await retriever.recall(
                    query.text,
                    [scopes[name] for name in query.scopes],
                    limit=query.limit,
                )
                results[query.name] = [
                    _recall_candidate(hit, scope_names_by_key) for hit in hits
                ]
                latencies[query.name] = _milliseconds_since(started)
        finally:
            await store.close()
        return BaselineCaseRun(
            candidates=results,
            query_latency_ms=latencies,
            prepare_latency_ms=prepare_latency,
        )


DEFAULT_BASELINES: tuple[MemoryQualityBaseline, ...] = (
    NoMemoryBaseline(),
    RecentWindowBaseline(),
    RawLexicalBaseline(),
    CurrentDoppelBaseline(),
)


def load_memory_quality_dataset(
    path: str | Path = DEFAULT_DATASET,
) -> MemoryQualityDataset:
    with Path(path).open(encoding="utf-8") as source:
        return MemoryQualityDataset.model_validate(json.load(source))


def build_metamorphic_memory_quality_dataset(
    dataset: MemoryQualityDataset,
    replacements: Mapping[str, str],
    *,
    variant: str,
) -> MemoryQualityDataset:
    """Build an evidence-equivalent dataset with substituted domain entities.

    The replacement is deliberately limited to natural-language inputs and gold
    renderings. Scope names, actors, timestamps, message IDs, evidence groups, and
    forbidden evidence remain byte-for-byte equivalent. This makes the variant useful
    for catching retrieval logic that recognizes fixture vocabulary instead of general
    query structure.

    Replacements are simultaneous rather than sequential, so a target can never be
    processed again during the same transformation. Every requested source term must
    occur at least once; a miss is treated as a stale or invalid quality fixture.
    """

    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", variant):
        raise ValueError("metamorphic variant must be a lowercase stable identifier")
    normalized = dict(replacements)
    if not normalized:
        raise ValueError("metamorphic replacements must not be empty")
    if any(not source or not target for source, target in normalized.items()):
        raise ValueError("metamorphic replacement terms must not be empty")
    if any(source == target for source, target in normalized.items()):
        raise ValueError("metamorphic replacement must change every source term")
    if len(set(normalized.values())) != len(normalized):
        raise ValueError("metamorphic replacement targets must be unique")

    pattern = re.compile(
        "|".join(re.escape(source) for source in sorted(normalized, key=len, reverse=True))
    )
    occurrences: Counter[str] = Counter()

    def replace_text(value: str) -> str:
        def substitute(match: re.Match[str]) -> str:
            source = match.group(0)
            occurrences[source] += 1
            return normalized[source]

        return pattern.sub(substitute, value)

    original = dataset.model_dump(mode="json")
    transformed = deepcopy(original)
    for case in transformed["cases"]:
        for message in case["messages"]:
            message["text"] = replace_text(message["text"])
        for memory in case["gold_memories"]:
            memory["content"] = replace_text(memory["content"])
        for query in case["queries"]:
            query["text"] = replace_text(query["text"])

    missing = sorted(set(normalized).difference(occurrences))
    if missing:
        raise ValueError(
            f"metamorphic source terms are absent from quality text: {missing}"
        )

    if _without_quality_language(original) != _without_quality_language(transformed):
        raise AssertionError("metamorphic transformation changed the evidence graph")
    transformed["name"] = f"{dataset.name}.metamorphic.{variant}"
    return MemoryQualityDataset.model_validate(transformed)


def _without_quality_language(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a structural copy suitable for evidence-graph comparison."""

    stripped = deepcopy(payload)
    for case in stripped["cases"]:
        for message in case["messages"]:
            message["text"] = ""
        for memory in case["gold_memories"]:
            memory["content"] = ""
        for query in case["queries"]:
            query["text"] = ""
    return stripped


async def run_memory_extraction_quality_benchmark(
    dataset: MemoryQualityDataset,
    *,
    baselines: Sequence[MemoryExtractionBaseline],
) -> dict[str, Any]:
    """Evaluate evidence/scope/role safety separately from semantic correctness.

    This layer deliberately does not infer that an extracted sentence is semantically
    correct merely because it cites a gold source. Content correctness still requires
    a human-labeled or independently judged live-model report.
    """

    selected = tuple(baselines)
    if not selected:
        raise ValueError("at least one extraction baseline is required")
    identities = [(baseline.name, baseline.version) for baseline in selected]
    if len(identities) != len(set(identities)):
        raise ValueError("memory extraction baseline identities must be unique")
    reports = [
        await _evaluate_extraction_baseline(dataset, baseline) for baseline in selected
    ]
    errors = [
        f"{report['name']}: {error}"
        for report in reports
        for error in report["correctness"]["errors"]
    ]
    scope_leakage = sum(
        report["aggregate"]["scope_leakage_count"] for report in reports
    )
    return {
        "result_schema_version": 1,
        "doppel_version": __version__,
        "generated_at": utc_now().isoformat(),
        "dataset": {
            "name": dataset.name,
            "version": dataset.dataset_version,
            "fingerprint": dataset.fingerprint,
            "case_count": len(dataset.cases),
            "message_count": sum(len(case.messages) for case in dataset.cases),
            "gold_memory_count": sum(len(case.gold_memories) for case in dataset.cases),
        },
        "measured_dimensions": [
            "gold_evidence_coverage",
            "supported_candidate_precision",
            "subject_attribution",
            "target_scope_accuracy",
            "ignored_evidence_writes",
            "agent_evidence_writes",
            "scope_isolation",
            "latency",
        ],
        "not_yet_measured": [
            "semantic_content_correctness",
            "memory_consolidation",
            "conflict_resolution",
            "answer_correctness",
            "llm_token_cost",
        ],
        "baselines": reports,
        "correctness": {
            "passed": not errors and scope_leakage == 0,
            "scope_leakage_count": scope_leakage,
            "errors": errors,
        },
    }


async def _evaluate_extraction_baseline(
    dataset: MemoryQualityDataset,
    baseline: MemoryExtractionBaseline,
) -> dict[str, Any]:
    case_reports: list[dict[str, Any]] = []
    errors: list[str] = []
    for case in dataset.cases:
        run = await baseline.run_case(dataset, case)
        report, case_errors = _evaluate_extraction_case(
            dataset, case, run.candidates, latency_ms=run.latency_ms
        )
        errors.extend(f"{case.name}: {error}" for error in case_errors)
        case_reports.append(report)
    candidate_reports = [
        candidate
        for case_report in case_reports
        for candidate in case_report["candidates"]
    ]
    gold_count = sum(report["gold_memory_count"] for report in case_reports)
    covered_gold = sum(report["covered_gold_memories"] for report in case_reports)
    candidate_count = len(candidate_reports)
    supported_count = sum(item["supported"] for item in candidate_reports)
    attributed = [item for item in candidate_reports if item["supported"]]
    latencies = [report["latency_ms"] for report in case_reports]
    aggregate = {
        "case_count": len(case_reports),
        "gold_memory_count": gold_count,
        "candidate_count": candidate_count,
        "gold_evidence_coverage": _rounded(
            covered_gold / gold_count if gold_count else 1.0
        ),
        "supported_candidate_precision": _rounded(
            supported_count / candidate_count if candidate_count else 1.0
        ),
        "subject_attribution_accuracy": _mean(
            float(item["subject_correct"]) for item in attributed
        ),
        "target_scope_accuracy": _mean(
            float(item["scope_correct"]) for item in attributed
        ),
        "unsupported_candidate_count": candidate_count - supported_count,
        "ignored_evidence_write_count": sum(
            item["uses_ignored_evidence"] for item in candidate_reports
        ),
        "agent_evidence_write_count": sum(
            item["uses_agent_evidence"] for item in candidate_reports
        ),
        "scope_leakage_count": sum(item["scope_leak"] for item in candidate_reports),
        "latency_ms": {
            "total": _rounded(sum(latencies)),
            "p50": _rounded(_percentile(latencies, 50)),
            "p95": _rounded(_percentile(latencies, 95)),
        },
    }
    return {
        "name": baseline.name,
        "version": baseline.version,
        "capabilities": {
            "extracts_memories": True,
            "consolidates_memories": False,
            "generates_answers": False,
        },
        "aggregate": aggregate,
        "cases": case_reports,
        "correctness": {
            "passed": not errors and aggregate["scope_leakage_count"] == 0,
            "scope_leakage_count": aggregate["scope_leakage_count"],
            "errors": errors,
        },
    }


def _evaluate_extraction_case(
    dataset: MemoryQualityDataset,
    case: QualityCase,
    candidates: Sequence[QualityExtractionCandidate],
    *,
    latency_ms: float,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    messages = {message.message_id: message for message in case.messages}
    scopes = {scope.name: scope for scope in dataset.scopes}
    ignored_ids = set(case.ignored_message_ids)
    candidate_ids = [candidate.candidate_id for candidate in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("extraction baseline returned duplicate candidate IDs")
    covered_gold: set[str] = set()
    rendered: list[dict[str, Any]] = []
    for candidate in candidates:
        source_ids = set(candidate.source_message_ids)
        unknown_sources = source_ids.difference(messages)
        if unknown_sources:
            errors.append(
                f"candidate {candidate.candidate_id} has unknown sources "
                f"{sorted(unknown_sources)}"
            )
        source_user_ids = {
            scopes[messages[source_id].scope].user_id
            for source_id in source_ids
            if source_id in messages
        }
        target = scopes.get(candidate.scope)
        scope_leak = target is None or any(
            user_id != target.user_id for user_id in source_user_ids
        )
        matching_gold = [
            memory
            for memory in case.gold_memories
            if source_ids.intersection(memory.evidence_message_ids)
        ]
        supported = bool(matching_gold)
        subject_correct = any(
            memory.subject == candidate.subject for memory in matching_gold
        )
        scope_correct = any(memory.scope == candidate.scope for memory in matching_gold)
        if subject_correct and scope_correct:
            covered_gold.update(
                memory.memory_key
                for memory in matching_gold
                if memory.subject == candidate.subject
                and memory.scope == candidate.scope
            )
        rendered.append(
            {
                **candidate.model_dump(mode="json"),
                "supported": supported,
                "subject_correct": subject_correct,
                "scope_correct": scope_correct,
                "uses_ignored_evidence": bool(source_ids.intersection(ignored_ids)),
                "uses_agent_evidence": any(
                    messages[source_id].actor in {Actor.AGENT, Actor.SYSTEM}
                    for source_id in source_ids
                    if source_id in messages
                ),
                "scope_leak": scope_leak,
                "matched_gold_memory_keys": [
                    memory.memory_key for memory in matching_gold
                ],
            }
        )
    return (
        {
            "name": case.name,
            "category": case.category,
            "gold_memory_count": len(case.gold_memories),
            "covered_gold_memories": len(covered_gold),
            "latency_ms": _rounded(latency_ms),
            "candidates": rendered,
        },
        errors,
    )


async def run_memory_quality_benchmark(
    dataset: MemoryQualityDataset,
    *,
    baselines: Sequence[MemoryQualityBaseline] | None = None,
) -> dict[str, Any]:
    selected = tuple(baselines or DEFAULT_BASELINES)
    if not selected:
        raise ValueError("at least one memory quality baseline is required")
    identities = [(baseline.name, baseline.version) for baseline in selected]
    if len(identities) != len(set(identities)):
        raise ValueError("memory quality baseline identities must be unique")

    message_count = sum(len(case.messages) for case in dataset.cases)
    query_count = sum(len(case.queries) for case in dataset.cases)
    gold_memory_count = sum(len(case.gold_memories) for case in dataset.cases)
    ignored_message_count = sum(len(case.ignored_message_ids) for case in dataset.cases)
    baseline_results: list[dict[str, Any]] = []
    all_errors: list[str] = []
    total_scope_leakage = 0
    for baseline in selected:
        result = await _evaluate_baseline(dataset, baseline)
        baseline_results.append(result)
        all_errors.extend(
            f"{baseline.name}: {error}" for error in result["correctness"]["errors"]
        )
        total_scope_leakage += result["correctness"]["scope_leakage_count"]
    if total_scope_leakage:
        all_errors.append(f"scope leakage candidates: {total_scope_leakage}")

    return {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "doppel_version": __version__,
        "generated_at": utc_now().isoformat(),
        "dataset": {
            "name": dataset.name,
            "version": dataset.dataset_version,
            "language": dataset.language,
            "fingerprint": dataset.fingerprint,
            "case_count": len(dataset.cases),
            "message_count": message_count,
            "query_count": query_count,
            "gold_memory_count": gold_memory_count,
            "ignored_message_count": ignored_message_count,
            "recent_window_size": dataset.recent_window_size,
        },
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "measured_dimensions": [
            "evidence_recall",
            "candidate_precision",
            "reciprocal_rank",
            "abstention",
            "forbidden_evidence",
            "scope_isolation",
            "redundancy",
            "context_characters",
            "retrieval_latency",
        ],
        "not_yet_measured": [
            "memory_extraction",
            "memory_consolidation",
            "conflict_resolution",
            "answer_correctness",
            "llm_token_cost",
        ],
        "baselines": baseline_results,
        "correctness": {
            "passed": not all_errors and total_scope_leakage == 0,
            "scope_leakage_count": total_scope_leakage,
            "errors": all_errors,
        },
    }


async def _evaluate_baseline(
    dataset: MemoryQualityDataset, baseline: MemoryQualityBaseline
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    errors: list[str] = []
    query_reports: list[dict[str, Any]] = []
    prepare_latencies: list[float] = []
    for case in dataset.cases:
        run = await baseline.run_case(dataset, case)
        prepare_latencies.append(run.prepare_latency_ms)
        unknown_queries = set(run.candidates).difference(
            query.name for query in case.queries
        )
        if unknown_queries:
            errors.append(
                f"{case.name}: baseline returned unknown queries {sorted(unknown_queries)}"
            )
        case_queries: list[dict[str, Any]] = []
        for query in case.queries:
            report, query_errors = _evaluate_query(
                case,
                query,
                run.candidates.get(query.name, []),
                latency_ms=run.query_latency_ms.get(query.name, 0.0),
            )
            errors.extend(f"{case.name}/{query.name}: {item}" for item in query_errors)
            case_queries.append(report)
            query_reports.append(report)
        cases.append(
            {
                "name": case.name,
                "category": case.category,
                "queries": case_queries,
            }
        )

    latencies = [item["latency_ms"] for item in query_reports]
    required_queries = [item for item in query_reports if item["required_group_count"]]
    abstention_queries = [
        item for item in query_reports if not item["required_group_count"]
    ]
    aggregate = {
        "query_count": len(query_reports),
        "required_query_count": len(required_queries),
        "abstention_query_count": len(abstention_queries),
        "macro_evidence_recall": _mean(
            item["evidence_recall"] for item in required_queries
        ),
        "macro_candidate_precision": _mean(
            item["candidate_precision"] for item in query_reports
        ),
        "mean_reciprocal_rank": _mean(
            item["reciprocal_rank"] for item in required_queries
        ),
        "abstention_accuracy": _mean(
            float(item["abstention_passed"]) for item in abstention_queries
        ),
        "forbidden_candidate_hits": sum(
            item["forbidden_candidate_hits"] for item in query_reports
        ),
        "scope_leakage_count": sum(
            item["scope_leakage_count"] for item in query_reports
        ),
        "redundant_relevant_candidates": sum(
            item["redundant_relevant_candidates"] for item in query_reports
        ),
        "average_candidates": _mean(
            float(item["retrieved_count"]) for item in query_reports
        ),
        "average_context_characters": _mean(
            float(item["context_characters"]) for item in query_reports
        ),
        "prepare_latency_ms": {
            "total": _rounded(sum(prepare_latencies)),
            "p50": _rounded(_percentile(prepare_latencies, 50)),
            "p95": _rounded(_percentile(prepare_latencies, 95)),
        },
        "query_latency_ms": {
            "p50": _rounded(_percentile(latencies, 50)),
            "p95": _rounded(_percentile(latencies, 95)),
            "max": _rounded(max(latencies, default=0.0)),
        },
    }
    scope_leakage = aggregate["scope_leakage_count"]
    return {
        "name": baseline.name,
        "version": baseline.version,
        "capabilities": {
            "extracts_memories": False,
            "consolidates_memories": False,
            "generates_answers": False,
        },
        "aggregate": aggregate,
        "cases": cases,
        "correctness": {
            "passed": not errors and scope_leakage == 0,
            "scope_leakage_count": scope_leakage,
            "errors": errors,
        },
    }


def _evaluate_query(
    case: QualityCase,
    query: QualityQuery,
    candidates: Sequence[QualityCandidate],
    *,
    latency_ms: float,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    messages = {message.message_id: message for message in case.messages}
    candidate_ids = [candidate.candidate_id for candidate in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("baseline returned duplicate candidate IDs")
    allowed_scopes = set(query.scopes)
    required_groups = [set(group.message_ids) for group in query.required_evidence]
    forbidden_ids = set(query.forbidden_message_ids)
    covered_groups: set[int] = set()
    relevant_candidates = 0
    forbidden_candidates = 0
    scope_leakage = 0
    first_relevant_rank = 0
    rendered_candidates: list[dict[str, Any]] = []
    for rank, candidate in enumerate(candidates, start=1):
        source_ids = set(candidate.source_message_ids)
        unknown_sources = source_ids.difference(messages)
        if unknown_sources:
            errors.append(
                f"candidate {candidate.candidate_id} has unknown sources "
                f"{sorted(unknown_sources)}"
            )
        source_scopes = {
            messages[source_id].scope
            for source_id in source_ids
            if source_id in messages
        }
        leaked = candidate.scope not in allowed_scopes or bool(
            source_scopes.difference(allowed_scopes)
        )
        scope_leakage += leaked
        matched_groups = [
            index
            for index, group in enumerate(required_groups)
            if group.intersection(source_ids)
        ]
        relevant = bool(matched_groups)
        if relevant:
            relevant_candidates += 1
            covered_groups.update(matched_groups)
            if not first_relevant_rank:
                first_relevant_rank = rank
        forbidden = bool(forbidden_ids.intersection(source_ids))
        forbidden_candidates += forbidden
        rendered_candidates.append(
            {
                **candidate.model_dump(mode="json"),
                "rank": rank,
                "relevant": relevant,
                "forbidden": forbidden,
                "scope_leak": leaked,
                "matched_evidence_groups": matched_groups,
            }
        )

    required_count = len(required_groups)
    retrieved_count = len(candidates)
    evidence_recall = len(covered_groups) / required_count if required_count else 1.0
    if retrieved_count:
        precision = relevant_candidates / retrieved_count
    else:
        precision = 1.0 if not required_count else 0.0
    reciprocal_rank = (
        1.0 / first_relevant_rank
        if first_relevant_rank
        else (1.0 if not required_count and not candidates else 0.0)
    )
    abstention_passed = not required_count and not candidates
    return (
        {
            "name": query.name,
            "query": query.text,
            "authorized_scopes": query.scopes,
            "required_group_count": required_count,
            "covered_group_count": len(covered_groups),
            "retrieved_count": retrieved_count,
            "relevant_candidate_count": relevant_candidates,
            "evidence_recall": _rounded(evidence_recall),
            "candidate_precision": _rounded(precision),
            "reciprocal_rank": _rounded(reciprocal_rank),
            "abstention_passed": abstention_passed,
            "forbidden_candidate_hits": forbidden_candidates,
            "scope_leakage_count": scope_leakage,
            "redundant_relevant_candidates": max(
                0, relevant_candidates - len(covered_groups)
            ),
            "context_characters": sum(len(item.content) for item in candidates),
            "latency_ms": _rounded(latency_ms),
            "candidates": rendered_candidates,
        },
        errors,
    )


def _message_candidate(
    message: QualityMessage, *, score: float | None = None
) -> QualityCandidate:
    return QualityCandidate(
        candidate_id=f"event:{message.message_id}",
        scope=message.scope,
        content=message.text,
        source_message_ids=[message.message_id],
        score=_rounded(score) if score is not None else None,
    )


def _recall_candidate(
    hit: RecallResult, scope_names_by_key: dict[str, str]
) -> QualityCandidate:
    if hit.scope is None:
        scope_name = ""
    else:
        scope_name = scope_names_by_key.get(hit.scope.scope_key, "")
    source_id = hit.source_message_id or hit.source_event_id
    if not source_id:
        raise RuntimeError(
            f"Doppel recall candidate lacks source identity: {hit.memory_id}"
        )
    return QualityCandidate(
        candidate_id=hit.memory_id or f"event:{source_id}",
        scope=scope_name,
        content=hit.fact,
        source_message_ids=[source_id],
        score=hit.similarity,
    )


def _features(text: str) -> Counter[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    features: Counter[str] = Counter()
    for word in _WORD_RE.findall(normalized):
        features[f"w:{word}"] += 2
    han = "".join(character for character in normalized if _HAN_RE.fullmatch(character))
    for character in han:
        features[f"c:{character}"] += 1
    for index in range(max(0, len(han) - 1)):
        features[f"b:{han[index : index + 2]}"] += 3
    return features


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(key, 0) for key, value in left.items())
    if not dot:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return dot / (left_norm * right_norm)


def _mean(values: Sequence[float] | Any) -> float:
    materialized = list(values)
    return _rounded(sum(materialized) / len(materialized)) if materialized else 0.0


def _percentile(values: Sequence[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile / 100 * len(ordered)) - 1)
    return ordered[index]


def _milliseconds_since(started: float) -> float:
    return (perf_counter() - started) * 1_000


def _rounded(value: float) -> float:
    return round(float(value), 4)


def _baseline_by_name(name: str) -> MemoryQualityBaseline:
    for baseline in DEFAULT_BASELINES:
        if baseline.name == name:
            return baseline
    raise ValueError(f"unknown memory quality baseline: {name}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument(
        "--baseline",
        action="append",
        choices=tuple(item.name for item in DEFAULT_BASELINES),
        help="Run only this baseline; repeat to select multiple baselines.",
    )
    parser.add_argument("--output")
    return parser


async def _main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    selected = (
        [_baseline_by_name(name) for name in args.baseline] if args.baseline else None
    )
    result = await run_memory_quality_benchmark(
        load_memory_quality_dataset(args.dataset), baselines=selected
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(f"memory quality result: {output}")
    else:
        sys.stdout.write(rendered)
    return 0 if result["correctness"]["passed"] else 1


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
