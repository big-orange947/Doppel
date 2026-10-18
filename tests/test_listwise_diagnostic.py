from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_listwise_diagnostic as runner
from benchmarks.public_memory_answer_comparison import _request_sha256
from doppel_memory.models import FactAuthority, MemoryScope


def generation():
    from datetime import UTC, datetime

    snippet = SimpleNamespace(
        memory_id="private-id",
        evidence_id="private-source",
        text="original text",
        actor="agent",
        authority=FactAuthority.AGENT_OUTPUT,
        at=datetime(2026, 1, 1, tzinfo=UTC),
        similarity=0.5,
    )
    return runner.source_request(
        "generic question",
        MemoryScope(user_id="private-owner", agent_id="a"),
        [snippet],
    )


def test_plan_fixed_small_budget_no_mmr_or_graph_and_request_binding():
    certificate = {"source_request_bytes": 50000, "source_request_sha256": "frozen"}
    plan = runner.make_plan({}, [certificate], "synthetic")
    assert sum(s["max_calls"] for s in plan["stages"].values()) == 12
    assert plan["diversity_weight"] == 0 and plan["graph_calls"] == 0
    assert plan["publication_ready"] is False
    assert plan["source_limit"] == 20 and plan["passage_limit"] == 80
    assert plan["certificates"] == [certificate]


def test_source_request_attribution_no_persistent_ids_or_gold():
    value = generation()
    assert "private-" not in value.model_dump_json()
    content = json.loads(value.input["items"][0]["content"])
    assert (
        content["authority"] == "agent_output"
        and content["speaker_role"] == "assistant"
    )
    assert set(value.input) == {"question", "items"}
    assert runner.request_bytes(value) > len(content["source_text"])


def test_oversize_preflight_rejected():
    with pytest.raises(ValueError, match="byte cap"):
        runner.make_plan({}, [{"source_request_bytes": 500001}], "synthetic")


@pytest.mark.asyncio
async def test_source_request_change_stops_before_paid_call(tmp_path):
    class Model:
        name, version = "fake", "1"
        calls = 0

        async def generate(self, request):
            self.calls += 1
            return {"ordered_ids": ["candidate-0"]}

    model = Model()
    audited = runner.AuditedRankModel(model, tmp_path)
    audited.expected_source_sha = "different"
    with pytest.raises(ValueError, match="differs"):
        await audited.generate(generation())
    assert model.calls == 0 and not list(tmp_path.iterdir())
    audited.expected_source_sha = _request_sha256(generation())
    await audited.generate(generation())
    assert model.calls == 1 and len(list(tmp_path.iterdir())) == 1


@pytest.mark.asyncio
async def test_provider_failure_still_has_preawait_receipt(tmp_path):
    class Broken:
        name, version = "fake", "1"

        async def generate(self, request):
            raise RuntimeError("offline")

    audited = runner.AuditedRankModel(Broken(), tmp_path)
    with pytest.raises(RuntimeError):
        await audited.generate(generation())
    assert len(list(tmp_path.iterdir())) == 1
