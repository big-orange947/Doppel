"""Synthetic reader/judge boundaries; no provider, network or benchmark claim.

Every row, context item and model response here is synthetic. The tests bind the
frozen comparison artifact, the reader/judge request contracts, deterministic
citation legality, cache/replay accounting and redaction without a live model.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from benchmarks import public_memory_answer_comparison as answer_module
from benchmarks.public_context_baseline import select_diagnostic_cases
from benchmarks.public_longmemeval import RuntimeCase, ScoringCase
from benchmarks.public_memory_answer_comparison import (
    COMPARISON_RUNNER,
    PROFILE_NAMES,
    READER_ITEM_FIELDS,
    ReaderOutput,
    _request_sha256,
    build_answer_plan,
    build_reader_request,
    build_rows,
    citation_audit,
    main,
    run_live,
    summarise_profiles,
)
from benchmarks.public_memory_comparison import encoded
from benchmarks.public_memory_pilot import build_manifest
from doppel_memory.intelligence import (
    StructuredGenerationRequest,
    StructuredOutputModel,
)
from doppel_memory.openai_compatible import OpenAICompatibleStructuredOutputConfig
from integrations.aml.contract import memory_scope

DATASET_NAMESPACE = "synthetic-answer-dataset"
RUN_NAMESPACE = "synthetic-answer-run"
SEED = 20261007
MAX_MESSAGES = 20
GOLD = "GOLD-ANSWER"
USAGE = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}


def synthetic_record(index: int) -> dict[str, Any]:
    return {
        "question_id": f"answer-case-{index}",
        "question_type": "single-session-user",
        "question": f"Question {index}: which option did we settle on?",
        "answer": f"{GOLD}-{index}",
        "question_date": "2024/01/09 09:30",
        "answer_session_ids": [f"session-{index}"],
        "haystack_session_ids": [f"session-{index}"],
        "haystack_dates": [f"2024/01/0{index + 1} 08:00"],
        "haystack_sessions": [
            [
                {
                    "role": "user",
                    "content": f"owner statement HISTORY_ONLY_SECRET_{index}",
                    "has_answer": True,
                },
                {
                    "role": "assistant",
                    "content": "I recommend the Go backend for that service.",
                    "has_answer": False,
                },
            ]
        ],
    }


@dataclass
class Fixture:
    records: list[dict[str, Any]]
    manifest: dict[str, Any]
    cases: list[tuple[RuntimeCase, ScoringCase]]
    comparison: dict[str, Any]
    dataset_path: Path
    manifest_path: Path
    comparison_path: Path
    comparison_sha256: str


def _item(
    scope_key: str,
    channel: str,
    memory_id: str,
    role: str,
    actor: str,
    authority: str,
    text: str,
    observed_at: str,
) -> dict[str, Any]:
    return {
        "channel": channel,
        "memory_id": memory_id,
        "scope_key": scope_key,
        "role": role,
        "actor": actor,
        "authority": authority,
        "text": text,
        "observed_at": observed_at,
        "temporal_status": None,
        "valid_from": None,
        "valid_to": None,
        "source_events": [f"event-{memory_id}"],
    }


def row_context(
    runtime: RuntimeCase, profile: str, *, index: int
) -> list[dict[str, Any]]:
    """Channel contents per profile; ids stay stable across profiles and cases."""
    scope = memory_scope(RUN_NAMESPACE, runtime.user_id)
    tag = runtime.user_id[:8]
    raw_items = [
        _item(
            scope.scope_key,
            "raw",
            f"mem-raw-{tag}-1",
            "user",
            "owner",
            "human_self",
            "The owner kept the appointment on Tuesday.",
            "2024-01-01T08:00:00+00:00",
        ),
        _item(
            scope.scope_key,
            "raw",
            f"mem-raw-{tag}-2",
            "assistant",
            "agent",
            "agent_output",
            "I recommend the Go backend for that service.",
            "2024-01-01T08:00:00+00:00",
        ),
    ]
    memory_items = [
        _item(
            scope.scope_key,
            "memory",
            f"mem-derived-{tag}-1",
            "derived-owner-memory",
            "owner",
            "human_self",
            "Owner appointment: Tuesday.",
            "2024-01-01T08:00:00+00:00",
        ),
        _item(
            scope.scope_key,
            "memory",
            f"mem-derived-{tag}-2",
            "derived-owner-memory",
            "owner",
            "human_self",
            "Owner preference: morning meetings.",
            "2024-01-01T08:00:00+00:00",
        ),
    ]
    if profile.startswith("raw"):
        items = raw_items
    elif profile.startswith("memory"):
        items = memory_items
    elif index == 1 and profile == "combined_vector":
        # Mirrors the opened artifact: this combined row shares the raw context.
        items = raw_items
    else:
        items = raw_items + memory_items
    return list(reversed(items)) if profile.endswith("reranked") else items


def build_comparison(
    manifest: dict[str, Any],
    cases: Sequence[tuple[RuntimeCase, ScoringCase]],
    manifest_sha256: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for profile in PROFILE_NAMES:
        for index, (runtime, scoring) in enumerate(cases):
            context = row_context(runtime, profile, index=index)
            rows.append(
                {
                    "case_id": scoring.case_id,
                    "profile": profile,
                    "packed_item_count": len(context),
                    "packed_context_bytes": len(encoded(context)),
                    "context": context,
                }
            )
    return {
        "runner": COMPARISON_RUNNER,
        "status": "complete",
        "manifest_fingerprint": manifest["manifest_fingerprint"],
        "ingestion_plan_fingerprint": "f" * 64,
        "input_sha256": {"manifest": manifest_sha256},
        "rows": rows,
    }


def fixture(tmp_path: Path) -> Fixture:
    records = [synthetic_record(index) for index in range(4)]
    dataset_bytes = json.dumps(records, ensure_ascii=False, indent=2).encode()
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_bytes(dataset_bytes)
    dataset_sha256 = hashlib.sha256(dataset_bytes).hexdigest()
    manifest = build_manifest(
        records,
        dataset_namespace=DATASET_NAMESPACE,
        run_namespace=RUN_NAMESPACE,
        source_sha256=dataset_sha256,
        seed=SEED,
        diagnostic_count=3,
        reserved_count=1,
        max_messages=MAX_MESSAGES,
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    cases = select_diagnostic_cases(records, manifest, source_sha256=dataset_sha256)
    comparison = build_comparison(
        manifest, cases, hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    )
    comparison_path = tmp_path / "comparison.json"
    comparison_path.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return Fixture(
        records=records,
        manifest=manifest,
        cases=cases,
        comparison=comparison,
        dataset_path=dataset_path,
        manifest_path=manifest_path,
        comparison_path=comparison_path,
        comparison_sha256=hashlib.sha256(comparison_path.read_bytes()).hexdigest(),
    )


def config(**overrides: Any) -> OpenAICompatibleStructuredOutputConfig:
    payload: dict[str, Any] = {
        "model": "fake-answer-model",
        "base_url": "https://example.invalid/v1",
        "schema_mode": "json_object",
        "max_completion_tokens": 2048,
        "max_tokens_parameter": "max_tokens",
        "temperature": 0.0,
        "thinking": "disabled",
        "timeout_seconds": 120.0,
    }
    payload.update(overrides)
    return OpenAICompatibleStructuredOutputConfig.model_validate(payload)


def plan_for(fx: Fixture, rows: Sequence[Any], **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "comparison_sha256": fx.comparison_sha256,
        "dataset_sha256": hashlib.sha256(fx.dataset_path.read_bytes()).hexdigest(),
        "provider_config": config(),
        "max_new_reader_calls": 18,
        "max_new_judge_calls": 18,
    }
    payload.update(overrides)
    return build_answer_plan(rows, fx.manifest, fx.comparison, **payload)


def default_responder(request: StructuredGenerationRequest) -> dict[str, Any]:
    if "reference_answer" in request.input:
        return {
            "answer_correct": True,
            "answer_rationale": "agrees with the reference answer",
            "citation_supported": True,
            "citation_rationale": "the cited text states the claim",
        }
    items = request.input["context_items"]
    return {
        "answer": f"According to {items[0]['memory_id']}, Tuesday.",
        "abstained": False,
        "cited_memory_ids": [items[0]["memory_id"]],
    }


class FakeProvider:
    """Deterministic structured-output stand-in; records every request."""

    def __init__(
        self,
        responder: Callable[[StructuredGenerationRequest], Mapping[str, Any]],
        *,
        name: str,
        version: str,
    ) -> None:
        self.name = name
        self.version = version
        self._responder = responder
        self.observer: Callable[[Mapping[str, int]], None] | None = None
        self.usage: Mapping[str, int] | None = None
        self.requests: list[StructuredGenerationRequest] = []

    async def generate(self, request: StructuredGenerationRequest) -> Mapping[str, Any]:
        self.requests.append(request)
        if self.usage is not None and self.observer is not None:
            self.observer(dict(self.usage))
        return self._responder(request)


class RecordingFactory:
    def __init__(
        self,
        responder: Callable[[StructuredGenerationRequest], Mapping[str, Any]],
        *,
        usage: Mapping[str, int] | None = USAGE,
        name: str = "fake-answer-model",
    ) -> None:
        self.responder = responder
        self.usage = usage
        self.name = name
        self.providers: list[FakeProvider] = []

    def __call__(
        self,
        config: OpenAICompatibleStructuredOutputConfig,
        api_key: str,
        usage_observer: Callable[[Mapping[str, int]], None],
    ) -> StructuredOutputModel:
        provider = FakeProvider(
            self.responder,
            name=self.name,
            version="1." + config.generation_fingerprint[:16],
        )
        provider.observer = usage_observer
        provider.usage = self.usage
        self.providers.append(provider)
        return provider

    @property
    def calls(self) -> int:
        return sum(len(provider.requests) for provider in self.providers)


def setup(tmp_path: Path) -> tuple[Fixture, list[Any], dict[str, Any]]:
    fx = fixture(tmp_path)
    rows = build_rows(fx.comparison, fx.cases, fx.manifest)
    return fx, rows, plan_for(fx, rows)


async def live(
    fx: Fixture,
    rows: Sequence[Any],
    plan: Mapping[str, Any],
    factory: RecordingFactory,
    *,
    run_dir: Path,
    api_key: str = "",
    cache_only: bool = False,
) -> dict[str, Any]:
    return await run_live(
        rows,
        fx.manifest,
        plan,
        run_dir=run_dir,
        api_key=api_key,
        cache_only=cache_only,
        provider_factory=factory,
    )


def test_reader_requests_ignore_gold_labels_and_evidence(tmp_path: Path) -> None:
    fx, rows, _ = setup(tmp_path)
    baseline = [_request_sha256(build_reader_request(row)) for row in rows]
    altered = []
    for record in fx.records:
        changed = deepcopy(record)
        changed["answer"] = "A DIFFERENT GOLD ANSWER"
        changed["question_type"] = "temporal-reasoning"
        changed["answer_session_ids"] = []
        changed["haystack_sessions"][0][0]["has_answer"] = False
        changed["haystack_sessions"][0][1]["has_answer"] = True
        altered.append(changed)
    altered_cases = select_diagnostic_cases(
        altered, fx.manifest, source_sha256=fx.manifest["source_sha256"]
    )
    altered_rows = build_rows(fx.comparison, altered_cases, fx.manifest)
    assert [
        _request_sha256(build_reader_request(row)) for row in altered_rows
    ] == baseline
    assert "GOLD" not in json.dumps(
        [build_reader_request(row).input for row in rows], ensure_ascii=False
    )


def test_reader_request_carries_question_time_and_visible_context(
    tmp_path: Path,
) -> None:
    fx, rows, _ = setup(tmp_path)
    row = rows[0]
    request = build_reader_request(row)
    assert request.input["question"] == fx.cases[0][0].query.query
    assert request.input["question_reference_time"] == "2024-01-09T09:30:00+00:00"
    assert [item["memory_id"] for item in request.input["context_items"]] == [
        item["memory_id"] for item in row.context
    ]
    assert set(request.input["context_items"][0]) == set(READER_ITEM_FIELDS)
    payload = json.dumps(request.input, ensure_ascii=False)
    assert "HISTORY_ONLY_SECRET" not in payload
    assert row.context[0]["scope_key"] not in payload
    assert row.case_id not in payload
    assert row.profile not in payload
    assert request.instructions == answer_module.READER_INSTRUCTIONS
    assert request.output_schema == answer_module.READER_SCHEMA


async def test_reader_only_sees_its_own_row(tmp_path: Path) -> None:
    fx, rows, plan = setup(tmp_path)
    factory = RecordingFactory(default_responder)
    report = await live(fx, rows, plan, factory, run_dir=tmp_path / "run")
    by_ids = {tuple(item["memory_id"] for item in row.context) for row in rows}
    seen = factory.providers[0].requests
    assert seen
    for request in seen:
        assert (
            tuple(item["memory_id"] for item in request.input["context_items"])
            in by_ids
        )
        assert all("scope_key" not in item for item in request.input["context_items"])
    assert report["distinct_reader_requests"] == 17
    assert report["logical_rows"] == 18


def test_assistant_reply_stays_attributed_context(tmp_path: Path) -> None:
    fx, rows, _ = setup(tmp_path)
    row = next(
        row
        for row in rows
        if row.profile == "raw_vector" and row.case_id == fx.cases[0][1].case_id
    )
    assistant = next(
        item for item in row.context if item["authority"] == "agent_output"
    )
    request = build_reader_request(row)
    sent = next(
        item
        for item in request.input["context_items"]
        if item["memory_id"] == assistant["memory_id"]
    )
    assert sent["role"] == "assistant"
    assert sent["authority"] == "agent_output"


async def test_assistant_citation_reported_without_authority_upgrade(
    tmp_path: Path,
) -> None:
    fx, rows, plan = setup(tmp_path)
    memory_only_ids = {
        item["memory_id"]
        for row in rows
        if row.profile.startswith("memory")
        for item in row.context
    }
    raw_assistant_ids = {
        item["memory_id"]
        for row in rows
        if row.profile == "raw_vector"
        for item in row.context
        if item["authority"] == "agent_output"
    }
    assert raw_assistant_ids and not raw_assistant_ids & memory_only_ids

    def responder(request: StructuredGenerationRequest) -> Mapping[str, Any]:
        if "reference_answer" in request.input:
            return default_responder(request)
        cited = [
            item["memory_id"]
            for item in request.input["context_items"]
            if item["authority"] == "agent_output"
        ]
        return {
            "answer": "You previously recommended the Go backend.",
            "abstained": False,
            "cited_memory_ids": cited,
        }

    factory = RecordingFactory(responder)
    report = await live(fx, rows, plan, factory, run_dir=tmp_path / "run")
    raw_rows = [row for row in report["rows"] if row["profile"] == "raw_vector"]
    assert raw_rows[0]["citation_check"]["legal"] is True
    assistant_cited = [
        item
        for row in raw_rows
        for item in row["cited_items"]
        if item["authority"] == "agent_output"
    ]
    assert assistant_cited
    assert all(item["role"] == "assistant" for item in assistant_cited)
    judge_requests = factory.providers[1].requests
    assert any(
        item["authority"] == "agent_output"
        for request in judge_requests
        for item in request.input["cited_items"]
    )
    assert "HISTORY_ONLY_SECRET" not in json.dumps(
        [request.input for request in judge_requests], ensure_ascii=False
    )


async def test_illegal_cross_row_and_cross_user_citations(tmp_path: Path) -> None:
    fx, rows, plan = setup(tmp_path)
    row = next(
        row
        for row in rows
        if row.profile == "memory_vector" and row.case_id == fx.cases[0][1].case_id
    )
    valid = row.context[0]["memory_id"]
    other_case = next(
        item["memory_id"]
        for other in rows
        if other.case_id == fx.cases[1][1].case_id
        for item in other.context
    )
    other_profile = next(
        item["memory_id"]
        for other in rows
        if other.profile == "combined_vector" and other.case_id == row.case_id
        for item in other.context
        if item["memory_id"] != valid
    )
    invented = "mem-invented-does-not-exist"

    def responder(request: StructuredGenerationRequest) -> Mapping[str, Any]:
        if "reference_answer" in request.input:
            return default_responder(request)
        if request.input["context_items"][0]["memory_id"] == valid:
            return {
                "answer": "Tuesday.",
                "abstained": False,
                "cited_memory_ids": [valid, other_case, other_profile, invented],
            }
        return default_responder(request)

    factory = RecordingFactory(responder)
    report = await live(fx, rows, plan, factory, run_dir=tmp_path / "run")
    target = next(
        entry
        for entry in report["rows"]
        if entry["profile"] == "memory_vector" and entry["case_id"] == row.case_id
    )
    check = target["citation_check"]
    assert check["legal"] is False
    assert check["illegal_ids"] == [other_case, other_profile, invented]
    assert check["cited_unique_count"] == 4
    assert (summary := report["profile_summary"]["memory_vector"])
    assert summary["citation_legal"] == "2/3"
    audit = citation_audit(row.context, [valid, valid])
    assert audit["legal"] is True
    assert audit["duplicate_ids"] == [valid]


async def test_answer_correct_and_citation_support_are_independent(
    tmp_path: Path,
) -> None:
    fx, rows, plan = setup(tmp_path)

    def responder(request: StructuredGenerationRequest) -> Mapping[str, Any]:
        if "reference_answer" in request.input:
            return {
                "answer_correct": True,
                "answer_rationale": "agrees with the reference answer",
                "citation_supported": False,
                "citation_rationale": "the cited text does not state the claim",
            }
        return default_responder(request)

    factory = RecordingFactory(responder)
    report = await live(fx, rows, plan, factory, run_dir=tmp_path / "run")
    assert all(row["judge"]["answer_correct"] is True for row in report["rows"])
    assert all(row["judge"]["citation_supported"] is False for row in report["rows"])
    for profile in PROFILE_NAMES:
        summary = report["profile_summary"][profile]
        assert summary["answer_correct"] == "3/3"
        assert summary["citation_supported"] == "0/3"
        assert summary["counts"]["judged_rows"] == 3


async def test_cache_reuse_and_prompt_or_schema_invalidation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fx, rows, plan = setup(tmp_path)
    plan = plan_for(fx, rows, max_new_reader_calls=60, max_new_judge_calls=60)
    run_dir = tmp_path / "run"
    first = RecordingFactory(default_responder)
    report = await live(fx, rows, plan, first, run_dir=run_dir)
    assert report["status"] == "complete"
    assert report["distinct_reader_requests"] == 17
    assert report["budget"]["new_reader_calls"] == 17
    # The judge input is smaller, so identical answers and citations deduplicate.
    assert report["distinct_judge_requests"] == 12
    assert report["budget"]["new_judge_calls"] == 12
    assert len(first.providers[0].requests) == 17

    second = RecordingFactory(default_responder)
    replay = await live(fx, rows, plan, second, run_dir=run_dir)
    assert second.calls == 0
    assert replay["budget"]["new_calls_total"] == 0
    assert replay["cache"]["reader"]["cache_hits_this_instance"] == 17
    assert [row["reader"]["answer"] for row in replay["rows"]] == [
        row["reader"]["answer"] for row in report["rows"]
    ]

    monkeypatch.setattr(
        answer_module,
        "READER_INSTRUCTIONS",
        answer_module.READER_INSTRUCTIONS + "\nKeep ids stable.",
    )
    third = RecordingFactory(default_responder)
    changed_prompt = await live(fx, rows, plan, third, run_dir=run_dir)
    assert len(third.providers[0].requests) == 17
    assert third.providers[1].requests == []
    assert changed_prompt["budget"]["new_reader_calls"] == 17
    assert changed_prompt["budget"]["new_judge_calls"] == 0

    monkeypatch.setattr(
        answer_module,
        "READER_SCHEMA",
        {**answer_module.READER_SCHEMA, "title": "MemoryAnswerV2"},
    )
    fourth = RecordingFactory(default_responder)
    changed_schema = await live(fx, rows, plan, fourth, run_dir=run_dir)
    assert len(fourth.providers[0].requests) == 17
    assert changed_schema["budget"]["new_reader_calls"] == 17


def test_generation_parameters_change_the_provider_identity() -> None:
    assert (
        config(temperature=0.0).generation_fingerprint
        != config(temperature=0.5).generation_fingerprint
    )
    assert (
        config(max_completion_tokens=2048).generation_fingerprint
        != config(max_completion_tokens=1024).generation_fingerprint
    )


async def test_changed_plan_cannot_reuse_a_bound_run_directory(
    tmp_path: Path,
) -> None:
    fx, rows, plan = setup(tmp_path)
    run_dir = tmp_path / "run"
    factory = RecordingFactory(default_responder)
    await live(fx, rows, plan, factory, run_dir=run_dir)
    changed = plan_for(fx, rows, max_new_reader_calls=19)
    with pytest.raises(ValueError, match="different plan"):
        await live(
            fx, rows, changed, RecordingFactory(default_responder), run_dir=run_dir
        )


async def test_failed_request_is_preserved_and_resumed_without_double_charge(
    tmp_path: Path,
) -> None:
    fx, rows, plan = setup(tmp_path)
    run_dir = tmp_path / "run"
    target = next(
        row
        for row in rows
        if row.profile == "memory_vector" and row.case_id == fx.cases[2][1].case_id
    )
    marker = target.context[0]["memory_id"]

    def flaky(request: StructuredGenerationRequest) -> Mapping[str, Any]:
        if (
            "reference_answer" not in request.input
            and request.input["context_items"][0]["memory_id"] == marker
        ):
            raise RuntimeError("PROVIDER-SECRET-TEXT")
        return default_responder(request)

    first = RecordingFactory(flaky)
    partial = await live(fx, rows, plan, first, run_dir=run_dir)
    assert partial["status"] == "partial"
    failed = [row for row in partial["rows"] if row["reader"]["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["reader"]["failure_class"] == "provider_attempt_failed"
    assert failed[0]["judge"]["status"] == "not_run"
    assert failed[0]["judge"]["failure_class"] == "reader_failed"
    assert "PROVIDER-SECRET-TEXT" not in json.dumps(partial, ensure_ascii=False)

    second = RecordingFactory(default_responder)
    resumed = await live(fx, rows, plan, second, run_dir=run_dir)
    assert resumed["status"] == "complete"
    assert len(second.providers[0].requests) == 1
    assert resumed["budget"]["new_reader_calls"] == 1
    assert resumed["budget"]["new_judge_calls"] == 1
    first_answers = {
        (row["profile"], row["case_id"]): row["reader"]["answer"]
        for row in partial["rows"]
        if row["reader"]["status"] == "completed"
    }
    replayed = [
        row for row in resumed["rows"] if row["reader"]["execution"] == "cache_hit"
    ]
    assert len(replayed) == 16
    assert all(
        row["reader"]["answer"] == first_answers[(row["profile"], row["case_id"])]
        for row in replayed
    )
    resumed_target = next(
        row
        for row in resumed["rows"]
        if row["profile"] == target.profile and row["case_id"] == target.case_id
    )
    assert resumed_target["reader"]["execution"] == "provider_completed"
    assert resumed_target["judge"]["status"] == "completed"


async def test_invalid_output_and_missing_usage_are_recorded(
    tmp_path: Path,
) -> None:
    fx, rows, plan = setup(tmp_path)
    run_dir = tmp_path / "run"

    def invalid(request: StructuredGenerationRequest) -> Mapping[str, Any]:
        if "reference_answer" in request.input:
            return default_responder(request)
        return {"answer": "missing the boolean and citation list"}

    factory = RecordingFactory(invalid, usage=None)
    report = await live(fx, rows, plan, factory, run_dir=run_dir)
    assert report["status"] == "partial"
    failed_classes = {row["reader"]["failure_class"] for row in report["rows"]}
    assert failed_classes == {
        "invalid_structured_output",
        "duplicate_of_failed_request",
    }
    assert report["budget"]["reader"]["calls_without_usage"] == 17
    assert report["budget"]["reader"]["reported_tokens"] is None
    assert report["budget"]["reader"]["token_accounting_complete"] is False

    def timeout(request: StructuredGenerationRequest) -> Mapping[str, Any]:
        if "reference_answer" in request.input:
            return default_responder(request)
        raise TimeoutError("provider timed out")

    timed_out = await live(
        fx, rows, plan, RecordingFactory(timeout), run_dir=tmp_path / "run2"
    )
    timeout_classes = {row["reader"]["failure_class"] for row in timed_out["rows"]}
    assert timeout_classes == {
        "provider_attempt_failed",
        "duplicate_of_failed_request",
    }
    assert "provider timed out" not in json.dumps(timed_out, ensure_ascii=False)


async def test_cache_only_reproduces_answers_without_provider_or_key(
    tmp_path: Path,
) -> None:
    fx, rows, plan = setup(tmp_path)
    run_dir = tmp_path / "run"
    first = RecordingFactory(default_responder)
    report = await live(fx, rows, plan, first, run_dir=run_dir, api_key="SECRET-KEY")

    def forbidden(request: StructuredGenerationRequest) -> Mapping[str, Any]:
        raise AssertionError("cache-only replay must not reach the provider")

    replay_factory = RecordingFactory(forbidden, usage=None)
    replay = await live(
        fx, rows, plan, replay_factory, run_dir=run_dir, cache_only=True
    )
    assert replay_factory.calls == 0
    assert replay["mode"] == "live-cache-only-replay"
    assert replay["budget"]["new_calls_total"] == 0
    assert replay["status"] == report["status"]
    assert [row["reader"]["answer"] for row in replay["rows"]] == [
        row["reader"]["answer"] for row in report["rows"]
    ]
    assert [row["judge"]["answer_correct"] for row in replay["rows"]] == [
        row["judge"]["answer_correct"] for row in report["rows"]
    ]
    assert "SECRET-KEY" not in json.dumps(report, ensure_ascii=False)
    assert "SECRET-KEY" not in json.dumps(replay, ensure_ascii=False)


async def test_cache_only_without_entries_fails_closed(tmp_path: Path) -> None:
    fx, rows, plan = setup(tmp_path)

    def forbidden(request: StructuredGenerationRequest) -> Mapping[str, Any]:
        raise AssertionError("cache-only replay must not reach the provider")

    report = await live(
        fx,
        rows,
        plan,
        RecordingFactory(forbidden),
        run_dir=tmp_path / "empty",
        cache_only=True,
    )
    assert report["status"] == "partial"
    failed_classes = {row["reader"]["failure_class"] for row in report["rows"]}
    assert failed_classes <= {"missing_cached_output", "duplicate_of_failed_request"}
    assert "missing_cached_output" in failed_classes
    assert report["budget"]["reader"]["attempts_reserved"] == 0
    assert report["budget"]["judge"]["attempts_reserved"] == 0


def test_citation_audit_rejects_unseen_ids() -> None:
    context = [
        {"memory_id": "mem-a"},
        {"memory_id": "mem-b"},
    ]
    audit = citation_audit(context, ["mem-a", "mem-c"])
    assert audit == {
        "legal": False,
        "illegal_ids": ["mem-c"],
        "duplicate_ids": [],
        "cited_item_count": 2,
        "cited_unique_count": 2,
        "allowed_item_count": 2,
    }


def test_reader_output_validation() -> None:
    assert ReaderOutput.model_validate(
        {"answer": "a", "abstained": False, "cited_memory_ids": ["x"]}
    ).cited_memory_ids == ["x"]
    with pytest.raises(ValidationError):
        ReaderOutput.model_validate({"answer": "a", "abstained": False})
    with pytest.raises(ValidationError):
        ReaderOutput.model_validate(
            {"answer": "  ", "abstained": False, "cited_memory_ids": []}
        )


def test_rows_reject_incomplete_or_mismatched_artifacts(tmp_path: Path) -> None:
    fx, rows, _ = setup(tmp_path)
    assert len(rows) == 18
    broken = deepcopy(fx.comparison)
    broken["rows"][0]["packed_context_bytes"] += 1
    with pytest.raises(ValueError, match="context is incomplete"):
        build_rows(broken, fx.cases, fx.manifest)
    missing = deepcopy(fx.comparison)
    missing["rows"] = missing["rows"][:-1]
    with pytest.raises(ValueError, match="row binding invalid"):
        build_rows(missing, fx.cases, fx.manifest)
    altered = deepcopy(fx.comparison)
    altered["manifest_fingerprint"] = "0" * 64
    with pytest.raises(ValueError, match="row binding invalid"):
        build_rows(altered, fx.cases, fx.manifest)


def test_profile_summary_uses_explicit_denominators() -> None:
    rows = [
        {
            "profile": PROFILE_NAMES[0],
            "reader": {"status": "completed", "abstained": False},
            "judge": {
                "status": "completed",
                "answer_correct": True,
                "citation_supported": False,
            },
            "citation_check": {"legal": True},
        },
        {
            "profile": PROFILE_NAMES[0],
            "reader": {"status": "failed", "abstained": None},
            "judge": {
                "status": "not_run",
                "answer_correct": None,
                "citation_supported": None,
            },
            "citation_check": {"legal": False},
        },
    ]
    summary = summarise_profiles(rows)[PROFILE_NAMES[0]]
    assert summary["reader_completed"] == "1/2"
    assert summary["answer_correct"] == "1/1"
    assert summary["citation_legal"] == "1/1"
    assert summary["citation_supported"] == "0/1"
    assert summary["judge_completed"] == "1/2"


def _cli_argv(fx: Fixture, tmp_path: Path, output: Path, *extra: str) -> list[str]:
    return [
        "public_memory_answer_comparison",
        "--dataset",
        str(fx.dataset_path),
        "--manifest",
        str(fx.manifest_path),
        "--comparison",
        str(fx.comparison_path),
        "--comparison-sha256",
        fx.comparison_sha256,
        "--output",
        str(output),
        "--run-dir",
        str(tmp_path / "run"),
        *extra,
    ]


def test_cli_preflight_writes_no_provider_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fx = fixture(tmp_path)
    output = tmp_path / "out-preflight.json"
    monkeypatch.setattr(sys, "argv", _cli_argv(fx, tmp_path, output))
    assert main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["mode"] == "preflight-no-provider"
    assert report["logical_rows"] == 18
    assert report["distinct_reader_requests"] == 17
    assert report["qa_metrics_available"] is False
    assert report["api_key_read"] is False
    assert not (tmp_path / "run").exists()
    assert "output:" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main()
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_cli_rejects_a_mismatched_comparison_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fx = fixture(tmp_path)
    output = tmp_path / "out.json"
    argv = _cli_argv(fx, tmp_path, output)
    argv[argv.index("--comparison-sha256") + 1] = "0" * 64
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        main()
    assert not output.exists()


def test_cli_cache_only_never_requires_a_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fx = fixture(tmp_path)
    monkeypatch.delenv("DOPPEL_TEST_ANSWER_KEY", raising=False)
    output = tmp_path / "out-cache-only.json"
    monkeypatch.setattr(
        sys,
        "argv",
        _cli_argv(
            fx,
            tmp_path,
            output,
            "--live",
            "--cache-only",
            "--api-key-env",
            "DOPPEL_TEST_ANSWER_KEY",
        ),
    )
    assert main() == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["mode"] == "live-cache-only-replay"
    assert report["status"] == "partial"
    assert report["api_key_read"] is False
    assert report["budget"]["new_calls_total"] == 0
    failed_classes = {row["reader"]["failure_class"] for row in report["rows"]}
    assert failed_classes <= {"missing_cached_output", "duplicate_of_failed_request"}
    assert "missing_cached_output" in failed_classes
    assert "DOPPEL_TEST_ANSWER_KEY" in json.dumps(report)
    assert not (tmp_path / "run" / "reader-provider-cache").exists()
