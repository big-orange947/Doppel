"""Frozen control runner checks; fake reviewers are not semantic validation."""

import json

import pytest

from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.source_attribution_controls import (
    DATASET,
    PROFILES,
    BoundModel,
    Probe,
    apply,
    execute,
    prepare,
)
from doppel_memory import (
    OpenAICompatibleStructuredOutputConfig,
    StructuredGenerationRequest,
)


def dataset():
    return json.loads(DATASET.read_text(encoding="utf-8"))


async def test_preflight_freezes_topology_and_excludes_expected_labels():
    data = dataset()
    plan = await prepare(data, OpenAICompatibleStructuredOutputConfig(model="fixture"))
    assert sum(map(len, plan["requests"].values())) == plan["max_calls"] == 12
    for case in data["cases"]:
        for profile in PROFILES:
            probe = Probe()
            await apply(case, profile, probe)
            for request in probe.requests:
                encoded = json.dumps(request, ensure_ascii=False)
                assert case["rubric"] not in encoded
                assert "expected_verdicts" not in encoded and case["id"] not in encoded
                if profile == "v2":
                    assert len(request["input"]["drafts"]) == 1
    changed = dataset()
    changed["cases"][0]["expected_verdicts"].reverse()
    assert (
        await prepare(changed, OpenAICompatibleStructuredOutputConfig(model="fixture"))
    )["fingerprint"] != plan["fingerprint"]


async def test_uncertain_fake_is_complete_but_never_counted_as_correct():
    data = dataset()
    model = Probe()
    plan = await prepare(data, OpenAICompatibleStructuredOutputConfig(model="fixture"))
    result = await execute(data, plan, model)
    assert result["status"] == "complete" and len(model.requests) == 12
    for summary in result["summary"].values():
        assert summary["drafts_reviewed"] == summary["uncertain"] == 8
        assert summary["verdict_matches"] == summary["false_flags"] == 0
        assert summary["missed_flags"] == 4


async def test_cache_replay_is_exact_without_new_attempts(tmp_path):
    data = dataset()
    plan = await prepare(data, OpenAICompatibleStructuredOutputConfig(model="fixture"))
    ledger = DurableCallLedger(
        tmp_path / "calls", budget_id=plan["fingerprint"], max_calls=12
    )
    try:
        model = Probe()
        first = await execute(
            data,
            plan,
            PilotStructuredModel(model, ledger=ledger, cache_dir=tmp_path / "cache"),
        )
        forbidden = Probe()
        cached = PilotStructuredModel(
            forbidden, ledger=ledger, cache_dir=tmp_path / "cache", cache_only=True
        )
        second = await execute(data, plan, cached)
        assert first == second and not forbidden.requests
        assert cached.report()["cache_hits_this_instance"] == 12
        assert ledger.report()["attempts_reserved"] == 12
    finally:
        ledger.close()


async def test_request_drift_is_rejected_before_provider():
    model = Probe()
    bound = BoundModel(model, ["wrong-request-hash"])
    with pytest.raises(ValueError, match="frozen preflight"):
        await bound.generate(
            StructuredGenerationRequest(
                instructions="source", input={}, output_schema={"type": "object"}
            )
        )
    assert not model.requests


async def test_failure_stops_and_redacts_provider_body():
    class Failing(Probe):
        async def generate(self, request):
            self.requests.append(request)
            raise RuntimeError("private-key-and-provider-body")

    data = dataset()
    plan = await prepare(data, OpenAICompatibleStructuredOutputConfig(model="fixture"))
    model = Failing()
    result = await execute(data, plan, model)
    assert (
        result["status"] == "stopped"
        and len(model.requests) == len(result["rows"]) == 1
    )
    assert "private-key-and-provider-body" not in json.dumps(result)
    assert all(s["drafts_reviewed"] == 0 for s in result["summary"].values())
