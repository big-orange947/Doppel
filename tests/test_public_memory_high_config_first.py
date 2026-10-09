import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from benchmarks.public_longmemeval import QueryInput, RuntimeCase, ScoringCase
from benchmarks.public_memory_answer_comparison import AnswerRow
from benchmarks.public_memory_high_config_first import (
    build_plan,
    persisted_generation,
    reader_request,
)
from benchmarks.public_memory_task_accuracy import Grade
from doppel_memory.intelligence import StructuredGenerationRequest
from doppel_memory.models import MemoryScope
from doppel_memory.query import PersonalMemoryCountResult


def row():
    runtime = RuntimeCase(
        "user",
        (),
        QueryInput("user", "generic question", datetime(2026, 1, 1, tzinfo=UTC)),
    )
    scoring = ScoringCase(
        "private-case-id", "private-category", False, "GOLD_NEVER_IN_RUNTIME", (), ()
    )
    return AnswerRow(0, scoring.case_id, "private-profile", runtime, scoring, ())


def test_reader_excludes_gold_and_aggregation_not_synthetic_memory():
    aggregation = PersonalMemoryCountResult(status="exact", value=4, observed_records=9)
    request = reader_request(
        row(), SimpleNamespace(base=SimpleNamespace(count=aggregation, complete=True))
    )
    text = request.model_dump_json()
    assert "GOLD_NEVER_IN_RUNTIME" not in text
    assert "private-case-id" not in text
    assert "private-profile" not in text
    assert request.input["context_items"] == []
    assert request.input["retrieval_aggregation"]["value"] == 4


def test_plan_no_reference_and_freezes_all_stage_budgets():
    schema = {"plan": {"source": {"relation_names": ["OWNS"]}}, "definitions": []}
    reranker = SimpleNamespace(report=lambda: {"name": "fake", "version": "1"})
    plan = build_plan(
        {},
        row().runtime,
        MemoryScope(user_id="user", agent_id="agent"),
        schema,
        "corpus",
        {},
        reranker,
    )
    assert sum(s["max_calls"] for s in plan["stages"].values()) == 5
    assert "GOLD_NEVER_IN_RUNTIME" not in json.dumps(plan)
    assert plan["item_limit"] == 20
    assert plan["context_byte_limit"] == 24000


@pytest.mark.asyncio
async def test_preserves_failed_stage_and_never_retries(tmp_path):
    calls = []

    class Failing:
        async def generate(self, request):
            calls.append(request)
            raise ValueError("secret provider text")

    path = tmp_path / "stage.json"
    request = StructuredGenerationRequest(
        instructions="data", input={}, output_schema=Grade.model_json_schema()
    )
    with pytest.raises(ValueError):
        await persisted_generation(Failing(), request, Grade, path)
    frozen = path.read_bytes()
    assert b"secret provider text" not in frozen
    with pytest.raises(ValueError, match="must not be silently retried"):
        await persisted_generation(Failing(), request, Grade, path)
    assert len(calls) == 1
    assert path.read_bytes() == frozen


@pytest.mark.asyncio
async def test_replay_failure_does_not_overwrite_completed_checkpoint(tmp_path):
    class Model:
        async def generate(self, request):
            return {"answer_correct": True, "rationale": "reason"}

    class Failure:
        async def generate(self, request):
            raise ValueError("cache broken")

    path = tmp_path / "stage.json"
    request = StructuredGenerationRequest(
        instructions="data", input={}, output_schema=Grade.model_json_schema()
    )
    first = await persisted_generation(Model(), request, Grade, path)
    frozen = path.read_bytes()
    repeated = await persisted_generation(Model(), request, Grade, path)
    assert first == repeated
    with pytest.raises(ValueError):
        await persisted_generation(Failure(), request, Grade, path)
    assert path.read_bytes() == frozen
