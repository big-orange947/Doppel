from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_source_aware_diagnostic as runner
from benchmarks.public_memory_answer_comparison import AnswerRow, _request_sha256
from doppel_memory.models import MemoryScope, RecallResult
from tests.test_public_memory_passage_diagnostic import item


def test_three_frozen_arms_no_question_rules_and_six_paid_call_cap():
    args = SimpleNamespace(phase="answers")
    parent = {"plan": {"schema": "synthetic"}}
    plan = runner.make_plan(args, {}, parent)
    assert list(plan["arms"]) == [
        "content_only",
        "source_metadata",
        "source_metadata_mmr",
    ]
    assert plan["arms"]["source_metadata_mmr"]["diversity_weight"] == 0.15
    assert all(stage["max_calls"] == 3 for stage in plan["stages"].values())
    assert plan["candidate_limit"] == 80 and plan["context_byte_limit"] == 24000
    assert plan["tested_arm"] == "source_metadata_mmr"


@pytest.mark.asyncio
async def test_every_arm_gets_same_snapshot_and_immutable_scope():
    scope = MemoryScope(user_id="owner", agent_id="a")
    candidate = RecallResult(scope=scope, memory_id="id", fact="original")
    strategy = runner.SavedCandidates([candidate])
    first = await strategy.search(None, "generic", [scope], limit=80)
    first[0].fact = "mutated"
    second = await strategy.search(None, "generic", [scope], limit=80)
    assert second[0].fact == "original"
    with pytest.raises(ValueError):
        await strategy.search(
            None, "generic", [MemoryScope(user_id="other", agent_id="a")]
        )


def test_baseline_reuse_requires_exact_reader_request_not_just_context_score():
    runtime = SimpleNamespace(
        query=SimpleNamespace(
            query="generic", reference_time=datetime(2026, 1, 1, tzinfo=UTC)
        )
    )
    scoring = SimpleNamespace(answer="PRIVATE_GOLD")
    context = [item()]
    row = {"case_id": "id", "context": context}
    request = runner.reader_request(
        AnswerRow(0, "id", "content_only", runtime, scoring, tuple(context))
    )
    old_contexts = {"rows": [{**row, "profile": "saved_source_passages_fit"}]}
    previous = {
        "case_id": "id",
        "profile": "saved_source_passages_fit",
        "reader": {"request_sha256": _request_sha256(request)},
        "grade": {"answer_correct": False, "rationale": "synthetic"},
    }
    old_qa = {"rows": [previous]}
    result = runner.reused_baseline(row, (runtime, scoring), old_contexts, old_qa)
    assert result["new_calls"] == 0 and result["grade"]["answer_correct"] is False
    old_qa["rows"][0]["reader"]["request_sha256"] = "different"
    with pytest.raises(ValueError, match="Reader"):
        runner.reused_baseline(row, (runtime, scoring), old_contexts, old_qa)
